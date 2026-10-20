"""Repeatable CPU pet baseline. Originals and the app library are never modified."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import platform
import os
from pathlib import Path
import random
import re
import statistics
import sys
import time
from contextlib import nullcontext
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from PIL import Image,ImageOps
from pets import PetDetector,MODEL_NAME,MODEL_SHA256,CLASSES,decode_detections


def score(records):
    metrics={}
    for species in ('cat','dog'):
        tp=sum(species in r['expected'] and species in r['predicted'] for r in records)
        fp=sum(species not in r['expected'] and species in r['predicted'] for r in records)
        fn=sum(species in r['expected'] and species not in r['predicted'] for r in records)
        tn=len(records)-tp-fp-fn
        metrics[species]=dict(tp=tp,fp=fp,fn=fn,tn=tn,
            precision=tp/(tp+fp) if tp+fp else None, recall=tp/(tp+fn) if tp+fn else None)
    metrics['exact_match']=sum(set(r['expected'])==set(r['predicted']) for r in records)
    metrics['photos']=len(records)
    return metrics


def stats(values):
    return dict(median=statistics.median(values),p95=float(np.percentile(values,95)),mean=statistics.mean(values))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('folder',type=Path)
    parser.add_argument('--labels',type=Path,required=True,help='JSON mapping filename prefixes to expected category lists')
    parser.add_argument('--model',choices=['yolo11n.pt','yolo11s.pt','yolo11m.pt','yolo11m.onnx'],default=MODEL_NAME)
    parser.add_argument('--square',action='store_true',help='Use fixed 640x640 letterboxing for runtime comparisons')
    parser.add_argument('--compact',action='store_true')
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--seed',type=int,default=42)
    args=parser.parse_args()
    if args.model.endswith('.onnx') and not args.square:parser.error('ONNX comparison requires --square')
    if args.repeats<1:parser.error('--repeats must be positive')
    labels=json.loads(args.labels.read_text(encoding='utf-8'))
    for values in labels.values():
        if not isinstance(values,list) or any(v not in ('cat','dog') for v in values):parser.error('Labels must be lists containing cat and/or dog')
    paths=sorted(p for p in args.folder.iterdir() if p.is_file() and p.suffix.lower() in {'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'})
    if not paths:parser.error('No supported images')
    manifest=[]
    for path in paths:
        group=re.sub(r'\d+$','',path.stem.lower())
        if group not in labels:parser.error(f'Missing label mapping for {path.name}: {group}')
        with path.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
        with Image.open(path) as source:width,height=source.size
        manifest.append(dict(path=str(path.resolve()),name=path.name,group=group,expected=labels[group],
            sha256=digest,width=width,height=height,bytes=path.stat().st_size))
    run=ROOT/'data'/'benchmarks'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run.mkdir(parents=True)
    (run/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    model_path=ROOT/'models'/args.model
    if not model_path.is_file():parser.error(f'Model missing: {model_path}')
    with model_path.open('rb') as source:model_hash=hashlib.file_digest(source,'sha256').hexdigest()
    start=time.perf_counter()
    if args.model==MODEL_NAME:
        model=PetDetector(print).model
    else:
        config=ROOT/'data'/'yolo-config';config.mkdir(parents=True,exist_ok=True)
        os.environ['YOLO_CONFIG_DIR']=str(config)
        from ultralytics import YOLO,settings
        settings.update({'sync':False})
        model=YOLO(str(model_path),task='detect')
    startup=(time.perf_counter()-start)*1000
    with Image.open(paths[0]) as source:warm=ImageOps.exif_transpose(source).convert('RGB')
    import torch
    torch.set_num_threads(8)
    torch.set_num_interop_threads(1)
    session_context=nullcontext()
    if args.model.endswith('.onnx'):
        import onnxruntime as ort
        original_session=ort.InferenceSession
        options=ort.SessionOptions()
        options.intra_op_num_threads=8
        options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        def controlled_session(*a,**kw):
            kw['sess_options']=options
            return original_session(*a,**kw)
        session_context=patch.object(ort,'InferenceSession',controlled_session)
    start=time.perf_counter()
    with session_context:
        for _ in range(3):model.predict(warm,imgsz=640,rect=not args.square,conf=.5,classes=list(CLASSES),device='cpu',verbose=False)
    warmup=(time.perf_counter()-start)*1000
    assert torch.get_num_threads()==8
    runtime_settings={'torch_intra_threads':torch.get_num_threads(),
                      'torch_interop_threads':torch.get_num_interop_threads()}
    if args.model.endswith('.onnx'):
        session=model.predictor.model.session
        actual=session.get_session_options()
        assert actual.intra_op_num_threads==8 and actual.inter_op_num_threads==1
        runtime_settings.update(ort_intra_threads=actual.intra_op_num_threads,
            ort_interop_threads=actual.inter_op_num_threads,
            ort_execution_mode=str(actual.execution_mode),providers=session.get_providers())
    records=[]
    for repeat in range(args.repeats):
        order=list(range(len(manifest)));random.Random(args.seed+repeat).shuffle(order)
        for index in order:
            item=manifest[index]
            start=time.perf_counter()
            with Image.open(item['path']) as source:
                source.load();decoded=time.perf_counter()
                image=ImageOps.exif_transpose(source).convert('RGB')
            oriented=time.perf_counter()
            result=model.predict(image,imgsz=640,rect=not args.square,conf=.5,classes=list(CLASSES),device='cpu',verbose=False)[0]
            predicted=time.perf_counter()
            boxes=result.boxes
            output=np.column_stack((boxes.xyxyn.cpu().numpy(),boxes.conf.cpu().numpy(),boxes.cls.cpu().numpy())) if boxes is not None and len(boxes) else np.empty((0,6))
            detections=decode_detections(output)
            finished=time.perf_counter()
            records.append(dict(name=item['name'],group=item['group'],repeat=repeat+1,expected=item['expected'],
                predicted=sorted({kind for kind,_,_ in detections}),detections=detections,
                timing_ms=dict(decode=(decoded-start)*1000,orientation_rgb=(oriented-decoded)*1000,
                    prediction_wall=(predicted-oriented)*1000,filter=(finished-predicted)*1000,total=(finished-start)*1000,
                    model_preprocess=result.speed['preprocess'],model_inference=result.speed['inference'],model_postprocess=result.speed['postprocess'])))
        print(f'Completed pass {repeat+1}/{args.repeats} ({len(manifest)} photos)',flush=True)
    # Accuracy is scored once per image, not inflated by repeated timings.
    first=[r for r in records if r['repeat']==1]
    changes=[item['name'] for item in manifest if len({tuple(r['predicted']) for r in records if r['name']==item['name']})>1]
    summary=dict(model=args.model,model_sha256=model_hash,model_bytes=model_path.stat().st_size,
        device='cpu',imgsz=640,rect=not args.square,precision='FP32',runtime_settings=runtime_settings,confidence=.5,repeats=args.repeats,seed=args.seed,startup_ms=startup,warmup_3_calls_ms=warmup,
        platform=platform.platform(),processor=platform.processor(),torch_threads=torch.get_num_threads(),
        packages={p:importlib.metadata.version(p) for p in ['ultralytics','torch','torchvision','Pillow','numpy']+(['onnx','onnxruntime'] if args.model.endswith('.onnx') else [])},
        dataset_groups=dict(Counter(item['group'] for item in manifest)),
        accuracy=score(first),by_group={g:score([r for r in first if r['group']==g]) for g in sorted(labels)},
        timing_ms={key:stats([r['timing_ms'][key] for r in records]) for key in records[0]['timing_ms']},
        prediction_changes_across_repeats=changes,
        caveats=['Development baseline, not a held-out evaluation.',
                 'Warm CPU inference; OS file cache may be warm. Startup excluded from per-photo timing.',
                 'Pet pipeline only: excludes human faces, hashing, database writes, UI and report serialization.',
                 'Internal model stage times are nested inside prediction_wall; do not add them again.',
                 'Category presence is scored, not pet count, identity or box localization.'])
    (run/'results.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    (run/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    if args.compact:
        print(json.dumps(dict(model=args.model,accuracy=summary['accuracy'],total_ms=summary['timing_ms']['total'],inference_ms=summary['timing_ms']['model_inference'],bytes=summary['model_bytes'])))
    else:
        print(json.dumps(summary,indent=2))
    print('OUTPUT_DIRECTORY='+str(run))

if __name__=='__main__':main()
