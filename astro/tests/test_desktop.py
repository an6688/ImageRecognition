"""Desktop session ownership and settings checks using disposable reports."""
import json
import gc
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.request import urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from astro.desktop import ReviewSession, load_state, save_state


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.images=self.root/'images';self.images.mkdir()
        self.report=self.make_report('first')
        self.session=ReviewSession(port=0)
        self.addCleanup(self.session.close)

    def make_report(self,name):
        image=self.images/(name+'.png');image.write_bytes(b'pixels')
        report=self.root/(name+'.html')
        data={'title':name,'frames':[{'path':str(image)}]}
        report.write_text('<script id="report-data" type="application/json">'+json.dumps(data)+'</script>',encoding='utf-8')
        return report

    def test_open_infers_folder_and_uses_current_ui(self):
        origin=self.session.start(self.report)
        self.assertEqual(self.session.server.root,self.images)
        with urlopen(origin,timeout=5) as response:
            html=response.read().decode()
        self.assertIn('Capture playback',html)
        self.assertIn(self.session.server.token,html)
        self.assertEqual(self.session.start(self.report),origin)
        self.assertTrue(self.session.thread.is_alive())

    def test_switch_stops_previous_service_and_close_stops_current(self):
        self.session.start(self.report)
        old_thread=self.session.thread
        second=self.make_report('second')
        self.session.start(second)
        self.assertFalse(old_thread.is_alive())
        current=self.session.thread
        self.assertEqual(self.session.server.report,second)
        self.session.close()
        self.assertFalse(current.is_alive())
        with self.assertRaisesRegex(RuntimeError,'closed'):
            self.session.start(second)

    def test_missing_and_invalid_reports_do_not_start_service(self):
        with self.assertRaises(FileNotFoundError):
            self.session.start(self.root/'missing.html')
        bad=self.root/'bad.html';bad.write_text('<html>Unrelated page</html>')
        with self.assertRaisesRegex(ValueError,'not a current'):
            self.session.start(bad)
        self.assertIsNone(self.session.server)

    def test_recent_report_settings_round_trip_and_corrupt_recovery(self):
        state=self.root/'settings/astrotrack.json'
        self.assertEqual(load_state(state),{})
        save_state(state,{'last_report':str(self.report)})
        self.assertEqual(load_state(state)['last_report'],str(self.report))
        state.write_text('not json')
        self.assertEqual(load_state(state),{})

    def test_folder_picker_starts_analysis_and_opens_finished_review(self):
        import tkinter as tk
        import time
        from unittest.mock import patch
        from astro.desktop import AstroPanel
        from astro.workflow import ReviewResult
        root=tk.Tk();root.withdraw()
        panel=AstroPanel(root,state_path=self.root/'ui-state.json')
        def analyze(folder,**kwargs):
            self.assertEqual(folder,str(self.images))
            kwargs['progress']({'phase':'previews','message':'Preparing previews','done':1,'total':2})
            return ReviewResult(self.report,self.root,2,0)
        try:
            with patch('astro.desktop.filedialog.askdirectory',return_value=str(self.images)), \
                 patch('astro.workflow.analyze_folder',side_effect=analyze), \
                 patch.object(panel.session,'start',return_value='http://127.0.0.1:8765'), \
                 patch('astro.desktop.webbrowser.open') as browser:
                panel.choose_folder()
                deadline=time.monotonic()+3
                while panel.busy and time.monotonic()<deadline:
                    root.update();time.sleep(.01)
                self.assertFalse(panel.busy)
                browser.assert_called_once_with('http://127.0.0.1:8765')
                self.assertIn('2 images',panel.status['text'])
                self.assertEqual(load_state(panel.state_path)['last_source'],str(self.images))
                self.assertFalse(panel.advanced_visible)
        finally:
            panel.dispose();root.destroy()
            del panel,root
            gc.collect()

    def test_cancel_button_leaves_existing_review_and_no_browser_open(self):
        import tkinter as tk
        import time
        from unittest.mock import patch
        from astro.desktop import AstroPanel
        from astro.workflow import AnalysisCancelled
        root=tk.Tk();root.withdraw()
        panel=AstroPanel(root,state_path=self.root/'cancel-state.json')
        def analyze(folder,**kwargs):
            self.assertTrue(kwargs['cancel'].wait(2))
            raise AnalysisCancelled('Analysis cancelled.')
        try:
            with patch('astro.workflow.analyze_folder',side_effect=analyze), \
                 patch('astro.desktop.webbrowser.open') as browser, \
                 patch.object(panel.session,'start') as start:
                panel.analyze_folder(str(self.images))
                self.assertEqual(str(panel.cancel_button['state']),'normal')
                panel.cancel_analysis()
                deadline=time.monotonic()+3
                while panel.busy and time.monotonic()<deadline:
                    root.update();time.sleep(.01)
                self.assertFalse(panel.busy)
                self.assertIn('cancelled',panel.status['text'])
                browser.assert_not_called();start.assert_not_called()
        finally:
            panel.dispose();root.destroy()
            del panel,root
            gc.collect()

    def test_panel_constructs_without_starting_helper_until_activated(self):
        import tkinter as tk
        from astro.desktop import AstroPanel
        root=tk.Tk();root.withdraw()
        try:
            panel=AstroPanel(root,state_path=self.root/'fresh-settings.json')
            root.update_idletasks()
            self.assertIsNone(panel.session.server)
            panel.activate()
            self.assertIsNone(panel.session.server)
            panel.dispose()
        finally:
            root.destroy()
            del panel,root
            gc.collect()


if __name__=='__main__':
    unittest.main()
