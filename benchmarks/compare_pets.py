"""Local smoke comparison; private input paths/results stay under ignored data/."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
(ROOT/'data'/'yolo-config').mkdir(parents=True,exist_ok=True)
os.environ['YOLO_CONFIG_DIR']=str(ROOT/'data'/'yolo-config')
from PIL import Image,ImageOps
from ultralytics import YOLO,settings
from benchmarks.legacy_detector import PetDetector as Legacy,REVISION
settings.update({'sync':False})

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',default='yolo11m.pt')
    parser.add_argument('photos',nargs='*',help='User dog photos to compare locally')
    args=parser.parse_args()
    folder=ROOT/'data'/'pet-evaluation';folder.mkdir(parents=True,exist_ok=True)
    cases=[(Path(path),['dog']) for path in args.photos]
    for filename,expected in [('000542.jpg',['cat']),('001150.jpg',['dog']),('001763.jpg',['cat','dog'])]:
        path=folder/filename
        if not path.exists():urllib.request.urlretrieve(f'https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/{REVISION}/images/{filename}',path)
        cases.append((path,expected))
    for name in ['bus.jpg','zidane.jpg']:
        path=folder/name
        if not path.exists():urllib.request.urlretrieve(f'https://raw.githubusercontent.com/ultralytics/assets/main/im/{name}',path)
        cases.append((path,[]))
    legacy=Legacy()
    model=YOLO(str(ROOT/'models'/args.model))
    records=[]
    for path,expected in cases:
        old=legacy.detect(path)
        with Image.open(path) as source:image=ImageOps.exif_transpose(source).convert('RGB')
        start=time.perf_counter()
        result=model.predict(image,imgsz=640,conf=.5,classes=[15,16],device='cpu',verbose=False)[0]
        new=[(result.names[int(b.cls.item())],float(b.conf.item())) for b in result.boxes]
        row=dict(file=str(path),expected=expected,legacy=[(k,float(c)) for k,c,_ in old],candidate_model=args.model,candidate=new,seconds=time.perf_counter()-start)
        records.append(row)
        print(path.name,'old:',row['legacy'],'new:',new)
    (folder/(args.model+'.json')).write_text(json.dumps(records,indent=2),encoding='utf-8')
    print('Results saved locally under data/pet-evaluation/' + args.model + '.json')

if __name__=='__main__':main()
