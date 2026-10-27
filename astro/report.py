"""Generate an offline AstroTrack exposure-review workspace (NumPy, OpenCV, Pillow)."""
import argparse,base64,csv,html,io,json,math,os,sys
from collections import Counter,defaultdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import cv2
import numpy as np
from PIL import Image

def encode(a,format='JPEG'):
    buf=io.BytesIO();Image.fromarray(a).save(buf,format=format,**({'quality':90} if format=='JPEG' else {}))
    return 'data:image/'+('jpeg' if format=='JPEG' else 'png')+';base64,'+base64.b64encode(buf.getvalue()).decode('ascii')

def n(value,default=0):
    try:
        result=float(value)
        return result if math.isfinite(result) else default
    except (TypeError,ValueError):return default

def read_gray(path):
    a=cv2.imdecode(np.fromfile(path,dtype=np.uint8),cv2.IMREAD_UNCHANGED)
    if a is None:raise ValueError('Image cannot be decoded: '+str(path))
    if a.dtype not in (np.uint8,np.uint16):raise ValueError('Expected unsigned 8/16-bit pixels')
    if a.ndim==3:a=cv2.cvtColor(a,cv2.COLOR_BGRA2GRAY if a.shape[2]==4 else cv2.COLOR_BGR2GRAY)
    return a

def views(gray):
    maximum=np.iinfo(gray.dtype).max
    sample=gray[::4,::4];lo,hi=np.percentile(sample,[1,99.98]);hi=max(hi,lo+maximum/255)
    values=np.arange(maximum+1,dtype=np.float32)
    linear=np.rint(values/maximum*255).astype(np.uint8)
    norm=np.clip((values-lo)/(hi-lo),0,1)
    enhanced=np.rint(np.arcsinh(12*norm)/np.arcsinh(12)*255).astype(np.uint8)
    return linear,enhanced,{'black':round(float(lo),2),'white':round(float(hi),2),'asinh':12}

