"""File organizer tests use disposable fixtures, never real exposures."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('organizer', Path(__file__).parents[1]/'organize_review.py')
organizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(organizer)


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base/'images'
        self.root.mkdir()
        self.review = self.base/'review.json'
        self.entries = []
        for name, decision in [('good.png','keep'),('bad.png','reject'),('maybe.png','revisit'),('unknown.png','unreviewed')]:
            path = self.root/name
            path.write_bytes(('pixels-'+name).encode())
            self.entries.append({'path':str(path),'review_decision':decision})
        self.write()

    def write(self):
        self.doc = {'kind':'astrotrack-review','schema_version':1,'assessments':self.entries}
        self.review.write_text(json.dumps(self.doc),encoding='utf-8')

    def test_preview_then_apply_exact_rejections(self):
        before = self.review.read_bytes()
        organizer.organize(self.review,self.root)
        self.assertFalse((self.root/'Rejected').exists())
        journal = organizer.organize(self.review,self.root,True)
        self.assertFalse((self.root/'bad.png').exists())
        self.assertEqual((self.root/'Rejected/bad.png').read_bytes(),b'pixels-bad.png')
        for name in ('good.png','maybe.png','unknown.png'):
            self.assertTrue((self.root/name).exists())
        events = [json.loads(line) for line in journal.read_text().splitlines()]
        self.assertEqual([e['status'] for e in events],['planned','moved'])
        self.assertEqual(events[-1]['source'],str(self.root/'bad.png'))
        self.assertEqual(self.review.read_bytes(),before)

    def test_collision_aborts_before_any_move(self):
        (self.root/'Rejected').mkdir()
        destination=self.root/'Rejected/bad.png'
        destination.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):
            organizer.organize(self.review,self.root,True)
        self.assertEqual(destination.read_bytes(),b'existing')
        self.assertTrue((self.root/'bad.png').exists())

    def test_missing_later_file_preflights_entire_batch(self):
        self.entries.append({'path':str(self.root/'missing.png'),'review_decision':'reject'})
        self.write()
        with self.assertRaises(FileNotFoundError):
            organizer.organize(self.review,self.root,True)
        self.assertTrue((self.root/'bad.png').exists())
        self.assertFalse((self.root/'Rejected').exists())

    def test_outside_traversal_duplicates_and_invalid_decisions(self):
        outside=self.base/'outside.png'
        outside.write_bytes(b'outside')
        variants=[
            {'path':str(outside),'review_decision':'reject'},
            {'path':str(self.root/'../outside.png'),'review_decision':'reject'},
            dict(self.entries[1]),
            {'path':str(self.root/'good.png'),'review_decision':'delete'},
            {'path':'bad.png','review_decision':'reject'},
        ]
        original=list(self.entries)
        for entry in variants:
            with self.subTest(entry=entry):
                self.entries=original+[entry];self.write()
                with self.assertRaises(ValueError):
                    organizer.organize(self.review,self.root,True)
                self.assertTrue((self.root/'bad.png').exists())
                self.assertFalse((self.root/'Rejected').exists())

    def test_nested_names_keep_distinct_destinations(self):
        sub=self.root/'night2'
        sub.mkdir()
        (sub/'bad.png').write_bytes(b'second')
        self.entries.append({'path':str(sub/'bad.png'),'review_decision':'reject'})
        self.write()
        organizer.organize(self.review,self.root,True)
        self.assertEqual((self.root/'Rejected/night2/bad.png').read_bytes(),b'second')
        self.assertEqual((self.root/'Rejected/bad.png').read_bytes(),b'pixels-bad.png')

    def test_copy_failure_keeps_original_and_removes_partial_copy(self):
        with patch.object(organizer.shutil,'copyfileobj',side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError,'disk full'):
                organizer.organize(self.review,self.root,True)
        self.assertEqual((self.root/'bad.png').read_bytes(),b'pixels-bad.png')
        self.assertFalse((self.root/'Rejected/bad.png').exists())
        log=next((self.root/'Rejected').glob('astro-moves-*.jsonl'))
        self.assertEqual(json.loads(log.read_text())['status'],'planned')

    def test_file_changed_after_plan_is_not_moved(self):
        _,moves=organizer.plan_moves(self.doc,self.root)
        source,destination,expected=moves[0]
        source.write_bytes(b'changed')
        destination.parent.mkdir()
        with self.assertRaisesRegex(ValueError,'changed'):
            organizer.move_no_replace(source,destination,expected)
        self.assertEqual(source.read_bytes(),b'changed')
        self.assertFalse(destination.exists())

    def test_destination_cannot_be_symlink(self):
        outside=self.base/'elsewhere';outside.mkdir()
        try:
            (self.root/'Rejected').symlink_to(outside,target_is_directory=True)
        except OSError:
            self.skipTest('Creating symlinks is not permitted on this Windows account')
        with self.assertRaises(ValueError):
            organizer.organize(self.review,self.root,True)
        self.assertEqual(list(outside.iterdir()),[])


if __name__=='__main__':
    unittest.main()
