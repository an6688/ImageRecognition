"""Export the existing Medium weights; does not change the application's model."""
import functools
import sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pets import PetDetector
import torch
import onnx

if __name__=='__main__':
    detector=PetDetector(print)
    # Ultralytics 8.3.203 predates Torch's default dynamo exporter.
    # Select its intended legacy exporter explicitly, without editing the package.
    with patch.object(torch.onnx,'export',functools.partial(torch.onnx.export,dynamo=False)):
        path=detector.model.export(format='onnx',imgsz=640,batch=1,device='cpu',
            half=False,dynamic=False,simplify=False,nms=False,opset=17)
    onnx.checker.check_model(path)
    print('Validated ONNX model:',path)