def render_frame(row,stars):
    path=Path(row['path']);stars=sorted(stars,key=lambda c:n(c.get('peak_contrast')),reverse=True)
    expected=int(n(row.get('measured_candidates',row.get('usable_stars'))))
    if len(stars)!=expected:raise ValueError('Candidate count mismatch: '+path.name)
    bright=stars[:max(1,len(stars)//4)]
    out={'id':int(row['index']),'name':path.name,'path':str(path.absolute()),'status':row['status'],'decision':row.get('review_decision','not_analyzed'),'reason':row.get('review_reason',''),'count':len(stars),'fraction':n(row.get('elongated_fraction')),'ratio':n(row.get('median_elongation')),'peaks':int(n(row.get('peak_count'))),'coverage':row.get('coverage','legacy_unknown'),'examined':int(n(row.get('examined_peaks'))),'skipped':int(n(row.get('skipped_peaks'))),'brightFraction':sum(c['elongated']=='1' for c in bright)/len(bright) if bright else None,'error':row.get('error',''),'examples':[],'markers':[]}
    if row['status']!='ok':return out
    gray=read_gray(path);h,w=gray.shape
    if (w,h)!=(int(row['width']),int(row['height'])):raise ValueError('Image size changed: '+str(path))
    linear,enhanced,stretch=views(gray)
    # Downsample 16-bit data before display mapping. Native crops retain original pixels.
    scale=min(1,1280/max(w,h));preview=cv2.resize(gray,(round(w*scale),round(h*scale)),interpolation=cv2.INTER_AREA)
    out.update(width=w,height=h,previewWidth=preview.shape[1],previewHeight=preview.shape[0],linear=encode(linear[preview]),enhanced=encode(enhanced[preview]),stretch=stretch)
    shown=stars if len(stars)<=120 else [stars[i] for i in np.linspace(0,len(stars)-1,120,dtype=int)]
    out['markers']=[{'x':n(c['x']),'y':n(c['y']),'elongated':c['elongated']=='1'} for c in shown]
    examples=[]
    for flag in ['1','0']:
        group=[c for c in stars if c['elongated']==flag]
        if group:examples.extend(group[i] for i in sorted(set(np.linspace(0,len(group)-1,min(6,len(group)),dtype=int))))
    padded=np.pad(gray,20,mode='constant')
    for c in examples:
        x,y=n(c['x']),n(c['y']);ix,iy=round(x),round(y)
        crop=padded[iy:iy+41,ix:ix+41]
        out['examples'].append({'id':c['candidate_id'],'x':x,'y':y,'cx':x-ix+20,'cy':y-iy+20,'ratio':n(c['elongation']),'major':n(c['major_sigma']),'minor':n(c['minor_sigma']),'angle':n(c['angle_degrees']),'contrast':n(c['peak_contrast']),'elongated':c['elongated']=='1','linear':encode(linear[crop],'PNG'),'enhanced':encode(enhanced[crop],'PNG')})
    return out

def write_launcher(report, image_folder):
    """Create a Windows launcher beside the report; never overwrite another file."""
    def quote(value):
        value=str(value)
        if any(c in value for c in '"\r\n'):
            raise ValueError('Path cannot be represented in a Windows launcher')
        return '"'+value.replace('%','%%')+'"'
    command=' '.join(quote(p) for p in [
        Path(sys.executable),Path(__file__).with_name('review_server.py').absolute(),
        report.absolute(),image_folder])
    launcher=report.with_suffix('.cmd')
    with launcher.open('x',encoding='utf-8',newline='') as handle:
        handle.write('@echo off\r\nsetlocal DisableDelayedExpansion\r\nchcp 65001 >nul\r\n'+command+'\r\nif errorlevel 1 pause\r\n')
    return launcher

def build(summary,candidates,output,title,workers=4):
    if output.exists():raise FileExistsError(output)
    launcher_requested=os.name=='nt' and output.suffix.lower() in {'.html','.htm'}
    if launcher_requested and output.with_suffix('.cmd').exists():
        raise FileExistsError(output.with_suffix('.cmd'))
    with summary.open(encoding='utf-8',newline='') as handle:
        rows=list(csv.DictReader(handle))
    grouped=defaultdict(list)
    with candidates.open(encoding='utf-8',newline='') as handle:
        for c in csv.DictReader(handle):
            grouped[(c['index'],c['path'])].append(c)
    if not rows:raise ValueError('Summary contains no frames')
    frames=[];cv2.setNumThreads(1)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs={pool.submit(render_frame,r,grouped[(r['index'],r['path'])]):r for r in rows}
        for job in as_completed(jobs):
            frames.append(job.result())
            if len(frames)%20==0 or len(frames)==len(rows):print(f'Prepared {len(frames)}/{len(rows)} frames',flush=True)
    frames.sort(key=lambda f:f['id'])
    metadata={'title':title,'frames':frames,'summary':summary.name,'candidates':candidates.name,'versions':sorted({r.get('analysis_version','unknown') for r in rows}),'threshold':1.7,'reviewFraction':.4,'minimumCandidates':8}
    payload=json.dumps(metadata,ensure_ascii=True,separators=(',',':'),allow_nan=False).replace('<','\\u003c')
    template=Path(__file__).with_name('astro_report_template.html').read_text(encoding='utf-8')
    document=template.replace('__TITLE__',html.escape(title)).replace('__REPORT_DATA__',payload)
    with output.open('x',encoding='utf-8') as f:f.write(document)
    folders={Path(f['path']).parent for f in frames}
    if launcher_requested and len(folders)==1:
        print('Local launcher: '+str(write_launcher(output,folders.pop())),flush=True)
    print(f'Report written: {output} ({len(frames)} frames, {output.stat().st_size/1e6:.1f} MB)',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('summary',type=Path);p.add_argument('candidates',type=Path);p.add_argument('output',type=Path);p.add_argument('--title',default='Exposure review');p.add_argument('--workers',type=int,default=4)
    a=p.parse_args();build(a.summary,a.candidates,a.output,a.title,max(1,min(a.workers,8)))
