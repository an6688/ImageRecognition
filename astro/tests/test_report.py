"""Offline report checks; run with the existing Python environment and Pillow."""
import base64
import csv
import importlib.util
import io
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from PIL import Image

spec = importlib.util.spec_from_file_location('astro_report', Path(__file__).parents[1] / 'report.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            self.images.append(dict(attrs)['src'])


class ReportTests(unittest.TestCase):
    def test_valid_report_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / 'image&test.png'
            Image.new('L', (64, 64), 50).save(image)
            row = dict(index='0', path=str(image), status='ok', width='64', height='64',
                       review_decision='no_elongation_flag', measured_candidates='1', peak_count='12',
                       coverage='limited', examined_peaks='1', skipped_peaks='11', analysis_version='elongation-v2',
                       review_reason='<unsafe & text>', elongated_fraction='1', median_elongation='2', analysis_ms='1')
            candidate = dict(index='0', path=str(image), candidate_id='0', x='32', y='32',
                             major_sigma='2', minor_sigma='1', angle_degrees='0', elongation='2', peak_contrast='.2', elongated='1')
            for name, record in [('summary.csv', row), ('candidates.csv', candidate)]:
                with (root/name).open('w', newline='', encoding='utf-8') as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(record))
                    writer.writeheader(); writer.writerow(record)
            output = root/'report.html'
            report.build(root/'summary.csv', root/'candidates.csv', output, '<title>')
            text = output.read_text(encoding='utf-8')
            self.assertIn('&lt;title&gt;', text)
            self.assertIn('No elongation flag (sample only)', text)
            self.assertIn('examined 1 of 12 detected peaks; skipped 11', text)
            self.assertIn('elongation-v2', text)
            self.assertIn('&lt;unsafe &amp; text&gt;', text)
            self.assertNotIn('<unsafe', text)
            parser = Assets(); parser.feed(text)
            self.assertEqual(len(parser.images), 2)
            for source in parser.images:
                self.assertTrue(source.startswith('data:image/jpeg;base64,'))
                with Image.open(io.BytesIO(base64.b64decode(source.split(',', 1)[1]))) as decoded:
                    decoded.verify()
            with self.assertRaises(FileExistsError):
                report.build(root/'summary.csv', root/'candidates.csv', output, 'second')
            with (root/'candidates.csv').open('w', newline='', encoding='utf-8') as handle:
                csv.DictWriter(handle, fieldnames=list(candidate)).writeheader()
            with self.assertRaisesRegex(ValueError, 'does not match'):
                report.build(root/'summary.csv', root/'candidates.csv', root/'bad.html', 'bad')


if __name__ == '__main__':
    unittest.main()
