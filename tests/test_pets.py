import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
import numpy as np
from PIL import Image
from core import Store
from pets import decode_detections,scan_pets
import app

class PetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.photo=self.folder/'pets.png';Image.new('RGB',(100,100)).save(self.photo)
        self.store=Store(self.folder/'data')
        digest=hashlib.sha256(self.photo.read_bytes()).hexdigest()
        with self.store.db:self.store.db.execute('INSERT INTO photos(id,path,digest,size,modified) VALUES(1,?,?,1,1)',(str(self.photo),digest))

    def tearDown(self):self.store.close();self.temp.cleanup()

    def factory(self,progress):
        class Detector:
            def detect(self,path):return [('cat',.9,[.1,.1,.3,.3]),('dog',.8,[.5,.1,.3,.3]),('dog',.7,[.5,.5,.3,.3])]
        return Detector()

    def test_backend_switch_rescans_and_preserves_rejections(self):
        scan_pets(self.store,lambda _:None,threading.Event(),self.factory)
        self.store.reject_pet(1,'cat')
        result=scan_pets(self.store,lambda _:None,threading.Event(),self.factory,backend='ONNX')
        self.assertEqual(result['processed'],1)
        self.assertEqual(self.store.pet_counts(),{'cat':0,'dog':1})
        scan_pets(self.store,lambda _:None,threading.Event(),lambda _:self.fail('cached'),backend='ONNX')
        self.assertEqual(scan_pets(self.store,lambda _:None,threading.Event(),self.factory)['processed'],1)
        self.assertEqual(self.store.rejected_pets(1),['cat'])

    def test_backend_initialization_failure_keeps_previous_results(self):
        scan_pets(self.store,lambda _:None,threading.Event(),self.factory)
        before=[tuple(r) for r in self.store.pet_detections(1)]
        with self.assertRaisesRegex(RuntimeError,'missing'):
            scan_pets(self.store,lambda _:None,threading.Event(),
                lambda _:(_ for _ in ()).throw(RuntimeError('missing')),backend='ONNX')
        self.assertEqual(before,[tuple(r) for r in self.store.pet_detections(1)])
        self.assertEqual(scan_pets(self.store,lambda _:None,threading.Event(),self.factory,backend='ONNX')['processed'],1)

    def test_backend_selector_persists_and_is_captured_by_worker(self):
        from pets import load_backend
        folder=self.store.folder
        with patch.object(app,'Store',lambda *args:Store(folder)):
            root=tk.Tk();ui=app.App(root)
            try:
                self.assertEqual(ui.pet_backend.get(),'PyTorch')
                ui.pet_backend.set('ONNX');ui.change_pet_backend()
                self.assertEqual(load_backend(folder),'ONNX')
                with patch('pets.scan_pets',return_value=dict(processed=0,errors=[],cancelled=False)) as scan:
                    ui.start_scan(pets_only=True);ui.worker.join(timeout=5)
                    self.assertFalse(ui.worker.is_alive())
                    self.assertEqual(scan.call_args.kwargs['backend'],'ONNX')
                    self.assertEqual(str(ui.pet_engine['state']),'disabled')
                    root.after_cancel(ui.poll_timer)
                    ui.poll()
                    self.assertEqual(str(ui.pet_engine['state']),'readonly')
            finally:
                ui.busy=False;ui.close()

    def test_filter_confidence_species_and_invalid_boxes(self):
        data=np.array([[-.1,0,.5,1,.9,15],[0,0,1,1,.3,16],[0,0,1,1,.99,0],[.8,0,.2,1,.8,16]])
        detections=decode_detections(data)
        self.assertEqual(len(detections),1);self.assertEqual(detections[0][0],'cat')
        self.assertEqual(detections[0][2],[0,0,.5,1])

    def test_galleries_count_photos_and_repeat_skips(self):
        result=scan_pets(self.store,lambda _:None,threading.Event(),self.factory)
        self.assertEqual(result['detections'],3)
        self.assertEqual(self.store.pet_counts(),{'cat':1,'dog':1})
        self.assertEqual(len(self.store.pet_photos('dog')),1)
        result=scan_pets(self.store,lambda _:None,threading.Event(),lambda _:self.fail('should not load model'))
        self.assertEqual(result['processed'],0)
        self.assertEqual(self.store.counts(),(1,0))
        self.store.close();self.store=Store(self.folder/'data')
        self.assertEqual(self.store.pet_counts()['cat'],1)

    def test_model_upgrade_rechecks_old_results_without_duplicates(self):
        scan_pets(self.store,lambda _:None,threading.Event(),self.factory)
        with self.store.db:self.store.db.execute("UPDATE pet_scans SET version='mobilenet-ssd-voc-1-conf50'")
        result=scan_pets(self.store,lambda _:None,threading.Event(),self.factory)
        self.assertEqual(result['processed'],1)
        self.assertEqual(len(self.store.pet_detections(1)),3)
        self.assertEqual(self.store.pet_counts(),{'cat':1,'dog':1})

    def test_rejection_survives_restart_and_model_upgrade_and_can_undo(self):
        scan_pets(self.store,lambda _:None,threading.Event(),self.factory)
        self.store.reject_pet(1,'cat')
        self.assertEqual(self.store.pet_counts(),{'cat':0,'dog':1})
        self.assertEqual(self.store.pet_photos('cat'),[])
        self.assertEqual({r['species'] for r in self.store.pet_detections(1)},{'dog'})
        self.store.close();self.store=Store(self.folder/'data')
        self.assertEqual(self.store.rejected_pets(1),['cat'])
        with self.store.db:self.store.db.execute("UPDATE pet_scans SET version='old-model'")
        scan_pets(self.store,lambda _:None,threading.Event(),self.factory)
        self.assertEqual(self.store.pet_counts(),{'cat':0,'dog':1})
        self.store.reject_pet(1,'cat',False)
        self.assertEqual(self.store.pet_counts(),{'cat':1,'dog':1})
        self.assertEqual(len(self.store.pet_detections(1)),3)

    def test_rejection_is_specific_to_photo_content_and_valid_species(self):
        scan_pets(self.store,lambda _:None,threading.Event(),self.factory)
        with self.assertRaises(ValueError):self.store.reject_pet(1,'bear')
        with self.assertRaises(ValueError):self.store.reject_pet(999,'cat')
        self.store.reject_pet(1,'cat')
        with self.store.db:self.store.db.execute("UPDATE photos SET digest='new-content' WHERE id=1")
        self.assertEqual(self.store.rejected_pets(1),[])

    def test_cancel_and_failed_files_are_retryable(self):
        cancel=threading.Event();cancel.set()
        self.assertTrue(scan_pets(self.store,lambda _:None,cancel,self.factory)['cancelled'])
        self.photo.unlink()
        result=scan_pets(self.store,lambda _:None,threading.Event(),self.factory)
        self.assertEqual(len(result['errors']),1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM pet_scans').fetchone()[0],0)

    def test_pet_only_scan_does_not_load_face_models(self):
        folder=self.store.folder
        with patch.object(app,'Store',lambda *args:Store(folder)):
            root=tk.Tk();ui=app.App(root)
            try:
                with patch.object(app,'Indexer',side_effect=AssertionError('Face models must not load')), patch('pets.scan_pets',return_value=dict(processed=1,errors=[],cancelled=False)) as scan:
                    ui.start_scan(pets_only=True)
                    ui.worker.join(timeout=5)
                    self.assertFalse(ui.worker.is_alive())
                    scan.assert_called_once()
                    kind,result=ui.events.get_nowait()
                    self.assertEqual(kind,'done')
                    self.assertEqual(result['pet_photos'],1)
                    self.assertEqual(result['errors'],[])
            finally:
                ui.busy=False
                ui.close()

    def test_navigation_returns_to_people(self):
        scan_pets(self.store,lambda _:None,threading.Event(),self.factory)
        with patch.object(app,'Store',lambda:self.store):
            root=tk.Tk();ui=app.App(root)
            try:
                ui.cat_button.invoke();root.update()
                self.assertEqual(ui.heading.cget('text'),'Cats');self.assertEqual(len(ui.images),1)
                ui.dog_button.invoke();root.update()
                self.assertEqual(ui.heading.cget('text'),'Dogs');self.assertEqual(len(ui.images),1)
                ui.back.invoke();root.update()
                self.assertEqual(ui.heading.cget('text'),'People');self.assertIsNone(ui.pet_kind)
            finally:
                root.after_cancel(ui.poll_timer);root.destroy()

if __name__=='__main__':unittest.main()
