import tempfile
import threading
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from core import Store, Indexer, choose_group

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'data')

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def seed(self, person, photo, feature):
        with self.store.db:
            self.store.db.execute('INSERT OR IGNORE INTO people(id) VALUES(?)', (person,))
            self.store.db.execute('INSERT OR IGNORE INTO photos(id,path,digest,size,modified) VALUES(?,?,?,?,?)', (photo, f'{photo}.jpg', str(photo), 1, 1))
            return self.store.db.execute('INSERT INTO faces(photo_id,person_id,embedding,thumb) VALUES(?,?,?,?)', (photo, person, np.array(feature,dtype=np.float32).tobytes(), 'face.jpg')).lastrowid

    def test_matching_rejects_different_faces_and_same_photo_group(self):
        examples = [(1, np.array([[1,0]], dtype=np.float32))]
        self.assertEqual(choose_group(np.array([1,0]), examples), 1)
        self.assertIsNone(choose_group(np.array([0,1]), examples))
        self.assertIsNone(choose_group(np.array([1,0]), examples, {1}))

    def test_merge_counts_unique_photos_and_persists_name(self):
        self.seed(1,1,[1,0]); self.seed(2,1,[0,1]); self.seed(2,2,[0,1])
        self.store.rename(1,'Bob')
        self.store.merge(2,1)
        rows = self.store.people()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['count'],2)
        self.store.close()
        self.store = Store(Path(self.temp.name) / 'data')
        self.assertEqual(self.store.people()[0]['name'],'Bob')

    def test_separate_moves_only_selected_face(self):
        face = self.seed(1,1,[1,0]); self.seed(1,2,[1,0])
        other = self.store.separate(face)
        self.assertNotEqual(other,1)
        self.assertEqual(len(self.store.photos(1)),1)
        self.assertEqual(len(self.store.photos(other)),1)

    def test_bad_merge_target_does_not_change_library(self):
        self.seed(1,1,[1,0])
        with self.assertRaises(ValueError): self.store.merge(1,999)
        self.assertEqual(self.store.people()[0]['id'],1)

    def test_import_repeat_duplicate_corrupt_and_cancel(self):
        photos = Path(self.temp.name) / 'photos'
        photos.mkdir()
        Image.new('RGB',(80,80),'white').save(photos/'one.png')
        (photos/'copy.png').write_bytes((photos/'one.png').read_bytes())
        (photos/'bad.jpg').write_bytes(b'not an image')
        indexer = Indexer.__new__(Indexer)
        indexer.store = self.store
        def extract(path):
            with Image.open(path) as image: image.load()
            return [(np.array([1,0],dtype=np.float32), Image.new('RGB',(112,112)))]
        indexer.extract = extract
        result = indexer.scan(photos, lambda _: None, threading.Event())
        self.assertEqual(result['imported'],1)
        self.assertEqual(result['skipped'],1)
        self.assertEqual(len(result['errors']),1)
        self.assertEqual(self.store.counts(),(1,1))
        self.store.rename(self.store.people()[0]['id'],'Bob')
        result = indexer.scan(photos, lambda _: None, threading.Event())
        self.assertEqual(result['imported'],0)
        self.assertEqual(result['skipped'],2)
        self.assertEqual(self.store.people()[0]['name'],'Bob')
        stop = threading.Event(); stop.set()
        self.assertTrue(indexer.scan(photos, lambda _: None, stop)['cancelled'])

if __name__ == '__main__': unittest.main()
