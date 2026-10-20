"""Check the app ONNX adapter against a saved ONNX benchmark (no library writes)."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pets import OnnxPetDetector

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference',type=Path,help='Folder containing an ONNX benchmark report')
    args=parser.parse_args()
    summary=json.loads((args.reference/'summary.json').read_text())
    if summary['model']!='yolo11m.onnx' or summary['rect']:parser.error('Expected square ONNX reference')
    model=ROOT/'models'/'yolo11m.onnx'
    with model.open('rb') as source:
        if hashlib.file_digest(source,'sha256').hexdigest()!=summary['model_sha256']:parser.error('Model hash differs')
    records={r['name']:r for r in json.loads((args.reference/'results.json').read_text()) if r['repeat']==1}
    detector=OnnxPetDetector(print)
    for item in json.loads((args.reference/'manifest.json').read_text()):
        path=Path(item['path'])
        with path.open('rb') as source:
            if hashlib.file_digest(source,'sha256').hexdigest()!=item['sha256']:raise ValueError(f'Changed image: {path.name}')
        actual=detector.detect(path);expected=records[item['name']]['detections']
        if len(actual)!=len(expected):raise AssertionError(f'Box count differs: {path.name}')
        for a,b in zip(actual,expected):
            if a[0]!=b[0]:raise AssertionError(f'Category differs: {path.name}')
            np.testing.assert_allclose([a[1],*a[2]],[b[1],*b[2]],rtol=0,atol=1e-5,err_msg=path.name)
    print(f'PASS: app ONNX adapter matches reference detections on {len(records)} photos (tolerance 1e-5).')

if __name__=='__main__':main()
