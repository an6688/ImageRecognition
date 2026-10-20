"""Local cat/dog detection with YOLO11 Medium and aspect-preserving input."""
from pathlib import Path
import hashlib
import json
import os
import urllib.request
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
VERSION = 'yolo11m-640-conf50-v1'
MODEL_NAME = 'yolo11m.pt'
MODEL_SHA256 = 'd5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95'
MODEL_URL = 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt'
CLASSES = {15: 'cat', 16: 'dog'}


def prepare_pet_model(progress=lambda _: None):
    folder=ROOT/'models'
    folder.mkdir(exist_ok=True)
    target=folder/MODEL_NAME
    def verified(path):
        if not path.is_file(): return False
        with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()==MODEL_SHA256
    if verified(target):return folder
    progress('Downloading upgraded cat/dog model (first run only)…')
    temporary=target.with_suffix('.download')
    try:
        with urllib.request.urlopen(MODEL_URL,timeout=60) as response,temporary.open('wb') as output:
            while block:=response.read(1024*1024):output.write(block)
        if not verified(temporary):raise ValueError('Pet model checksum mismatch; retry the scan.')
        os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)
    return folder


def decode_detections(output, threshold=0.5):
    """Decode normalized [x1,y1,x2,y2,confidence,class] rows into stored boxes."""
    found=[]
    for row in np.asarray(output).reshape(-1,6):
        if not np.isfinite(row).all():continue
        species=CLASSES.get(int(row[5]));confidence=float(row[4])
        if species is None or confidence<threshold:continue
        x1,y1,x2,y2=np.clip(row[:4],0,1).tolist()
        if x2<=x1 or y2<=y1:continue
        found.append((species,confidence,[x1,y1,x2-x1,y2-y1]))
    return found


class PetDetector:
    def __init__(self,progress=lambda _:None):
        folder=prepare_pet_model(progress)
        config=ROOT/'data'/'yolo-config'
        config.mkdir(parents=True,exist_ok=True)
        os.environ['YOLO_CONFIG_DIR']=str(config)
        from ultralytics import YOLO,settings
        settings.update({'sync':False})
        self.model=YOLO(str(folder/MODEL_NAME))

    def detect(self,path):
        with Image.open(path) as source:
            image=ImageOps.exif_transpose(source).convert('RGB')
        # Ultralytics letterboxes to preserve aspect ratio, unlike the old square stretch.
        result=self.model.predict(image,imgsz=640,conf=.5,classes=list(CLASSES),device='cpu',verbose=False)[0]
        if result.boxes is None or len(result.boxes)==0:return []
        output=np.column_stack((result.boxes.xyxyn.cpu().numpy(),
                                result.boxes.conf.cpu().numpy(),result.boxes.cls.cpu().numpy()))
        return decode_detections(output)


def scan_pets(store,progress,cancelled,detector_factory=PetDetector):
    pending=store.db.execute("""SELECT p.* FROM photos p LEFT JOIN pet_scans s ON s.photo_id=p.id
        WHERE s.photo_id IS NULL OR s.digest<>p.digest OR s.version<>? ORDER BY p.id""",(VERSION,)).fetchall()
    result=dict(processed=0,detections=0,errors=[],cancelled=False)
    if not pending or cancelled.is_set():
        result['cancelled']=cancelled.is_set()
        return result
    detector=detector_factory(progress)
    for index,photo in enumerate(pending,1):
        if cancelled.is_set():
            result['cancelled']=True; break
        progress(f"Finding cats and dogs · {index} of {len(pending)} · {Path(photo['path']).name}")
        try:
            with open(photo['path'],'rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
            if digest!=photo['digest']:
                raise ValueError('Original photo has changed; reimport it before pet detection.')
            detections=detector.detect(photo['path'])
            with store.db:
                store.db.execute('DELETE FROM pets WHERE photo_id=?',(photo['id'],))
                store.db.executemany('INSERT INTO pets(photo_id,species,confidence,box) VALUES(?,?,?,?)',
                    [(photo['id'],kind,confidence,json.dumps(box)) for kind,confidence,box in detections])
                store.db.execute('INSERT OR REPLACE INTO pet_scans(photo_id,digest,version) VALUES(?,?,?)',
                    (photo['id'],digest,VERSION))
            result['processed']+=1;result['detections']+=len(detections)
        except Exception as exc:result['errors'].append(f"{Path(photo['path']).name}: {exc}")
    return result
