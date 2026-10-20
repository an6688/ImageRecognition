"""Recorded vehicle tracking, separate from the photo library."""
import argparse
from datetime import datetime,timezone
import json
import hashlib
import importlib.metadata
import math
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import cv2
import numpy as np
from pets import OnnxPetDetector,ROOT

VEHICLES={2:'Car',3:'Motorcycle',5:'Bus',7:'Truck'}

def sampling(fps,target):
    if not math.isfinite(fps) or fps<=0:raise ValueError('Video has no usable frame rate.')
    if not math.isfinite(target) or target<=0:raise ValueError('Analysis rate must be positive.')
    stride=max(1,math.ceil(fps/target))
    return stride,fps/stride

def create_tracker(fps):
    import lap  # Fail explicitly instead of Ultralytics installing during a scan.
    from ultralytics.trackers.bot_sort import BOTSORT
    args=SimpleNamespace(track_high_thresh=.25,track_low_thresh=.1,new_track_thresh=.25,
        track_buffer=30,match_thresh=.8,fuse_score=True,gmc_method='sparseOptFlow',
        proximity_thresh=.5,appearance_thresh=.8,with_reid=False,model='auto')
    return BOTSORT(args,frame_rate=fps)

def restore_boxes(rows,shape,rotation):
    """Map boxes from a counterclockwise rotated detector view to original pixels."""
    out=rows.copy()
    if not len(out) or rotation==0:return out
    h,w=shape[:2];x1,y1,x2,y2=rows[:,:4].T
    if rotation==90:out[:,:4]=np.column_stack((w-y2,x1,w-y1,x2))
    elif rotation==180:out[:,:4]=np.column_stack((w-x2,h-y2,w-x1,h-y1))
    elif rotation==270:out[:,:4]=np.column_stack((y1,h-x2,y2,h-x1))
    else:raise ValueError('Rotation must be 0, 90, 180 or 270.')
    return out


def draw_tracks(frame,tracks,source_time,processing_fps,analysis_fps):
    for row in tracks:
        x1,y1,x2,y2,identity,confidence,kind=row[:7]
        identity=int(identity);color=((identity*67)%200+55,(identity*113)%200+55,(identity*37)%200+55)
        p1=(int(x1),int(y1));p2=(int(x2),int(y2))
        cv2.rectangle(frame,p1,p2,color,2)
        text=f'{VEHICLES.get(int(kind),"Vehicle")} #{identity} {confidence:.0%}'
        cv2.putText(frame,text,(p1[0],max(20,p1[1]-6)),cv2.FONT_HERSHEY_SIMPLEX,.55,color,2)
    cv2.rectangle(frame,(0,0),(frame.shape[1],64),(25,25,25),-1)
    cv2.putText(frame,f'{source_time:.1f}s | Processing {processing_fps:.1f} FPS',
        (12,25),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),2)
    cv2.putText(frame,f'Analysis {analysis_fps:g} FPS | ONNX + BoT-SORT',
        (12,51),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),1)
    return frame

