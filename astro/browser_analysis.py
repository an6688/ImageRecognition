"""Thread-safe bridge from the report to the desktop folder picker."""
import secrets
import threading


class BrowserAnalysis:
    ACTIVE = {'choosing', 'analysis', 'previews', 'opening', 'cancelling'}

    def __init__(self, events):
        self.events = events
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.desktop_busy = False
        self.closed = False
        self.report = None
        self.state = {'phase': 'idle', 'job': None, 'message': ''}

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def choose(self):
        with self.lock:
            if self.closed or self.desktop_busy or self.state['phase'] in self.ACTIVE:
                raise ValueError('AstroTrack is busy. Finish or cancel the current operation first.')
            self.cancel = threading.Event()
            self.report = None
            self.state = {'phase': 'choosing', 'job': secrets.token_urlsafe(16),
                          'message': 'Choose a folder in the Windows folder picker.'}
            self.events.put(('browser_choose', self.state['job']))
            return self.snapshot()

    def update(self, phase, message, **extra):
        with self.lock:
            self.state.update(phase=phase, message=message, **extra)

    def progress(self, event):
        with self.lock:
            if not self.cancel.is_set():
                self.state.update(event)

    def cancel_job(self, job):
        with self.lock:
            self.check_job(job)
            if self.state['phase'] in self.ACTIVE:
                self.cancel.set()
                self.update('cancelling', 'Cancelling analysis…')
            return self.snapshot()

    def check_job(self, job):
        if not job or job != self.state['job']:
            raise ValueError('This analysis belongs to another request. Refresh the report.')

    def ready(self, result, message):
        with self.lock:
            self.report = result.report
            self.update('ready', message, done=result.total, total=result.total)

    def result(self, job):
        with self.lock:
            self.check_job(job)
            if self.closed or self.desktop_busy:
                raise ValueError('AstroTrack is busy or closing. Try opening the new review again when it is ready.')
            if self.state['phase'] != 'ready' or self.report is None:
                raise ValueError('The new review is not ready.')
            return self.report

    def opened(self):
        with self.lock:
            self.report = None
            self.state = {'phase': 'idle', 'job': None, 'message': ''}

    def close(self):
        with self.lock:
            self.closed = True
            self.cancel.set()
