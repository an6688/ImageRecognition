"""Desktop-managed AstroTrack review sessions and launch panel."""
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

from .review_server import ReviewServer

REPO = Path(__file__).resolve().parents[1]
DEFAULT_STATE = REPO/'data/astrotrack.json'


def load_state(path):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):
        return {}


def save_state(path, state):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state,indent=2),encoding='utf-8')
    temporary.replace(path)


class ReviewSession:
    """Own the local service, including switching reports and orderly shutdown."""
    def __init__(self, port=8765):
        self.port=port
        self.server=None
        self.thread=None
        self.closed=False
        self.lock=threading.RLock()

    def start(self, report):
        report=Path(report).resolve(strict=True)
        with self.lock:
            if self.closed:
                raise RuntimeError('AstroTrack has closed.')
            if self.server and self.server.report==report:
                return self.server.origin
            self._stop()
            try:
                server=ReviewServer(report,None,self.port)
            except OSError as error:
                if getattr(error,'winerror',None)==10048 or getattr(error,'errno',None) in (98,10048):
                    raise RuntimeError('Another AstroTrack window or older report launcher is already open. Close it, then reopen this review.') from error
                raise
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.1},daemon=True)
            self.server,self.thread=server,thread
            thread.start()
            return server.origin

    def _stop(self):
        if self.server:
            # shutdown waits for an in-progress file move to finish.
            self.server.shutdown()
            self.thread.join()
            self.server.server_close()
            self.server=self.thread=None

    def close(self):
        with self.lock:
            self.closed=True
            self._stop()


class AstroPanel:
    def __init__(self, parent, state_path=DEFAULT_STATE):
        self.parent=parent
        self.state_path=Path(state_path)
        self.state=load_state(self.state_path)
        self.session=ReviewSession()
        self.events=queue.Queue()
        self.busy=False
        self.closed=False
        self.closing=False
        self.activated=False
        outer=ttk.Frame(parent,padding=28)
        outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='AstroTrack',font=('Segoe UI',25,'bold')).pack(anchor='w')
        ttk.Label(outer,text='Review captures, play the sequence, and set rejected images aside.',
                  wraplength=760).pack(anchor='w',pady=(8,24))
        review=ttk.LabelFrame(outer,text='Exposure review',padding=18)
        review.pack(fill='x')
        self.report_label=ttk.Label(review,text=str(self.state.get('last_report','No report selected')),
                                    wraplength=740)
        self.report_label.pack(anchor='w',pady=(0,12))
        row=ttk.Frame(review);row.pack(fill='x')
        self.open_button=ttk.Button(row,text='Open review…',command=self.choose_report)
        self.open_button.pack(side='left')
        self.reopen_button=ttk.Button(row,text='Reopen last review',command=self.reopen)
        self.reopen_button.pack(side='left',padx=10)
        ttk.Label(review,text='The review opens in your browser. Folder access starts automatically while this app is open.',
                  wraplength=740).pack(anchor='w',pady=(12,0))
        advanced=ttk.LabelFrame(outer,text='Aligned sequence explorer',padding=18)
        advanced.pack(fill='x',pady=20)
        ttk.Label(advanced,text='Compare aligned exposures, differences, and max / median / variation views. '
                  'This experimental viewer supports up to 40 images; normal report playback uses the full sequence.',
                  wraplength=740).pack(anchor='w',pady=(0,12))
        buttons=ttk.Frame(advanced);buttons.pack(fill='x')
        self.sequence_open=ttk.Button(buttons,text='Open saved explorer…',command=self.open_sequence)
        self.sequence_open.pack(side='left')
        self.sequence_build=ttk.Button(buttons,text='Create aligned explorer…',command=self.build_sequence)
        self.sequence_build.pack(side='left',padx=10)
        self.status=ttk.Label(outer,text='Open an existing AstroTrack review to get started.',wraplength=780)
        self.status.pack(anchor='w',pady=8)
        self.timer=parent.after(100,self.poll)

    def activate(self):
        if self.activated or self.closed:
            return
        self.activated=True
        if self.state.get('last_report'):
            self.reopen()

    def choose_report(self):
        path=filedialog.askopenfilename(parent=self.parent,title='Open AstroTrack review',
            initialdir=str(REPO/'astro/results'),filetypes=[('AstroTrack report','*.html')])
        if path:
            self.open_report(path)

    def reopen(self):
        path=self.state.get('last_report')
        if path and Path(path).is_file():
            self.open_report(path)
        else:
            self.status.config(text='Choose a report with Open review.')
            if path:
                self.choose_report()

    def set_busy(self, value):
        self.busy=value
        for button in [self.open_button,self.reopen_button,self.sequence_open,self.sequence_build]:
            button.config(state='disabled' if value else 'normal')

    def open_report(self, path):
        if self.busy or self.closed:
            return
        self.set_busy(True)
        self.status.config(text='Opening the review…')
        def work():
            try:
                origin=self.session.start(path)
                if not self.closed:
                    self.events.put(('review',(str(Path(path).resolve()),origin)))
            except Exception as error:
                self.events.put(('error',str(error)))
        threading.Thread(target=work,daemon=True).start()

    def open_sequence(self):
        path=filedialog.askopenfilename(parent=self.parent,title='Open aligned sequence explorer',
            initialdir=str(REPO/'astro/results'),filetypes=[('Sequence explorer','*.html')])
        if path:
            webbrowser.open(Path(path).resolve().as_uri())

    def build_sequence(self):
        if self.busy or self.closed:
            return
        folder=filedialog.askdirectory(parent=self.parent,title='Choose 2–40 matching exposures')
        if not folder:
            return
        output=filedialog.asksaveasfilename(parent=self.parent,title='Save aligned sequence explorer',
            defaultextension='.html',initialfile='sequence.html',filetypes=[('HTML','*.html')])
        if not output:
            return
        self.set_busy(True)
        self.status.config(text='Aligning exposures and building the sequence explorer…')
        def work():
            try:
                from .sequence import build
                build(Path(folder),Path(output))
                self.events.put(('sequence',str(Path(output).resolve())))
            except Exception as error:
                self.events.put(('error',str(error)))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                kind,value=self.events.get_nowait()
                self.set_busy(False)
                if kind=='review':
                    path,origin=value
                    self.state['last_report']=path
                    self.report_label.config(text=path)
                    self.status.config(text='Review open. Playback and folder actions are ready. Keep AstroTrack open while reviewing.')
                    try:
                        save_state(self.state_path,self.state)
                    except OSError:
                        self.status.config(text='Review open. The recent-report setting could not be saved.')
                    if not self.closing:
                        webbrowser.open(origin)
                elif kind=='sequence':
                    self.status.config(text='Aligned explorer ready.')
                    if not self.closing:
                        webbrowser.open(Path(value).as_uri())
                else:
                    self.status.config(text=value)
                    if not self.closing:
                        messagebox.showerror('AstroTrack',value,parent=self.parent)
        except queue.Empty:
            pass
        self.timer=self.parent.after(100,self.poll)

    def dispose(self):
        self.closed=True
        self.parent.after_cancel(self.timer)
        self.session.close()