def process_video(source,target_fps=10,cancel=None,preview=None,progress=print,rotation=0):
    """Process sampled frames in order. Each invocation owns a fresh tracker."""
    if rotation not in (0,90,180,270):raise ValueError('Unsupported detection rotation')
    source=Path(source).resolve();cancel=cancel or threading.Event()
    capture=cv2.VideoCapture(str(source));writer=None;run=None
    try:
        if not capture.isOpened():raise ValueError(f'Cannot open video: {source}')
        source_fps=capture.get(cv2.CAP_PROP_FPS)
        stride,analysis_fps=sampling(source_fps,target_fps)
        total=int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        detector=OnnxPetDetector(progress)
        tracker=create_tracker(analysis_fps)
        model_path=ROOT/'models'/'yolo11m.onnx'
        model_hash=None
        if model_path.is_file():
            with model_path.open('rb') as model_file:model_hash=hashlib.file_digest(model_file,'sha256').hexdigest()
        from ultralytics.engine.results import Boxes
        run=ROOT/'data'/'videos'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        run.mkdir(parents=True)
        index=0;processed=0;ids=set();first_shape=None;last_source_time=0
        inference_seconds=0;tracking_seconds=0;started=time.perf_counter()
        with (run/'tracks.jsonl').open('w',encoding='utf-8') as records:
            while not cancel.is_set() and capture.grab():
                current=index;index+=1
                if current%stride:continue
                ok,frame=capture.retrieve()
                if not ok:raise ValueError(f'Could not decode frame {current}')
                if writer is None:
                    h,w=frame.shape[:2];first_shape=(h,w)
                    writer=cv2.VideoWriter(str(run/'annotated.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),analysis_fps,(w,h))
                    if not writer.isOpened():raise RuntimeError('Could not create the annotated MP4.')
                if frame.shape[:2]!=first_shape:raise ValueError('Frame dimensions changed during the video.')
                tick=time.perf_counter()
                rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
                rotated=np.ascontiguousarray(np.rot90(rgb,rotation//90))
                detections=restore_boxes(detector.detect_rgb(rotated,list(VEHICLES),confidence=.1),frame.shape,rotation)
                inferred=time.perf_counter();inference_seconds+=inferred-tick
                tracks=tracker.update(Boxes(detections,frame.shape[:2]),frame)
                tracking_seconds+=time.perf_counter()-inferred
                processed+=1;last_source_time=current/source_fps
                ids.update(int(row[4]) for row in tracks)
                records.write(json.dumps(dict(frame=current,seconds=last_source_time,tracks=tracks.tolist()))+'\n')
                speed=processed/(time.perf_counter()-started)
                draw_tracks(frame,tracks,last_source_time,speed,analysis_fps)
                writer.write(frame)
                if preview:preview(frame,dict(processed=processed,source_seconds=last_source_time,
                    total_seconds=total/source_fps if total>0 else None,processing_fps=speed,analysis_fps=analysis_fps))
                if processed%30==0:progress(f'{last_source_time:.1f}s analyzed | {speed:.1f} processing FPS')
        elapsed=time.perf_counter()-started
        if processed==0 and not cancel.is_set():raise ValueError('Video contains no decodable frames.')
        if total>0 and index<total-1 and not cancel.is_set():raise ValueError(f'Video ended early at frame {index} of {total}')
        summary=dict(source=str(source),source_fps=source_fps,source_frames_reported=total,
            analysis_fps=analysis_fps,stride=stride,processed_frames=processed,cancelled=cancel.is_set(),
            elapsed_seconds=elapsed,processing_fps=processed/elapsed if elapsed else 0,
            inference_seconds=inference_seconds,tracking_seconds=tracking_seconds,track_ids_seen=len(ids),
            tracker='BoT-SORT',camera_motion='sparseOptFlow',reidentification=False,
            model='yolo11m.onnx',model_sha256=model_hash,
            packages={p:importlib.metadata.version(p) for p in ('onnxruntime','ultralytics','lap')},
            detection_rotation_ccw=rotation,classes=VEHICLES,detector_confidence=.1,new_track_confidence=.25,
            note='Track IDs are clip-local, not identities or a reliable unique-vehicle count. Accuracy is not yet labeled. Timing excludes model initialization; includes decoding, drawing, output and preview callbacks.')
        (run/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        progress(f'{"Stopped" if cancel.is_set() else "Finished"}: {processed} frames; {summary["processing_fps"]:.1f} processing FPS')
        return run
    except Exception as exc:
        if run is not None:(run/'error.txt').write_text(f'Incomplete run: {exc}',encoding='utf-8')
        raise
    finally:
        capture.release()
        if writer is not None:writer.release()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video',type=Path);parser.add_argument('--analysis-fps',type=float,default=10)
    parser.add_argument('--rotation',type=int,choices=[0,90,180,270],default=0,help='Rotate detector input counterclockwise; output stays upright')
    args=parser.parse_args()
    print('OUTPUT_DIRECTORY='+str(process_video(args.video,args.analysis_fps,rotation=args.rotation)))
