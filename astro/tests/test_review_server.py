"""HTTP integration checks for local review; all images are disposable fixtures."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).parents[1]))
import organize_review
from review_server import ReviewServer, SESSION_TAG, DATA_TAG


class LocalReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve()
        self.images=self.base/'images';self.images.mkdir()
        self.good=self.images/'good.png';self.good.write_bytes(b'good pixels')
        self.bad=self.images/'bad.png';self.bad.write_bytes(b'bad pixels')
        self.report=self.base/'report.html'
        data={'frames':[{'path':str(p)} for p in [self.good,self.bad]]}
        self.report.write_text('<html>'+SESSION_TAG+DATA_TAG+json.dumps(data)+'</script></html>')
        self.server=ReviewServer(self.report,self.images,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.headers={'Content-Type':'application/json','Origin':self.server.origin,'X-Astro-Token':self.server.token}

    def stop(self):
        self.server.shutdown();self.thread.join();self.server.server_close()

    def post(self,path,body,headers=None):
        request=Request(self.server.origin+path,json.dumps(body).encode(),headers=self.headers if headers is None else headers,method='POST')
        try:
            with urlopen(request,timeout=5) as response:
                return response.status,json.load(response)
        except HTTPError as exc:
            return exc.code,json.load(exc)

    def test_page_only_and_local_token(self):
        with urlopen(self.server.origin,timeout=5) as response:
            page=response.read().decode()
            self.assertIn(self.server.token,page)
            self.assertIn('Rejected',page)
            self.assertEqual(response.headers['X-Frame-Options'],'DENY')
        with self.assertRaises(HTTPError):
            urlopen(self.server.origin+'/../images/good.png',timeout=5)
        for headers in [{}, {**self.headers,'Origin':'https://unrelated.example'}, {**self.headers,'X-Astro-Token':'wrong'}, {**self.headers,'Host':'unrelated.example'}]:
            code,_=self.post('/api/plan',{'paths':[str(self.bad)]},headers)
            self.assertEqual(code,403)
        self.assertTrue(self.bad.exists())

    def test_preview_then_move_and_replay_rejected(self):
        code,plan=self.post('/api/plan',{'paths':[str(self.bad)]})
        self.assertEqual(code,200)
        self.assertEqual(len(plan['files']),1)
        self.assertTrue(self.bad.exists())
        self.assertFalse((self.images/'Rejected').exists())
        code,result=self.post('/api/move',{'plan':plan['plan']})
        self.assertEqual(code,200)
        self.assertFalse(self.bad.exists())
        self.assertEqual((self.images/'Rejected/bad.png').read_bytes(),b'bad pixels')
        self.assertEqual(self.good.read_bytes(),b'good pixels')
        self.assertIn(str(self.bad),result['moved'])
        code,_=self.post('/api/move',{'plan':plan['plan']})
        self.assertEqual(code,400)
        self.server.moved={}
        self.server.refresh_moved()
        self.assertIn(str(self.bad),self.server.moved)

    def test_only_report_files_can_move(self):
        stranger=self.images/'other.png';stranger.write_bytes(b'not in report')
        outside=self.base/'outside.png';outside.write_bytes(b'outside')
        for paths in [[str(stranger)],[str(outside)],[str(self.bad),str(self.bad)],[],['../bad.png']]:
            with self.subTest(paths=paths):
                code,_=self.post('/api/plan',{'paths':paths})
                self.assertEqual(code,400)
        self.assertTrue(self.bad.exists())

    def test_changed_image_invalidates_plan(self):
        _,plan=self.post('/api/plan',{'paths':[str(self.bad)]})
        self.bad.write_bytes(b'a different exposure')
        code,result=self.post('/api/move',{'plan':plan['plan']})
        self.assertEqual(code,400)
        self.assertIn('changed',result['error'])
        self.assertTrue(self.bad.exists())
        self.assertFalse((self.images/'Rejected').exists())

    def test_collision_after_preview_moves_nothing(self):
        _,plan=self.post('/api/plan',{'paths':[str(self.bad)]})
        folder=self.images/'Rejected';folder.mkdir()
        (folder/'bad.png').write_bytes(b'existing')
        code,_=self.post('/api/move',{'plan':plan['plan']})
        self.assertEqual(code,400)
        self.assertTrue(self.bad.exists())
        self.assertEqual((folder/'bad.png').read_bytes(),b'existing')

    def test_partial_failure_reports_completed_moves(self):
        _,plan=self.post('/api/plan',{'paths':[str(self.good),str(self.bad)]})
        original=organize_review.move_no_replace
        def move(source,destination,expected):
            if source==self.bad:
                raise OSError('Simulated copy failure')
            return original(source,destination,expected)
        with patch.object(organize_review,'move_no_replace',side_effect=move):
            code,result=self.post('/api/move',{'plan':plan['plan']})
        self.assertEqual(code,400)
        self.assertIn(str(self.good),result['moved'])
        self.assertNotIn(str(self.bad),result['moved'])
        self.assertEqual(self.bad.read_bytes(),b'bad pixels')
        self.assertEqual((self.images/'Rejected/good.png').read_bytes(),b'good pixels')

    def test_move_without_preview_is_rejected(self):
        code,_=self.post('/api/move',{'plan':'invented'})
        self.assertEqual(code,400)
        self.assertTrue(self.bad.exists())


if __name__=='__main__':
    unittest.main()
