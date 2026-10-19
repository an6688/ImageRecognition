"""Select detected faces or draw a manual rectangle in photo coordinates."""
import json
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageTk
from core import Indexer

class FaceEditor:
    def __init__(self, app, photo, path):
        self.app, self.photo = app, photo
        self.window = tk.Toplevel(app.root)
        self.window.title('Choose people in this photo')
        self.window.transient(app.root)
        self.window.grab_set()
        self.indexer = None
        self.selection = None
        self.drawn = None
        self.start = None
        ttk.Label(self.window, text='Click a detected face, or drag a rectangle around a missed face.', padding=12).pack()
        self.tags = ttk.Label(self.window, text='Tagged: ' + (', '.join(app.store.photo_labels(photo)) or 'No one yet'), padding=(12,0,12,10), wraplength=830)
        self.tags.pack(fill='x')
        self.canvas = tk.Canvas(self.window, width=850, height=500, background='#202638', highlightthickness=0)
        self.canvas.pack(padx=12)
        controls = ttk.Frame(self.window, padding=12); controls.pack(fill='x')
        self.people = app.store.db.execute("SELECT id,name FROM people WHERE hidden=0 ORDER BY name,id").fetchall()
        self.picker = ttk.Combobox(controls, state='readonly', width=30,
            values=['Create new person']+[f'{p["name"] or "Unnamed"} · Group {p["id"]}' for p in self.people])
        self.picker.current(0); self.picker.pack(side='left')
        self.name = ttk.Entry(controls, width=22); self.name.pack(side='left', padx=8)
        self.name.insert(0,'')
        self.save_button = ttk.Button(controls,text='Save selected face',command=self.save,state='disabled')
        self.save_button.pack(side='left')
        self.note = ttk.Label(self.window,text='Loading faces…',padding=12,wraplength=830); self.note.pack(fill='x')
        self.picker.bind('<<ComboboxSelected>>',lambda e:self.name.config(state='normal' if self.picker.current()==0 else 'disabled'))
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        self.path = path
        self.load_timer = self.window.after(30,self.load)

    def load(self):
        if self.indexer is not None:
            return
        try:
            self.indexer = Indexer(data=self.app.store.folder)
            self.image,self.candidates = self.indexer.inspect_photo(self.path)
            self.scale = min(850/self.image.width,500/self.image.height,1)
            self.preview = ImageTk.PhotoImage(self.image.resize((int(self.image.width*self.scale),int(self.image.height*self.scale))))
            self.canvas.create_image(0,0,image=self.preview,anchor='nw')
            for i,(box,_,_) in enumerate(self.candidates):
                x,y,w,h=box
                self.canvas.create_rectangle(x*self.scale,y*self.scale,(x+w)*self.scale,(y+h)*self.scale,outline='#75dca4',width=2)
            for row in self.app.store.assignments(self.photo):
                box = json.loads(row['box']) if row['box'] else None
                if box is None and row['embedding']:
                    feature = np.frombuffer(row['embedding'], dtype=np.float32)
                    matches = [candidate for candidate in self.candidates
                               if candidate[1].size == feature.size and float(candidate[1] @ feature) > 0.999]
                    if matches:
                        box = matches[0][0]
                if box is not None:
                    x,y,w,h=box
                    self.canvas.create_rectangle(x*self.scale,y*self.scale,(x+w)*self.scale,(y+h)*self.scale,outline='#f4c45c',width=2)
                    label = row['name'] or f"Person {row['person_id']}"
                    if row['hidden']: label += ' (hidden)'
                    tx=max(0,x*self.scale); ty=max(0,y*self.scale-20)
                    item=self.canvas.create_text(tx,ty,text=label,anchor='nw',fill='white',font=('Segoe UI',10,'bold'))
                    background=self.canvas.create_rectangle(self.canvas.bbox(item),fill='#202638',outline='')
                    self.canvas.tag_raise(item,background)
            self.canvas.bind('<ButtonPress-1>',self.press)
            self.canvas.bind('<B1-Motion>',self.drag)
            self.canvas.bind('<ButtonRelease-1>',self.release)
            self.note.config(text='Green boxes: detected faces. Gold boxes: saved manual selections. Choose an existing person or enter a new name.')
        except Exception as exc:
            self.note.config(text=f'Could not load photo: {exc}')

    def point(self,event):
        return (max(0,min(self.image.width,event.x/self.scale)),max(0,min(self.image.height,event.y/self.scale)))

    def press(self,event):
        self.start=self.point(event)
        self.selection=None
        self.save_button.config(state='disabled')
        if self.drawn: self.canvas.delete(self.drawn)
        self.drawn=None

    def drag(self,event):
        if self.start is None: return
        x,y=self.start; x2,y2=self.point(event)
        if self.drawn: self.canvas.delete(self.drawn)
        self.drawn=self.canvas.create_rectangle(x*self.scale,y*self.scale,x2*self.scale,y2*self.scale,outline='#faad55',width=3)

    def release(self,event):
        if self.start is None: return
        x,y=self.start; x2,y2=self.point(event)
        self.start=None
        if abs(x2-x)*self.scale<6 and abs(y2-y)*self.scale<6:
            hits=[c for c in self.candidates if c[0][0]<=x<=c[0][0]+c[0][2] and c[0][1]<=y<=c[0][1]+c[0][3]]
            if not hits:
                self.note.config(text='No detected face here. Drag a rectangle around the face to add it manually.')
                return
            self.selection=min(hits,key=lambda c:c[0][2]*c[0][3])
        else:
            box=[int(min(x,x2)),int(min(y,y2)),int(abs(x2-x)),int(abs(y2-y))]
            if min(box[2:])<12:
                self.note.config(text='Select a larger rectangle around the face.'); return
            try:
                feature,crop=self.indexer.describe_region(self.image,box)
                self.selection=(box,feature,crop)
            except Exception as exc:
                self.note.config(text=str(exc)); return
        if self.drawn: self.canvas.delete(self.drawn)
        box,feature,_=self.selection; x,y,w,h=box
        self.drawn=self.canvas.create_rectangle(x*self.scale,y*self.scale,(x+w)*self.scale,(y+h)*self.scale,outline='#faad55',width=3)
        self.save_button.config(state='normal')
        self.note.config(text='Face selected. Choose a person and save.' if feature.size else 'Manual tag only: recognition could not extract this face. You can still save it to a person; it will not teach future matching.')

    def save(self):
        if self.selection is None: return
        try:
            box,feature,crop=self.selection
            person=self.people[self.picker.current()-1]['id'] if self.picker.current()>0 else None
            self.app.store.save_selection(self.photo,box,feature,crop,person,self.name.get())
            self.app.render()
            self.app.status.config(text='Face saved. Manual selections are kept when unchanged photos are rescanned.')
            self.close()
        except Exception as exc:
            messagebox.showerror('Could not save selection',str(exc),parent=self.window)

    def close(self):
        self.window.after_cancel(self.load_timer)
        if self.indexer: self.indexer.store.close()
        self.window.destroy()
