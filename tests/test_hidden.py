import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
import numpy as np
from PIL import Image
from core import Store, Indexer, choose_group
import app

class HiddenTests(unittest.TestCase):
    def test_hide_rescan_future_import_restore_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            photos=folder/'photos'; photos.mkdir()
            Image.new('RGB',(100,100),'red').save(photos/'first.png')
            indexer=Indexer.__new__(Indexer)
            indexer.store=Store(folder/'data')
            feature=np.array([1,0],dtype=np.float32)
            indexer.extract=lambda _: [(feature,Image.new('RGB',(112,112)))]
            try:
                indexer.scan(photos,lambda _:None,threading.Event())
                person=indexer.store.people()[0]['id']
                indexer.store.rename(person,'Bob')
                indexer.store.set_hidden(person,True)
                self.assertEqual(indexer.store.people(),[])
                self.assertEqual(indexer.store.people(hidden=True)[0]['name'],'Bob')
                indexer.store.close(); indexer.store=Store(folder/'data')
                self.assertEqual(indexer.store.people(),[])
                # Simulate the subject refresh removing every old face.
                with indexer.store.db: indexer.store.db.execute('DELETE FROM faces')
                self.assertEqual(choose_group(feature,indexer.store.prototypes()),person)
                self.assertEqual(indexer.store.people(hidden=True)[0]['count'],0)
                Image.new('RGB',(100,100),'blue').save(photos/'second.png')
                result=indexer.scan(photos,lambda _:None,threading.Event())
                self.assertEqual(result['errors'],[])
                self.assertEqual(indexer.store.people(),[])
                self.assertEqual(indexer.store.people(hidden=True)[0]['count'],1)
                indexer.store.set_hidden(person,False)
                self.assertEqual(indexer.store.people()[0]['name'],'Bob')
                self.assertEqual(indexer.store.people(hidden=True),[])
            finally: indexer.store.close()

    def test_desktop_hide_restore_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(app,'Store',lambda:Store(directory)):
                root=tk.Tk(); instance=app.App(root)
                try:
                    with instance.store.db:
                        instance.store.db.execute("INSERT INTO people(id,name) VALUES(1,'Bob')")
                        instance.store.db.execute("INSERT INTO photos(id,path,digest,size,modified) VALUES(1,'photo.jpg','hash',1,1)")
                        instance.store.db.execute('INSERT INTO faces(photo_id,person_id,embedding,thumb) VALUES(1,1,?,?)',(np.array([1,0],dtype=np.float32).tobytes(),'missing.jpg'))
                    instance.render(); root.update()
                    instance.hide_person(1); root.update()
                    self.assertEqual(instance.store.people(),[])
                    instance.toggle_hidden(); root.update()
                    self.assertEqual(instance.heading.cget('text'),'Hidden people')
                    self.assertEqual(len(instance.images),1)
                    instance.hide_person(1,False); root.update()
                    instance.toggle_hidden(); root.update()
                    self.assertEqual(len(instance.images),1)
                    instance.busy=True
                    instance.hide_person(1)
                    self.assertEqual(len(instance.store.people()),1)
                    instance.busy=False
                finally: instance.close()

if __name__=='__main__': unittest.main()
