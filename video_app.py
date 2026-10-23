"""Responsive preview for the recorded-video tracking demo."""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import cv2
from PIL import Image,ImageTk
from video_tracking import process_video,TrackingControl,SUBJECTS,pick_track

class VideoApp:
    def __init__(self,root,embedded=False):
        self.embedded=embedded;self.control=TrackingControl();self.latest=None;self.mapping=None
        self.root=root;self.worker=None;self.output=None;self.closing=False
        self.cancel=threading.Event();self.frames=queue.Queue(maxsize=1);self.events=queue.Queue()
        if not embedded:root.title('ImageRecognition — Videos');root.geometry('850x900')
        bar=ttk.Frame(root,padding=12);bar.pack(fill='x')
        self.open=ttk.Button(bar,text='Open video',command=self.start);self.open.pack(side='left')
        self.pause=ttk.Button(bar,text='Pause',state='disabled',command=self.toggle_pause);self.pause.pack(side='left',padx=6)
        ttk.Button(bar,text='Clear selection',command=lambda:self.select(None)).pack(side='left',padx=6)
        self.stop=ttk.Button(bar,text='Stop',state='disabled',command=self.cancel.set);self.stop.pack(side='left',padx=8)
        self.results=ttk.Button(bar,text='Open results',state='disabled',command=lambda:os.startfile(self.output));self.results.pack(side='left')
        ttk.Label(root,text='ONNX + BoT-SORT • Analyze up to 10 frames per video second').pack()
        ttk.Label(root,text='Pause and click a box to follow it. Tracking can lose subjects or confuse their IDs.').pack()
        options=ttk.Frame(root,padding=8);options.pack()
        self.subject=tk.StringVar(value='Vehicles')
        ttk.Label(options,text='Track:').pack(side='left',padx=8)
        self.subject_box=ttk.Combobox(options,textvariable=self.subject,values=list(SUBJECTS),state='readonly',width=12)
        self.subject_box.pack(side='left')
        ttk.Label(options,text='Detection view:').pack(side='left',padx=8)
        self.rotation=tk.StringVar(value='Original')
        self.rotation_box=ttk.Combobox(options,textvariable=self.rotation,state='readonly',width=32,
            values=['Original','90° counterclockwise (overhead)','180°','90° clockwise'])
        self.rotation_box.pack(side='left')
        self.selection=ttk.Label(root,text='Showing all tracks',padding=6);self.selection.pack()
        self.status=ttk.Label(root,text='Choose a recorded video to begin.',wraplength=680,padding=10);self.status.pack()
        self.picture=tk.Canvas(root,background='#202638',highlightthickness=0);self.picture.pack(fill='both',expand=True)
        self.picture.bind('<Button-1>',self.click);self.picture.bind('<Configure>',lambda _:self.render())
        self.timer=root.after(80,self.poll)
        if not embedded:root.protocol('WM_DELETE_WINDOW',self.close)

    def toggle_pause(self):
        if self.control.paused.is_set():self.control.paused.clear();self.pause.config(text='Pause')
        else:self.control.paused.set();self.pause.config(text='Resume')

    def select(self,identity):
        self.control.select(identity);self.render()

    def click(self,event):
        if not self.mapping or self.latest is None:return
        ox,oy,sx,sy=self.mapping
        identity=pick_track(self.latest[1].get('tracks',[]),(event.x-ox)/sx,(event.y-oy)/sy)
        if identity is not None:self.select(identity)

    def render(self):
        if self.latest is None:return
        rgb,info=self.latest;h,w=info.get('source_shape',rgb.shape[:2])
        cw=max(1,self.picture.winfo_width());ch=max(1,self.picture.winfo_height())
        scale=min(cw/w,ch/h);dw=max(1,int(w*scale));dh=max(1,int(h*scale))
        ox=(cw-dw)/2;oy=(ch-dh)/2;sx=dw/w;sy=dh/h;self.mapping=(ox,oy,sx,sy)
        self.image=ImageTk.PhotoImage(Image.fromarray(rgb).resize((dw,dh),Image.Resampling.LANCZOS))
        self.picture.delete('all');self.picture.create_image(ox,oy,image=self.image,anchor='nw')
        selected=self.control.selection();tracks=info.get('tracks',[])
        matches=[r for r in tracks if int(r[4])==selected]
        if selected is None:self.selection.config(text='Showing all tracks — click a box to select')
        elif not matches:self.selection.config(text=f'Track #{selected} lost / not visible. Selection retained.')
        else:self.selection.config(text=f'Following track #{selected}')
        classes=SUBJECTS.get(info.get('subject',self.subject.get()),{})
        for row in tracks:
            identity=int(row[4]);chosen=identity==selected
            color='#ffff00' if chosen else ('#999999' if selected is not None else '#66ddff')
            self.picture.create_rectangle(ox+row[0]*sx,oy+row[1]*sy,ox+row[2]*sx,oy+row[3]*sy,outline=color,width=4 if chosen else 2)
            self.picture.create_text(ox+row[0]*sx,max(oy+10,oy+row[1]*sy-8),anchor='sw',fill=color,
                text=f"{classes.get(int(row[6]),'Subject')} #{identity} {row[5]:.0%}",font=('Segoe UI',10,'bold'))

    def running(self):return self.worker is not None and self.worker.is_alive()

    def dispose(self):
        self.cancel.set();self.root.after_cancel(self.timer)

    def start(self):
        if self.worker and self.worker.is_alive():return
        source=filedialog.askopenfilename(title='Choose a video',filetypes=[('Videos','*.mp4 *.mov *.avi *.mkv'),('All files','*.*')])
        if not source:return
        rotation={'Original':0,'90° counterclockwise (overhead)':90,'180°':180,'90° clockwise':270}[self.rotation.get()]
        subject=self.subject.get()
        self.subject_box.config(state='disabled')
        self.control=TrackingControl();self.latest=None;self.mapping=None;self.picture.delete('all')
        self.selection.config(text='Showing all tracks')
        while not self.frames.empty():self.frames.get_nowait()
        self.pause.config(state='normal',text='Pause')
        self.rotation_box.config(state='disabled')
        self.cancel.clear();self.output=None;self.results.config(state='disabled')
        self.open.config(state='disabled');self.stop.config(state='normal');self.status.config(text='Loading model…')
        def preview(frame,info):
            h,w=frame.shape[:2];ratio=min(640/w,720/h,1)
            rgb=cv2.cvtColor(cv2.resize(frame,(int(w*ratio),int(h*ratio))),cv2.COLOR_BGR2RGB)
            try:self.frames.get_nowait()
            except queue.Empty:pass
            self.frames.put_nowait((rgb,info))
        def work():
            try:
                output=process_video(source,cancel=self.cancel,preview=preview,rotation=rotation,subject=subject,control=self.control,
                    progress=lambda text:self.events.put(('status',text)))
                self.events.put(('done',output))
            except Exception as exc:self.events.put(('error',str(exc)))
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()

    def poll(self):
        try:
            rgb,info=self.frames.get_nowait()
            self.latest=(rgb,info);self.render()
            if 'processing_fps' in info:self.status.config(text=f"Video {info['source_seconds']:.1f}s · Processing {info['processing_fps']:.1f} FPS · Analysis {info['analysis_fps']:g} FPS")
        except queue.Empty:pass
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='status':self.status.config(text=value)
                else:
                    self.subject_box.config(state='readonly');self.pause.config(state='disabled')
                    self.rotation_box.config(state='readonly')
                    self.open.config(state='normal');self.stop.config(state='disabled')
                    if kind=='done':
                        self.output=str(value);self.results.config(state='normal')
                        self.status.config(text=f'{"Stopped" if self.cancel.is_set() else "Finished"}. Video and tracking report saved. Click Open results.')
                    else:
                        self.status.config(text='Tracking failed.')
                        if not self.closing:messagebox.showerror('Video tracking',value)
        except queue.Empty:pass
        if self.closing and not self.running():
            if not self.embedded:self.root.destroy()
            return
        self.timer=self.root.after(80,self.poll)

    def close(self):
        self.closing=True;self.cancel.set()
        self.open.config(state='disabled');self.status.config(text='Stopping and finishing the output file…')

if __name__=='__main__':
    root=tk.Tk();VideoApp(root);root.mainloop()
