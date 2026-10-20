"""Responsive preview for the recorded-video tracking demo."""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import cv2
from PIL import Image,ImageTk
from video_tracking import process_video

class VideoApp:
    def __init__(self,root):
        self.root=root;self.worker=None;self.output=None;self.closing=False
        self.cancel=threading.Event();self.frames=queue.Queue(maxsize=1);self.events=queue.Queue()
        root.title('Video tracking — vehicles');root.geometry('720x900')
        bar=ttk.Frame(root,padding=12);bar.pack(fill='x')
        self.open=ttk.Button(bar,text='Open video',command=self.start);self.open.pack(side='left')
        self.stop=ttk.Button(bar,text='Stop',state='disabled',command=self.cancel.set);self.stop.pack(side='left',padx=8)
        self.results=ttk.Button(bar,text='Open results',state='disabled',command=lambda:os.startfile(self.output));self.results.pack(side='left')
        ttk.Label(root,text='Vehicles • ONNX + BoT-SORT • Analyze up to 10 frames per video second').pack()
        ttk.Label(root,text='Preview runs at processing speed. IDs belong to this clip, not known identities.').pack()
        options=ttk.Frame(root,padding=8);options.pack()
        ttk.Label(options,text='Detection view:').pack(side='left',padx=8)
        self.rotation=tk.StringVar(value='90° counterclockwise (overhead)')
        self.rotation_box=ttk.Combobox(options,textvariable=self.rotation,state='readonly',width=32,
            values=['Original','90° counterclockwise (overhead)','180°','90° clockwise'])
        self.rotation_box.pack(side='left')
        self.status=ttk.Label(root,text='Choose a recorded video to begin.',wraplength=680,padding=10);self.status.pack()
        self.picture=ttk.Label(root,anchor='center');self.picture.pack(fill='both',expand=True)
        self.timer=root.after(80,self.poll);root.protocol('WM_DELETE_WINDOW',self.close)

    def start(self):
        if self.worker and self.worker.is_alive():return
        source=filedialog.askopenfilename(title='Choose a video',filetypes=[('Videos','*.mp4 *.mov *.avi *.mkv'),('All files','*.*')])
        if not source:return
        rotation={'Original':0,'90° counterclockwise (overhead)':90,'180°':180,'90° clockwise':270}[self.rotation.get()]
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
                output=process_video(source,cancel=self.cancel,preview=preview,rotation=rotation,
                    progress=lambda text:self.events.put(('status',text)))
                self.events.put(('done',output))
            except Exception as exc:self.events.put(('error',str(exc)))
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()

    def poll(self):
        try:
            rgb,info=self.frames.get_nowait()
            self.image=ImageTk.PhotoImage(Image.fromarray(rgb));self.picture.config(image=self.image)
        except queue.Empty:pass
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='status':self.status.config(text=value)
                else:
                    self.rotation_box.config(state='readonly')
                    self.open.config(state='normal');self.stop.config(state='disabled')
                    if kind=='done':
                        self.output=str(value);self.results.config(state='normal')
                        self.status.config(text=f'{"Stopped" if self.cancel.is_set() else "Finished"}. Video and tracking report saved. Click Open results.')
                    else:
                        self.status.config(text='Tracking failed.')
                        if not self.closing:messagebox.showerror('Video tracking',value)
        except queue.Empty:pass
        if self.closing and not (self.worker and self.worker.is_alive()):self.root.destroy();return
        self.timer=self.root.after(80,self.poll)

    def close(self):
        self.closing=True;self.cancel.set()
        self.open.config(state='disabled');self.status.config(text='Stopping and finishing the output file…')

if __name__=='__main__':
    root=tk.Tk();VideoApp(root);root.mainloop()
