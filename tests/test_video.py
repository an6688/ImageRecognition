import unittest
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
import video_tracking as video

class VideoTests(unittest.TestCase):
    def test_pause_can_resume_or_cancel_without_changing_selection(self):
        import time
        control=video.TrackingControl();cancel=threading.Event()
        control.select(12);control.paused.set()
        results=[];thread=threading.Thread(target=lambda:results.append(control.wait(cancel)))
        thread.start();time.sleep(.06);self.assertTrue(thread.is_alive())
        control.paused.clear();thread.join(timeout=1)
        self.assertFalse(thread.is_alive());self.assertGreater(results[0],.04)
        control.paused.set();cancel.set();control.wait(cancel)
        self.assertEqual(control.selection(),12)

    def test_click_maps_letterboxed_preview_and_retains_lost_id(self):
        import tkinter as tk
        from types import SimpleNamespace
        from video_app import VideoApp
        root=tk.Tk();root.geometry('850x900');ui=VideoApp(root)
        try:
            root.update()
            ui.latest=(np.zeros((400,200,3),dtype=np.uint8),{'source_shape':(800,400),'subject':'Dogs',
                'tracks':[[100,200,200,400,7,.9,16,0],[120,220,160,300,9,.8,16,1]]})
            ui.render();ox,oy,sx,sy=ui.mapping
            ui.click(SimpleNamespace(x=ox+140*sx,y=oy+250*sy))
            self.assertEqual(ui.control.selection(),9)  # smallest overlapping box
            ui.click(SimpleNamespace(x=0,y=0))
            self.assertEqual(ui.control.selection(),9)  # background does not retarget
            ui.latest=(ui.latest[0],{'source_shape':(800,400),'tracks':[]})
            ui.render();self.assertIn('lost',ui.selection['text'])
            self.assertEqual(ui.control.selection(),9)
            ui.select(None);self.assertIsNone(ui.control.selection())
        finally:ui.dispose();root.destroy()

    def test_main_app_embeds_photo_video_and_astro_workspaces(self):
        import tkinter as tk
        import app
        from core import Store
        with tempfile.TemporaryDirectory() as folder,patch.object(app,'Store',lambda:Store(folder)),patch('astro.desktop.load_state',return_value={}):
            root=tk.Tk();ui=app.App(root)
            try:
                self.assertEqual([ui.tabs.tab(t,'text') for t in ui.tabs.tabs()],['Photos','Videos','AstroTrack'])
                self.assertIs(ui.video.root,ui.video_page)
                ui.tabs.select(ui.video_page);root.update()
                self.assertTrue(ui.video.picture.winfo_ismapped())
                self.assertIs(ui.astro.parent,ui.astro_page)
                self.assertIsNone(ui.astro.session.server)
                ui.tabs.select(ui.astro_page);root.update()
                self.assertTrue(ui.astro.open_button.winfo_ismapped())
                self.assertTrue(ui.astro.activated)
                self.assertIsNone(ui.astro.session.server)

            finally:ui.close()

    def test_subject_filter_and_selected_id_reach_output(self):
        import json
        seen=[]
        class Detector:
            def __init__(self,*args):pass
            def detect_rgb(self,image,classes,**kwargs):
                seen.append(classes)
                return np.array([[10,10,40,40,.9,classes[0]]],dtype=np.float32)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'input.avi'
            writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'MJPG'),10,(64,64))
            for _ in range(3):writer.write(np.zeros((64,64,3),dtype=np.uint8))
            writer.release()
            for subject,classes in video.SUBJECTS.items():
                seen.clear();control=video.TrackingControl()
                def preview(frame,info):
                    self.assertEqual(info['subject'],subject)
                    if info['tracks']:control.select(int(info['tracks'][0][4]))
                with patch.object(video,'ROOT',root),patch.object(video,'OnnxPetDetector',Detector):
                    run=video.process_video(source,subject=subject,control=control,preview=preview,progress=lambda _:None)
                self.assertEqual(seen,[list(classes)]*3)
                rows=[json.loads(line) for line in (run/'tracks.jsonl').read_text().splitlines()]
                self.assertIsNone(rows[0]['selected_track_id'])
                self.assertEqual(rows[1]['selected_track_id'],1)
                summary=json.loads((run/'summary.json').read_text())
                self.assertEqual(summary['subject'],subject)
                self.assertEqual(summary['classes'],{str(k):v for k,v in classes.items()})

    def test_rotated_boxes_return_to_original_coordinates(self):
        expected=np.array([[10,20,40,60,.8,2]],dtype=np.float32)
        for rotation,coords in [(0,[10,20,40,60]),(90,[20,60,60,90]),
                                (180,[60,20,90,60]),(270,[20,10,60,40])]:
            rows=np.array([[*coords,.8,2]],dtype=np.float32)
            np.testing.assert_allclose(video.restore_boxes(rows,(80,100),rotation),expected)
        self.assertEqual(video.restore_boxes(np.empty((0,6)),(80,100),90).shape,(0,6))

    def test_preview_window_processes_worker_events(self):
        import tkinter as tk
        import time
        import video_app
        root=tk.Tk();root.withdraw();ui=video_app.VideoApp(root)
        def run(source,**kwargs):
            kwargs['preview'](np.zeros((100,100,3),dtype=np.uint8),{})
            kwargs['progress']('Preview test')
            return Path('test-output')
        try:
            with patch.object(video_app.filedialog,'askopenfilename',return_value='test.mp4'),patch.object(video_app,'process_video',side_effect=run) as worker:
                ui.start();ui.worker.join(timeout=3)
                self.assertFalse(ui.worker.is_alive())
                root.after_cancel(ui.timer);ui.poll()
                self.assertEqual(ui.output,'test-output')
                self.assertEqual(str(ui.open['state']),'normal')
                self.assertEqual(worker.call_args.kwargs['rotation'],0)
                self.assertTrue(hasattr(ui,'image'))
        finally:
            root.after_cancel(ui.timer);root.destroy()

    def test_sampling_preserves_source_time(self):
        self.assertEqual(video.sampling(60,10),(6,10))
        self.assertEqual(video.sampling(5,10),(1,5))
        self.assertLessEqual(video.sampling(29.97,10)[1],10)
        for fps in (0,float('nan')):
            with self.assertRaises(ValueError):video.sampling(fps,10)

    def test_tracker_retains_id_and_fresh_session_resets(self):
        # Configure Ultralytics locally before importing trackers.
        import os
        os.environ['YOLO_CONFIG_DIR']=str(video.ROOT/'data'/'yolo-config')
        from ultralytics.engine.results import Boxes
        frame=np.zeros((100,100,3),dtype=np.uint8)
        def boxes(x):return Boxes(np.array([[x,10,x+20,30,.9,2]],dtype=np.float32),(100,100))
        tracker=video.create_tracker(10)
        first=tracker.update(boxes(10),frame)
        second=tracker.update(boxes(12),frame)
        self.assertEqual(int(first[0,4]),int(second[0,4]))
        tracker.update(Boxes(np.empty((0,6),dtype=np.float32),(100,100)),frame)
        recovered=tracker.update(boxes(14),frame)
        self.assertEqual(int(first[0,4]),int(recovered[0,4]))
        fresh=video.create_tracker(10).update(boxes(10),frame)
        self.assertEqual(int(fresh[0,4]),1)

    def test_pipeline_output_duration_and_cancellation(self):
        import json
        class Detector:
            def __init__(self,*args):pass
            def detect_rgb(self,*args,**kwargs):return np.empty((0,6),dtype=np.float32)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'input.avi'
            writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'MJPG'),30,(64,64))
            for _ in range(30):writer.write(np.zeros((64,64,3),dtype=np.uint8))
            writer.release();original=source.read_bytes()
            with patch.object(video,'ROOT',root),patch.object(video,'OnnxPetDetector',Detector):
                result=video.process_video(source,progress=lambda _:None)
                summary=json.loads((result/'summary.json').read_text())
                self.assertEqual(summary['processed_frames'],10)
                self.assertFalse(summary['cancelled'])
                output=cv2.VideoCapture(str(result/'annotated.mp4'))
                self.assertEqual(int(output.get(cv2.CAP_PROP_FRAME_COUNT)),10)
                self.assertEqual(output.get(cv2.CAP_PROP_FPS),10);output.release()
                stop=threading.Event()
                result=video.process_video(source,cancel=stop,preview=lambda *_:stop.set(),progress=lambda _:None)
                summary=json.loads((result/'summary.json').read_text())
                self.assertTrue(summary['cancelled']);self.assertEqual(summary['processed_frames'],1)
            self.assertEqual(source.read_bytes(),original)

if __name__=='__main__':unittest.main()
