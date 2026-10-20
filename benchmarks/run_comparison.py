"""Run the controlled runtime comparison from a terminal or the Windows launcher."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path)
    parser.add_argument('--labels',type=Path)
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    if args.repeats<1:parser.error('--repeats must be positive')
    if args.folder is None or args.labels is None:
        import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk();root.withdraw()
        try:
            if args.folder is None:
                choice=filedialog.askdirectory(title='Select benchmark photo folder')
                if not choice:return
                args.folder=Path(choice)
            if args.labels is None:
                choice=filedialog.askopenfilename(title='Select benchmark labels JSON',
                    initialdir=str(ROOT/'data'/'benchmarks'),filetypes=[('Labels','*.json')])
                if not choice:return
                args.labels=Path(choice)
        finally:root.destroy()
    if not args.folder.is_dir():parser.error('Photo folder does not exist')
    if not args.labels.is_file():parser.error('Labels file does not exist')
    try:
        import onnx,onnxruntime  # noqa: F401
    except ImportError:
        parser.exit(1,'Install optional tools first: .venv\\Scripts\\python -m pip install -r benchmarks/requirements-onnx.txt\n')
    def run(*arguments):
        subprocess.run([sys.executable,*map(str,arguments)],cwd=ROOT,check=True)
    try:
        if not (ROOT/'models'/'yolo11m.onnx').is_file():run('benchmarks/export_onnx.py')
        for model in ('yolo11m.pt','yolo11m.onnx'):
            print(f'\nBenchmarking {model}',flush=True)
            run('benchmarks/benchmark_folder.py',args.folder.resolve(),'--labels',args.labels.resolve(),
                '--model',model,'--square','--compact','--repeats',args.repeats)
    except subprocess.CalledProcessError as exc:
        parser.exit(exc.returncode,'Benchmark stopped; see the error above.\n')
    print('\nComparison complete. Full reports are in data/benchmarks.')

if __name__=='__main__':main()
