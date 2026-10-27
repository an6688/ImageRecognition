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
        self.cancel=threading.Event()
        self.worker=None
        self.busy=False
        self.task=None
        self.closed=False
        self.closing=False
        self.activated=False
        outer=ttk.Frame(parent,padding=28)
        outer.pack(fill='both',expand=True)
        style=ttk.Style(parent)
        style.configure('Astro.Primary.TButton',padding=(16,10),font=('Segoe UI',11,'bold'))
        ttk.Label(outer,text='AstroTrack',font=('Segoe UI',25,'bold')).pack(anchor='w')
        ttk.Label(outer,text='Analyze a folder of exposures or open a saved review.',
                  wraplength=740).pack(anchor='w',pady=(6,18))
        primary=ttk.LabelFrame(outer,text='New review',padding=16)
        primary.pack(fill='x')
        self.analyze_button=ttk.Button(primary,text='Choose image folder…',
            style='Astro.Primary.TButton',command=self.choose_folder)
        self.analyze_button.pack(anchor='w')
        ttk.Label(primary,text='PNG, JPEG and TIFF · Selected folder only, without subfolders · Processed locally.',
                  wraplength=730).pack(anchor='w',pady=(8,0))
        self.folder_label=ttk.Label(primary,text=str(self.state.get('last_source','')),wraplength=730)
        self.folder_label.pack(anchor='w',pady=(4,0))
        review=ttk.LabelFrame(outer,text='Saved review',padding=16)
        review.pack(fill='x',pady=(14,12))
        self.report_label=ttk.Label(review,text=str(self.state.get('last_report','No saved review selected')),
                                   wraplength=730)
        self.report_label.pack(anchor='w',pady=(0,10))
        row=ttk.Frame(review);row.pack(fill='x')
        self.open_button=ttk.Button(row,text='Open saved review…',command=self.choose_report)
        self.open_button.pack(side='left')
        self.reopen_button=ttk.Button(row,text='Reopen last review',command=self.reopen)
        self.reopen_button.pack(side='left',padx=10)
        self.progress_row=ttk.Frame(outer)
        self.progress=ttk.Progressbar(self.progress_row,mode='indeterminate')
        self.progress.pack(side='left',fill='x',expand=True)
        self.cancel_button=ttk.Button(self.progress_row,text='Cancel analysis',command=self.cancel_analysis,state='disabled')
        self.cancel_button.pack(side='right',padx=(12,0))
        self.status=ttk.Label(outer,text='Choose an image folder to create a review, or open one you saved earlier.',wraplength=760)
        self.status.pack(anchor='w',pady=(0,10))
        self.advanced_visible=False
        self.advanced_toggle=ttk.Checkbutton(outer,text='Advanced sequence tools',command=self.toggle_advanced)
        self.advanced_toggle.pack(anchor='w')
        self.advanced=ttk.LabelFrame(outer,text='Aligned sequence explorer',padding=16)
        ttk.Label(self.advanced,text='Compare alignment, differences and projections across 2–40 matching exposures. '
                  'Use normal capture playback for the full sequence.',wraplength=730).pack(anchor='w',pady=(0,10))
        buttons=ttk.Frame(self.advanced);buttons.pack(fill='x')
        self.sequence_open=ttk.Button(buttons,text='Open saved explorer…',command=self.open_sequence)
        self.sequence_open.pack(side='left')
        self.sequence_build=ttk.Button(buttons,text='Create aligned explorer…',command=self.build_sequence)
        self.sequence_build.pack(side='left',padx=10)
        self.set_busy(False)
        self.timer=parent.after(100,self.poll)

    def toggle_advanced(self):
        self.advanced_visible=self.advanced_toggle.instate(['selected'])
        if self.advanced_visible:
            self.advanced.pack(fill='x',pady=(10,0))
        else:
            self.advanced.pack_forget()

    def activate(self):
        if self.activated or self.closed:
            return
        self.activated=True
        if self.state.get('last_report'):
            self.reopen()

    def choose_folder(self):
        if self.busy or self.closed:
            return
        initial=self.state.get('last_source')
        folder=filedialog.askdirectory(parent=self.parent,title='Choose captures to analyze',
            **({'initialdir':initial} if initial and Path(initial).is_dir() else {}))
        if folder:
            self.analyze_folder(folder)

    def analyze_folder(self, folder):
        if self.busy or self.closed:
            return
        self.cancel=threading.Event()
        self.task='analysis'
        self.state['last_source']=str(folder)
        self.folder_label.config(text=str(folder))
        self.set_busy(True,cancellable=True)
        self.status.config(text='Checking the image folder…')
        def work():
            from .workflow import analyze_folder, AnalysisCancelled
            try:
                result=analyze_folder(folder,cancel=self.cancel,progress=lambda event:self.events.put(('progress',event)))
                if self.cancel.is_set():
                    raise AnalysisCancelled('Analysis cancelled. Generated results were kept; your source images were not changed.')
                self.events.put(('progress',{'phase':'opening','message':'Opening the review…','done':None,'total':0}))
                origin=self.session.start(result.report)
                if self.cancel.is_set():
                    raise AnalysisCancelled('Analysis cancelled. Generated results were kept; your source images were not changed.')
                self.events.put(('created',(result,origin)))
            except AnalysisCancelled as error:
                self.events.put(('cancelled',str(error)))
            except Exception as error:
                self.events.put(('error',str(error)))
        self.worker=threading.Thread(target=work,daemon=True)
        self.worker.start()

    def cancel_analysis(self):
        if self.busy and self.task=='analysis' and not self.cancel.is_set():
            self.cancel.set()
            self.cancel_button.config(state='disabled')
            self.status.config(text='Cancelling analysis… waiting for the current work to stop safely.')

    def choose_report(self):
        path=filedialog.askopenfilename(parent=self.parent,title='Open AstroTrack review',
            initialdir=str(REPO/'data/astrotrack-runs' if (REPO/'data/astrotrack-runs').exists() else REPO/'astro/results'),
            filetypes=[('AstroTrack report','*.html')])
        if path:
            self.open_report(path)

    def reopen(self):
        path=self.state.get('last_report')
        if path and Path(path).is_file():
            self.open_report(path)
        else:
            self.status.config(text='Choose a saved report, or select an image folder to make a new review.')
            if path:
                self.choose_report()

    def set_busy(self, value, cancellable=False):
        self.busy=value
        for button in [self.analyze_button,self.open_button,self.reopen_button,self.sequence_open,self.sequence_build]:
            button.config(state='disabled' if value else 'normal')
        if value:
            self.progress.configure(mode='indeterminate')
            self.progress.start(12)
            self.progress_row.pack(fill='x',pady=(2,10),before=self.status)
        else:
            self.task=None
            self.progress.stop()
            self.progress_row.pack_forget()
            if not self.state.get('last_report'):
                self.reopen_button.config(state='disabled')
        self.cancel_button.config(state='normal' if value and cancellable else 'disabled')

    def show_progress(self, event):
        if self.cancel.is_set() and self.task=='analysis':
            return
        self.status.config(text=event['message'])
        if event.get('done') is not None and event.get('total'):
            self.progress.stop()
            self.progress.configure(mode='determinate',maximum=event['total'],value=event['done'])
        elif str(self.progress.cget('mode'))!='indeterminate':
            self.progress.configure(mode='indeterminate')
            self.progress.start(12)
        if event.get('phase')=='opening':
            self.cancel_button.config(state='disabled')

    def open_report(self, path):
        if self.busy or self.closed:
            return
        self.task='opening'
        self.set_busy(True)
        self.status.config(text='Opening the review…')
        def work():
            try:
                origin=self.session.start(path)
                if not self.closed:
                    self.events.put(('review',(str(Path(path).resolve()),origin)))
            except Exception as error:
                self.events.put(('error',str(error)))
        self.worker=threading.Thread(target=work,daemon=True)
        self.worker.start()

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
        self.task='sequence'
        self.set_busy(True)
        self.status.config(text='Aligning exposures and building the sequence explorer…')
        def work():
            try:
                from .sequence import build
                build(Path(folder),Path(output))
                self.events.put(('sequence',str(Path(output).resolve())))
            except Exception as error:
                self.events.put(('error',str(error)))
        self.worker=threading.Thread(target=work,daemon=True)
        self.worker.start()

    def review_ready(self, path, origin, message):
        self.state['last_report']=str(path)
        self.report_label.config(text=str(path))
        self.reopen_button.config(state='normal')
        self.status.config(text=message)
        try:
            save_state(self.state_path,self.state)
        except OSError:
            self.status.config(text=message+' The recent-review setting could not be saved.')
        if not self.closing:
            webbrowser.open(origin)

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':
                    self.show_progress(value)
                    continue
                # The terminal event may arrive just before the worker returns.
                # Join while the UI still owns its widgets, so worker cleanup
                # cannot release the last Tk references on a background thread.
                if self.worker is not None:
                    self.worker.join()
                    self.worker=None
                self.set_busy(False)
                if kind=='review':
                    path,origin=value
                    self.review_ready(path,origin,'Review open. Playback and folder actions are ready.')
                elif kind=='created':
                    result,origin=value
                    message=f'Review ready: {result.total:,} images.'
                    if result.failed:
                        message+=f' {result.failed:,} could not be read; the report lists them.'
                    self.review_ready(result.report,origin,message)
                elif kind=='sequence':
                    self.status.config(text='Aligned explorer ready.')
                    if not self.closing:
                        webbrowser.open(Path(value).as_uri())
                elif kind=='cancelled':
                    self.status.config(text=value)
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
        self.cancel.set()
        if self.worker is not None:
            self.worker.join()
            self.worker=None
        self.session.close()
