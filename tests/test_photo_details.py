import tempfile
import unittest
from pathlib import Path
from PIL import Image
import numpy as np
from core import Store

class PhotoDetailTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.folder=Path(self.temp.name)
        self.store=Store(self.folder)
        with self.store.db:
            self.store.db.execute("INSERT INTO photos(id,path,digest,size,modified) VALUES(1,'a.jpg','a',1,1)")
        self.ani=self.store.save_selection(1,[0,0,30,30],np.array([1,0]),Image.new('RGB',(30,30),'red'),name='Ani')
        self.mom=self.store.save_selection(1,[50,0,30,30],np.array([0,1]),Image.new('RGB',(30,30),'blue'),name='Mom')

    def tearDown(self):
        self.store.close(); self.temp.cleanup()

    def test_labels_show_every_person_and_follow_renames_and_hiding(self):
        self.assertEqual(self.store.photo_labels(1),['Ani','Mom'])
        self.store.rename(self.mom,'Mother')
        self.store.set_hidden(self.mom,True)
        self.assertEqual(self.store.photo_labels(1),['Ani','Mother (hidden)'])
        self.store.rename(self.ani,'')
        self.assertEqual(self.store.photo_labels(1)[0],f'Person {self.ani}')
        self.assertEqual(self.store.photo_labels(999),[])

    def test_cover_is_independent_and_persists(self):
        face=self.store.assignments(1)[0]
        self.store.set_cover(self.ani,face['id'])
        selected=self.store.people()[0]['thumb']
        original=(self.store.thumbs/selected).read_bytes()
        Image.new('RGB',(30,30),'green').save(self.store.thumbs/face['thumb'])
        self.store.close(); self.store=Store(self.folder)
        self.assertEqual(self.store.people()[0]['thumb'],selected)
        self.assertEqual((self.store.thumbs/selected).read_bytes(),original)
        with self.assertRaises(ValueError):self.store.set_cover(self.mom,face['id'])
        with self.store.db:self.store.db.execute('DELETE FROM faces WHERE id=?',(face['id'],))
        ani=next(p for p in self.store.people() if p['id']==self.ani)
        self.assertEqual(ani['thumb'],selected)

if __name__=='__main__':unittest.main()
