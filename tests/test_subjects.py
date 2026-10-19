import tempfile
import threading
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from core import Indexer, Store, select_main_face

class SubjectTests(unittest.TestCase):
    def test_foreground_beats_centered_bystander(self):
        subject = [50, 150, 240, 260]
        background = [480, 480, 45, 50]
        self.assertEqual(select_main_face([background, subject],1000,1000),[subject])

    def test_center_breaks_equal_size_tie(self):
        edge = [0,0,100,100]
        center = [450,450,100,100]
        self.assertEqual(select_main_face([edge,center],1000,1000),[center])

    def test_empty_and_tiny_faces(self):
        self.assertEqual(select_main_face(None,1000,1000),[])
        self.assertEqual(select_main_face([],1000,1000),[])
        self.assertEqual(select_main_face([[450,450,30,30]],1000,1000),[])

    def test_group_photo_keeps_only_one(self):
        self.assertEqual(len(select_main_face([[100,100,100,100],[300,100,100,100]],1000,1000)),1)

    def test_refresh_preserves_name_assignment_backup_and_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            photos = folder/'photos'; photos.mkdir()
            Image.new('RGB',(200,200),'white').save(photos/'one.png')
            indexer = Indexer.__new__(Indexer)
            indexer.store = Store(folder/'data')
            crop = Image.new('RGB',(112,112))
            subject = np.array([1,0],dtype=np.float32)
            bystander = np.array([0,1],dtype=np.float32)
            indexer.extract = lambda _: [(bystander,crop),(subject,crop)]
            try:
                indexer.scan(photos,lambda _:None,threading.Event())
                db=indexer.store.db
                subject_id=db.execute('SELECT person_id FROM faces ORDER BY id DESC LIMIT 1').fetchone()[0]
                indexer.store.rename(subject_id,'My name')
                with db: db.execute('UPDATE photos SET selection_version=0')
                indexer.extract = lambda _: [(subject,crop)]
                result=indexer.refresh_library(lambda _:None,threading.Event())
                self.assertEqual(result['errors'],[])
                self.assertEqual(result['imported'],1)
                self.assertEqual(indexer.store.counts(),(1,1))
                person=indexer.store.people()[0]
                self.assertEqual(person['id'],subject_id)
                self.assertEqual(person['name'],'My name')
                self.assertTrue(list((folder/'data').glob('before-subject-filter-*.sqlite')))
                result=indexer.refresh_library(lambda _:None,threading.Event())
                self.assertEqual(result['skipped'],1)
                self.assertEqual(result['imported'],0)
            finally: indexer.store.close()

if __name__ == '__main__': unittest.main()
