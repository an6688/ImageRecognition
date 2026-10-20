"""Local cat/dog detection using a pinned MobileNet-SSD VOC model."""
from pathlib import Path
import os
import urllib.request
import cv2
import numpy as np
from PIL import Image, ImageOps

REVISION = 'bb17b6c3eef36d80be441ae8e5339be66e8e3b7a'
VERSION = 'mobilenet-ssd-voc-1-conf50'
CLASSES = {8: 'cat', 12: 'dog'}
ROOT = Path(__file__).resolve().parents[1]


def prepare_pet_model(progress=lambda _: None):
    folder = ROOT / 'models'
    folder.mkdir(exist_ok=True)
    for filename, minimum in [('deploy.prototxt', 10000), ('mobilenet_iter_73000.caffemodel', 20000000)]:
        target = folder / filename
        if target.exists() and target.stat().st_size >= minimum:
            continue
        progress('Downloading cat/dog model (first run only)…')
        temporary = target.with_suffix(target.suffix + '.download')
        try:
            url = f'https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/{REVISION}/{filename}'
            with urllib.request.urlopen(url,timeout=60) as response, temporary.open('wb') as output:
                while block := response.read(1024*1024): output.write(block)
            if temporary.stat().st_size < minimum:
                raise ValueError('Pet model download incomplete; retry the scan.')
            os.replace(temporary,target)
        finally:temporary.unlink(missing_ok=True)
    return folder


def decode_detections(output, threshold=0.5):
    found=[]
    for row in output.reshape(-1,7):
        if not np.isfinite(row).all(): continue
        species=CLASSES.get(int(row[1]))
        confidence=float(row[2])
        if species is None or confidence < threshold: continue
        x1,y1,x2,y2=np.clip(row[3:7],0,1).tolist()
        if x2<=x1 or y2<=y1: continue
        found.append((species,confidence,[x1,y1,x2-x1,y2-y1]))
    return found


class PetDetector:
    def __init__(self,progress=lambda _:None):
        folder=prepare_pet_model(progress)
        self.net=cv2.dnn.readNetFromCaffe(str(folder/'deploy.prototxt'),str(folder/'mobilenet_iter_73000.caffemodel'))

    def detect(self,path):
        with Image.open(path) as source:
            image=ImageOps.exif_transpose(source).convert('RGB')
            image.thumbnail((1600,1600))
        frame=cv2.cvtColor(np.array(image),cv2.COLOR_RGB2BGR)
        self.net.setInput(cv2.dnn.blobFromImage(frame,1/127.5,(300,300),127.5,swapRB=False,crop=False))
        return decode_detections(self.net.forward())
