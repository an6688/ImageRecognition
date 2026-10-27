"""Offline report checks with generated 16-bit fixtures."""
import base64
import csv
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

spec = importlib.util.spec_from_file_location(
    'astro_report', Path(__file__).parents[1] / 'report.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class ReportTests(unittest.TestCase):
    def setUp(self):
        # Keep fixtures in the checkout; this also works in restricted workspaces.
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.image = self.root / 'image&test.png'
        pixels = np.tile(np.arange(4096,8192,64,dtype=np.uint16),(64,1))
        self.pixels = pixels
        ok, encoded = cv2.imencode('.png', pixels)
        self.assertTrue(ok)
        encoded.tofile(self.image)
        self.row = dict(index='0', path=str(self.image), status='ok',
            width='64', height='64', review_decision='review_suggested',
            measured_candidates='1', peak_count='12', coverage='limited',
            examined_peaks='1', skipped_peaks='11', analysis_version='elongation-v2',
            review_reason='</script><script>unsafe</script>',
            elongated_fraction='1', median_elongation='2', analysis_ms='1')
        self.candidate = dict(index='0',path=str(self.image),candidate_id='0',
            x='32.25',y='31.75',major_sigma='2',minor_sigma='1',
            angle_degrees='10',elongation='2',peak_contrast='.2',elongated='1')

    def write_csv(self,name,records):
        with (self.root/name).open('w',newline='',encoding='utf-8') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)

    def build_fixture(self):
        self.write_csv('summary.csv',[self.row])
        self.write_csv('candidates.csv',[self.candidate])
        output=self.root/'report.html'
        report.build(self.root/'summary.csv',self.root/'candidates.csv',
                     output,'M31 <review>',workers=1)
        text=output.read_text(encoding='utf-8')
        payload=re.search(r'<script id="report-data" type="application/json">(.*?)</script>',
                          text,re.S).group(1)
        return output,text,json.loads(payload)

    def test_build_escape_assets_and_no_overwrite(self):
        output,text,data=self.build_fixture()
        self.assertIn('M31 &lt;review&gt;',text)
        self.assertNotIn('</script><script>unsafe',text)
        self.assertEqual(data['frames'][0]['reason'],self.row['review_reason'])
        frame=data['frames'][0]
        self.assertEqual(frame['coverage'],'limited')
        self.assertEqual(frame['skipped'],11)
        self.assertEqual(frame['decision'],'review_suggested')
        self.assertEqual(frame['count'],1)
        self.assertTrue(Path(frame['path']).is_absolute())
        self.assertEqual(Path(frame['path']),self.image.absolute())
        self.assertNotIn('See the evidence. Make the call.',text)
        self.assertNotIn('Why the earlier preview looked black.',text)
        for item in [frame,*frame['examples']]:
            for mode in ['linear','enhanced']:
                with Image.open(io.BytesIO(base64.b64decode(item[mode].split(',')[1]))) as im:
                    im.verify()
        with self.assertRaises(FileExistsError):
            report.build(self.root/'summary.csv',self.root/'candidates.csv',output,'Again')

    def test_launcher_quotes_paths_and_refuses_overwrite(self):
        directory=self.root/'night & 100%'
        directory.mkdir()
        output=directory/'review.html'
        launcher=report.write_launcher(output,directory)
        text=launcher.read_text(encoding='utf-8')
        self.assertIn('DisableDelayedExpansion',text)
        self.assertIn('chcp 65001',text)
        self.assertIn('"'+str(output.absolute()).replace('%','%%')+'"',text)
        self.assertIn('review_server.py"',text)
        before=launcher.read_bytes()
        with self.assertRaises(FileExistsError):
            report.write_launcher(output,directory)
        self.assertEqual(launcher.read_bytes(),before)

    def test_16bit_decode_and_display_separation(self):
        decoded=report.read_gray(self.image)
        self.assertEqual(decoded.dtype,np.uint16)
        np.testing.assert_array_equal(decoded,self.pixels)
        linear,enhanced,_=report.views(decoded)
        self.assertGreater(int(enhanced[7000])-int(enhanced[5000]),
                           int(linear[7000])-int(linear[5000]))
        np.testing.assert_array_equal(report.read_gray(self.image),self.pixels)

    def test_crop_and_overview_share_source_coordinates(self):
        frame=report.render_frame(self.row,[self.candidate])
        crop=frame['examples'][0]
        self.assertEqual((crop['cx'],crop['cy']),(20.25,19.75))
        self.assertEqual((crop['x'],crop['y']),(32.25,31.75))
        self.assertEqual(frame['markers'][0]['x'],32.25)
        self.assertEqual(frame['markers'][0]['y'],31.75)
        self.assertEqual(crop['ratio'],2)

    def test_mismatched_candidates_and_changed_dimensions(self):
        with self.assertRaisesRegex(ValueError,'count mismatch'):
            report.render_frame(self.row,[])
        self.row['width']='65'
        with self.assertRaisesRegex(ValueError,'size changed'):
            report.render_frame(self.row,[self.candidate])

    def test_legacy_count_and_failed_image(self):
        row=dict(self.row)
        row['usable_stars']=row.pop('measured_candidates')
        self.assertEqual(report.render_frame(row,[self.candidate])['count'],1)
        row.update(status='error',usable_stars='0',error='Decode failed',
                   review_decision='not_analyzed',path='missing.png')
        frame=report.render_frame(row,[])
        self.assertEqual(frame['error'],'Decode failed')
        self.assertEqual(frame['examples'],[])


if __name__=='__main__':
    unittest.main()
