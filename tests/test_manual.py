import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk
import numpy as np
from PIL import Image
from core import Store, Indexer
import app
import editor

class ManualTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.folder=Path(self.temp.name)
        self.photos=self.folder/'photos'; self.photos.mkdir()
        self.path=self.photos/'one.png'
        Image.new('RGB',(400,300),'white').save(self.path)
        self.store=Store(self.folder/'data')
        self.indexer=Indexer.__new__(Indexer); self.indexer.store=self.store
        self.feature=np.array([1,0],dtype=np.float32)
        self.crop=Image.new('RGB',(112,112))
        self.indexer.extract=lambda _: [(self.feature,self.crop)]
        self.indexer.scan(self.photos,lambda _:None,threading.Event())
        self.photo=self.store.all_photos()[0]['id']

    def tearDown(self):
        self.store.close(); self.temp.cleanup()

    def test_second_person_survives_rescan_and_duplicate_click(self):
        mom=self.store.save_selection(self.photo,[20,20,40,40],np.array([0,1]),self.crop,name='Mom')
        self.store.save_selection(self.photo,[21,21,40,40],np.array([0,1]),self.crop,person=mom)
        self.assertEqual(self.store.counts(),(1,2))
        with self.store.db:self.store.db.execute('UPDATE photos SET selection_version=0')
        result=self.indexer.refresh_library(lambda _:None,threading.Event())
        self.assertEqual(result['errors'],[])
        self.assertEqual(self.store.counts(),(1,2))
        self.assertEqual(len(self.store.photos(mom)),1)
        self.assertEqual(self.store.summary()['with_faces'],1)

    def test_select_existing_auto_face_updates_not_duplicates(self):
        mom=self.store.save_selection(self.photo,[20,20,40,40],self.feature,self.crop,name='Mom')
        self.assertEqual(self.store.counts(),(1,1))
        with self.store.db:self.store.db.execute('UPDATE photos SET selection_version=0')
        self.indexer.refresh_library(lambda _:None,threading.Event())
        self.assertEqual(self.store.counts(),(1,1))
        self.assertEqual(self.store.people()[0]['id'],mom)

    def test_undetected_manual_tag_and_empty_named_group(self):
        with self.store.db:
            mom=self.store.db.execute("INSERT INTO people(name) VALUES('Mom')").lastrowid
        self.assertIn(mom,[r['id'] for r in self.store.people()])
        self.store.save_selection(self.photo,[100,20,40,40],np.array([]),self.crop,person=mom)
        self.assertEqual(len(self.store.photos(mom)),1)
        self.assertNotIn(mom,[p for p,_ in self.store.prototypes()])

    def test_changed_original_keeps_manual_selection_and_reports_error(self):
        self.store.save_selection(self.photo,[20,20,40,40],self.feature,self.crop,name='Mom')
        Image.new('RGB',(401,300),'blue').save(self.path)
        result=self.indexer.scan(self.photos,lambda _:None,threading.Event())
        self.assertEqual(len(result['errors']),1)
        self.assertEqual(self.store.counts(),(1,1))

    def test_summary_counts_photos_separately_from_appearances(self):
        with self.store.db:self.store.db.execute("INSERT INTO photos(path,digest,size,modified) VALUES('missing','b',1,1)")
        mom=self.store.save_selection(self.photo,[100,20,40,40],np.array([0,1]),self.crop,name='Mom')
        self.store.set_hidden(mom,True)
        self.assertEqual(self.store.summary(),dict(total=2,with_faces=1,without_faces=1,visible_faces=1,hidden_faces=1))

    def test_editor_click_draw_save_and_all_photos(self):
        with patch.object(app,'Store',lambda:self.store):
            root=tk.Tk(); ui=app.App(root)
            class FakeIndexer:
                def __init__(self,**kw):self.store=SimpleNamespace(close=lambda:None)
                def inspect_photo(self,path):return Image.new('RGB',(400,300)),[([20,20,40,40],np.array([1,0],dtype=np.float32),Image.new('RGB',(112,112)))]
                def describe_region(self,image,box):return np.array([],dtype=np.float32),image.crop((box[0],box[1],box[0]+box[2],box[1]+box[3]))
            try:
                ui.show_all(); root.update()
                self.assertEqual(ui.heading.cget('text'),'All photos')
                with patch.object(editor,'Indexer',FakeIndexer):
                    view=editor.FaceEditor(ui,self.photo,str(self.path))
                    root.update(); view.load()
                    view.press(SimpleNamespace(x=30,y=30)); view.release(SimpleNamespace(x=30,y=30))
                    self.assertEqual(list(view.selection[1]),[1,0])
                    view.press(SimpleNamespace(x=100,y=100)); view.drag(SimpleNamespace(x=150,y=150)); view.release(SimpleNamespace(x=150,y=150))
                    self.assertEqual(view.selection[0],[100,100,50,50])
                    view.name.insert(0,'Mom'); view.save(); root.update()
                    self.assertEqual(self.store.counts(),(1,2))
            finally:
                root.after_cancel(ui.poll_timer)
                ui.video.dispose();root.destroy()

if __name__=='__main__':unittest.main()
