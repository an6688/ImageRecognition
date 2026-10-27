"""Folder-to-review workflow checks with synthetic images and the existing analyzer."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from astro import workflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.images=self.root/'images & spaces';self.images.mkdir()
        self.output=self.root/'runs'
        pixels=np.full((96,96),800,dtype=np.uint16)
        for x,y in [(20,20),(60,20),(20,60),(60,60)]:
            cv2.circle(pixels,(x,y),2,30000,-1)
        ok,encoded=cv2.imencode('.png',pixels)
        self.assertTrue(ok)
        for name in ['001.png','002.png']:
            encoded.tofile(self.images/name)

    def hashes(self):
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.images.iterdir() if p.is_file()}

    def analyzer(self):
        try:
            return workflow.find_analyzer()
        except FileNotFoundError:
            self.skipTest('Build the analyzer to run this integration test')

    def test_real_folder_produces_review_and_preserves_originals(self):
        original=self.hashes();events=[]
        result=workflow.analyze_folder(self.images,output_root=self.output,
            executable=self.analyzer(),progress=events.append)
        self.assertEqual(result.total,2)
        self.assertEqual(result.failed,0)
        self.assertTrue(result.report.is_file())
        self.assertIn('Capture playback',result.report.read_text(encoding='utf-8'))
        self.assertEqual(json.loads((result.run_dir/'run.json').read_text())['state'],'ready')
        self.assertEqual(self.hashes(),original)
        self.assertEqual(events[0]['phase'],'analysis')
        self.assertEqual([e['done'] for e in events if e['phase']=='previews'],[0,1,2])

    def test_partial_decode_failure_is_visible_in_review(self):
        (self.images/'broken.png').write_bytes(b'not an image')
        result=workflow.analyze_folder(self.images,output_root=self.output,executable=self.analyzer())
        self.assertEqual((result.total,result.failed),(3,1))
        html=result.report.read_text(encoding='utf-8')
        self.assertIn('broken.png',html)
        self.assertIn('"status":"error"',html)

    def test_repeat_run_uses_new_output_and_excludes_subfolders(self):
        nested=self.images/'Rejected';nested.mkdir()
        (nested/'old.png').write_bytes(b'ignored nested image')
        first=workflow.analyze_folder(self.images,output_root=self.output,executable=self.analyzer())
        second=workflow.analyze_folder(self.images,output_root=self.output,executable=self.analyzer())
        self.assertNotEqual(first.run_dir,second.run_dir)
        self.assertEqual(second.total,2)
        self.assertTrue(first.report.exists())

    def test_cancelled_before_start_creates_nothing(self):
        event=threading.Event();event.set()
        with self.assertRaises(workflow.AnalysisCancelled):
            workflow.analyze_folder(self.images,output_root=self.output,cancel=event)
        self.assertFalse(self.output.exists())

    def test_cancel_during_previews_keeps_sources_and_marks_run_cancelled(self):
        event=threading.Event();original=self.hashes()
        def progress(value):
            if value['phase']=='previews' and value.get('done')==1:
                event.set()
        with self.assertRaises(workflow.AnalysisCancelled):
            workflow.analyze_folder(self.images,output_root=self.output,
                executable=self.analyzer(),cancel=event,progress=progress)
        run=next(self.output.iterdir())
        self.assertEqual(json.loads((run/'run.json').read_text())['state'],'cancelled')
        self.assertFalse((run/'review.html').exists())
        self.assertEqual(self.hashes(),original)

    def test_empty_and_fits_only_folders_explain_supported_formats(self):
        empty=self.root/'empty';empty.mkdir()
        (empty/'raw.fit').write_bytes(b'raw')
        with self.assertRaisesRegex(ValueError,'FITS'):
            workflow.inspect_folder(empty)

    def test_missing_analyzer_and_all_unreadable_images(self):
        with self.assertRaisesRegex(FileNotFoundError,'not been built'):
            workflow.find_analyzer(self.root)
        with self.assertRaisesRegex(FileNotFoundError,'could not be found'):
            workflow.analyze_folder(self.images,executable=self.root/'missing.exe',output_root=self.output)
        bad=self.root/'bad';bad.mkdir();(bad/'image.png').write_bytes(b'broken')
        with self.assertRaisesRegex(ValueError,'None of the images'):
            workflow.analyze_folder(bad,executable=self.analyzer(),output_root=self.output)
        run=next(self.output.iterdir())
        self.assertEqual(json.loads((run/'run.json').read_text())['state'],'error')
        self.assertFalse((run/'review.html').exists())

    def test_cancel_terminates_only_owned_analyzer_process(self):
        class Process:
            stopped=False
            returncode=None
            def poll(self):
                return self.returncode
            def terminate(self):
                self.stopped=True;self.returncode=-1
            def wait(self,timeout=None):
                return self.returncode
        process=Process();event=threading.Event();event.set()
        with patch.object(workflow.subprocess,'Popen',return_value=process):
            with self.assertRaises(workflow.AnalysisCancelled):
                workflow.run_analyzer(Path('analyzer.exe'),self.images,self.root/'a.csv',
                    self.root/'b.csv',self.root/'log.txt',event)
        self.assertTrue(process.stopped)


if __name__=='__main__':
    unittest.main()
