"""Report-to-desktop analysis checks; all exposures are disposable fixtures."""
import gc
import json
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from astro.desktop import AstroPanel
from astro.workflow import analyze_folder, AnalysisCancelled, find_analyzer


class ReportAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.base=Path(self.tmp.name).resolve()
        self.images=self.base/'old';self.images.mkdir()
        image=self.images/'old.png';image.write_bytes(b'original')
        self.report=self.base/'old.html'
        self.report.write_text('<script id="report-data" type="application/json">'+
            json.dumps({'title':'Old review','frames':[{'path':str(image)}]})+'</script>')
        self.root=tk.Tk();self.root.withdraw()
        self.panel=AstroPanel(self.root,state_path=self.base/'settings.json')
        self.panel.session.port=0
        self.origin=self.panel.session.start(self.report)
        self.server=self.panel.session.server
        self.token=self.server.token

    def tearDown(self):
        self.panel.dispose();self.root.destroy()
        del self.panel,self.root
        gc.collect()
        self.tmp.cleanup()

    def post(self,route,body=None,token=None):
        headers={'Origin':self.origin,'Content-Type':'application/json',
                 'X-Astro-Token':self.token if token is None else token}
        request=Request(self.origin+route,json.dumps(body or {}).encode(),headers=headers,method='POST')
        try:
            with urlopen(request,timeout=5) as response:
                return response.status,json.load(response)
        except HTTPError as error:
            return error.code,json.load(error)

    def pump(self,phases):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            self.root.update()
            state=self.panel.browser_analysis.snapshot()
            if state['phase'] in phases:
                return state
            time.sleep(.01)
        self.fail('Analysis did not finish: '+str(state))

    def test_authentication_duplicate_requests_and_picker_cancel(self):
        with patch('astro.desktop.filedialog.askdirectory',return_value='') as picker:
            self.assertEqual(self.post('/api/analysis/choose',token='wrong')[0],403)
            self.assertTrue(self.panel.events.empty())
            code,job=self.post('/api/analysis/choose',{'folder':'untrusted-path'})
            self.assertEqual(code,200)
            self.assertEqual(self.post('/api/analysis/choose')[0],400)
            self.pump({'cancelled'})
            picker.assert_called_once()
        self.assertEqual(self.server.report,self.report)
        self.assertEqual(self.post('/api/analysis/open',{'job':job['job']})[0],400)
        self.assertEqual(self.post('/api/analysis/cancel',{'job':'stale'})[0],400)

    def test_real_analysis_switches_same_server_and_invalidates_old_token(self):
        import cv2
        import numpy as np
        try:
            find_analyzer()
        except FileNotFoundError:
            self.skipTest('Build the C++ analyzer for this integration test.')
        folder=self.base/'new captures';folder.mkdir()
        path=folder/'capture.png'
        pixels=np.zeros((64,64),dtype=np.uint16);pixels[20:23,30:33]=40000
        cv2.imwrite(str(path),pixels)
        original=path.read_bytes()
        def run(folder,**kwargs):
            return analyze_folder(folder,output_root=self.base/'runs',**kwargs)
        with patch('astro.desktop.filedialog.askdirectory',return_value=str(folder)), \
             patch('astro.workflow.analyze_folder',side_effect=run), \
             patch('astro.desktop.webbrowser.open') as browser:
            _,job=self.post('/api/analysis/choose')
            state=self.pump({'ready','error'})
            self.assertEqual(state['phase'],'ready',state)
            self.assertEqual(self.server.report,self.report)
            browser.assert_not_called()
            _,state=self.post('/api/analysis/status')
            self.assertEqual(state['job'],job['job'])
            code,result=self.post('/api/analysis/open',{'job':job['job']})
            self.assertEqual(code,200,result);self.assertTrue(result['reload'])
        self.assertIs(self.panel.session.server,self.server)
        self.assertEqual(self.server.origin,self.origin)
        self.assertEqual(self.server.root,folder)
        self.assertEqual(self.server.allowed,{str(path)})
        self.assertNotEqual(self.server.token,self.token)
        self.assertEqual(self.post('/api/analysis/choose')[0],403)
        self.token=self.server.token
        self.assertEqual(self.post('/api/plan',{'paths':[str(self.images/'old.png')]})[0],400)
        with urlopen(self.origin,timeout=5) as response:
            page=response.read().decode()
        self.assertIn('new captures',page)
        self.assertIn('"analysisEnabled": true',page)
        self.assertEqual(path.read_bytes(),original)

    def test_cancel_running_analysis_keeps_current_review(self):
        def run(folder,**kwargs):
            kwargs['progress']({'phase':'previews','message':'Preparing previews','done':1,'total':5})
            kwargs['cancel'].wait(5)
            raise AnalysisCancelled('Analysis cancelled.')
        with patch('astro.desktop.filedialog.askdirectory',return_value=str(self.images)), \
             patch('astro.workflow.analyze_folder',side_effect=run):
            _,job=self.post('/api/analysis/choose')
            self.pump({'previews'})
            self.assertEqual(self.post('/api/plan',{'paths':[str(self.images/'old.png')]})[0],400)
            code,state=self.post('/api/analysis/cancel',{'job':job['job']})
            self.assertEqual(code,200)
            self.assertEqual(state['phase'],'cancelling')
            self.pump({'cancelled'})
        self.assertEqual(self.server.report,self.report)
        self.assertEqual(self.server.token,self.token)

    def test_analysis_errors_stay_in_report_and_allow_retry(self):
        with patch('astro.desktop.filedialog.askdirectory',return_value=str(self.images)), \
             patch('astro.workflow.analyze_folder',side_effect=ValueError('No readable captures')), \
             patch('astro.desktop.messagebox.showerror') as dialog:
            self.post('/api/analysis/choose')
            state=self.pump({'error'})
            self.assertEqual(state['message'],'No readable captures')
            dialog.assert_not_called()
        self.assertEqual(self.server.report,self.report)
        self.assertEqual(self.post('/api/analysis/choose')[0],200)
        self.panel.browser_analysis.cancel.set()
        with patch('astro.desktop.filedialog.askdirectory',return_value=''):
            self.pump({'cancelled'})

    def test_invalid_replacement_preserves_report_and_move_plans(self):
        self.server.plans={'old':'plan'}
        invalid=self.base/'invalid.html';invalid.write_text('bad report')
        with self.assertRaises(ValueError):
            self.server.load_report(invalid)
        self.assertEqual(self.server.report,self.report)
        self.assertEqual(self.server.token,self.token)
        self.assertEqual(self.server.plans,{'old':'plan'})


if __name__=='__main__':
    unittest.main()
