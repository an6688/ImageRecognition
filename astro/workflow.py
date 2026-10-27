"""Create an AstroTrack review from a selected local image folder."""
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import threading
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
SUFFIXES = {'.png', '.jpg', '.jpeg', '.tif', '.tiff'}


class AnalysisCancelled(Exception):
    pass


@dataclass(frozen=True)
class ReviewResult:
    report: Path
    run_dir: Path
    total: int
    failed: int


def inspect_folder(folder):
    folder=Path(folder).resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('Choose an image folder.')
    files=sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES)
    if not files:
        raise ValueError('No PNG, JPEG or TIFF images were found in this folder. Subfolders are not included; FITS files need conversion first.')
    return folder,files


def find_analyzer(repo=REPO):
    candidates=[Path(repo)/'astro/build/Release/astro_analyze.exe',
                Path(repo)/'astro/build/astro_analyze.exe',
                Path(repo)/'astro/build/astro_analyze']
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError('The AstroTrack analyzer has not been built on this machine. Build the astro target once, then choose the folder again. See astro/README.md.')


def run_analyzer(executable, folder, summary, candidates, log_path, cancel):
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    with log_path.open('wb') as log:
        process=subprocess.Popen([str(executable),str(folder),str(summary),str(candidates)],
                                 stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        try:
            while process.poll() is None:
                if cancel.wait(.1):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill();process.wait()
                    raise AnalysisCancelled('Analysis cancelled. Your source images were not changed.')
            if cancel.is_set():
                raise AnalysisCancelled('Analysis cancelled. Your source images were not changed.')
            return process.returncode
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait()


def analyze_folder(folder, *, output_root=None, executable=None, cancel=None, progress=None):
    """Read source images, retaining each run in a new output folder."""
    cancel=cancel or threading.Event()
    progress=progress or (lambda event:None)
    def check():
        if cancel.is_set():
            raise AnalysisCancelled('Analysis cancelled. Your source images were not changed.')
    check()
    folder,files=inspect_folder(folder)
    executable=Path(executable) if executable is not None else find_analyzer()
    if not executable.is_file():
        raise FileNotFoundError('The AstroTrack analyzer could not be found.')
    check()
    output_root=Path(output_root) if output_root is not None else REPO/'data/astrotrack-runs'
    label=re.sub(r'[^A-Za-z0-9._-]+','-',folder.name).strip('.-')[:60] or 'captures'
    run_dir=output_root/(datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+label+'-'+uuid4().hex[:8])
    run_dir.mkdir(parents=True,exist_ok=False)
    summary,candidates,report=run_dir/'summary.csv',run_dir/'candidates.csv',run_dir/'review.html'
    manifest={'source':str(folder),'created_at':datetime.now(timezone.utc).isoformat(),'found':len(files)}
    def state(value,**extra):
        manifest.update(state=value,**extra)
        (run_dir/'run.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    try:
        state('analyzing')
        progress({'phase':'analysis','message':f'Analyzing {len(files):,} images…','done':None,'total':len(files)})
        code=run_analyzer(executable,folder,summary,candidates,run_dir/'analysis.log',cancel)
        check()
        if code not in (0,1) or not summary.is_file() or not candidates.is_file():
            raise RuntimeError('The analyzer could not finish. Details were saved in '+str(run_dir/'analysis.log'))
        with summary.open(encoding='utf-8',newline='') as handle:
            rows=list(csv.DictReader(handle))
        if not rows or not any(row.get('status')=='ok' for row in rows):
            raise ValueError('None of the images could be read. Check that they are supported 8/16-bit images. Details: '+str(run_dir/'analysis.log'))
        failed=sum(row.get('status')!='ok' for row in rows)
        state('preparing',total=len(rows),failed=failed)
        progress({'phase':'previews','message':'Preparing the review…','done':0,'total':len(rows)})
        from .report import build
        from concurrent.futures import CancelledError
        try:
            build(summary,candidates,report,folder.name,progress=lambda done,total:progress({
                'phase':'previews','message':f'Preparing previews: {done:,} of {total:,}',
                'done':done,'total':total}),cancel=cancel)
        except CancelledError as error:
            raise AnalysisCancelled('Analysis cancelled. Your source images were not changed.') from error
        check()
        state('ready',report=str(report))
        return ReviewResult(report,run_dir,len(rows),failed)
    except AnalysisCancelled:
        state('cancelled')
        raise
    except Exception as error:
        state('error',error=str(error))
        raise
