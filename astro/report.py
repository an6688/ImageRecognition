"""Build a self-contained, local review report from Astro CSVs (requires Pillow)."""
import argparse
import base64
import csv
import html
import io
import json
import math
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


def embed(image):
    stream = io.BytesIO()
    image.save(stream, format='JPEG', quality=88)
    return 'data:image/jpeg;base64,' + base64.b64encode(stream.getvalue()).decode('ascii')


def escape(value):
    return html.escape(str(value), quote=True)


def build(summary_path, candidates_path, output, title):
    with summary_path.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    with candidates_path.open(encoding='utf-8', newline='') as handle:
        candidate_rows = list(csv.DictReader(handle))
    grouped = defaultdict(list)
    for row in candidate_rows:
        grouped[(row['index'], row['path'])].append(row)
    versions = {row.get('analysis_version', 'elongation-v1') for row in rows}
    version = ', '.join(sorted(versions)) or 'unknown'
    for row in rows:
        row['usable_stars'] = row.get('measured_candidates', row.get('usable_stars', '0'))
    cards = []
    for row in rows:
        path = Path(row['path'])
        key = (row['index'], row['path'])
        candidates = grouped[key]
        if len(candidates) != int(row['usable_stars']):
            raise ValueError(f'Candidate CSV does not match summary for {path.name}')
        candidates.sort(key=lambda star: float(star['peak_contrast']), reverse=True)
        decision = row['review_decision']
        readable = decision.replace('_', ' ').capitalize()
        coverage = row.get('coverage', 'legacy_unknown')
        examined = row.get('examined_peaks', 'unknown')
        skipped = row.get('skipped_peaks', 'unknown')
        if coverage == 'limited':
            coverage_text = f"Coverage limited: examined {examined} of {row['peak_count']} detected peaks; skipped {skipped}. Shape result describes only that brightest subset."
            readable += ' (sample only)'
        elif coverage == 'all_detected_peaks':
            coverage_text = f"All {examined} detected peaks examined; none skipped by a processing cap. This is not proof that every star was detected."
        else:
            coverage_text = 'Coverage unavailable for this result.'
        visual = ''
        if row['status'] == 'ok':
            with Image.open(path) as original:
                # Match the analyzer's stored raster, deliberately ignoring EXIF rotation.
                original.seek(0)
                if original.mode in ('I;16', 'I;16L', 'I;16B', 'I'):
                    original = original.point(lambda value: value / 256).convert('L')
                raster = original.convert('RGB')
            if raster.size != (int(row['width']), int(row['height'])):
                raise ValueError(f'Image dimensions changed since analysis: {path}')
            thumb = ImageOps.contain(raster, (1000, 750))
            draw = ImageDraw.Draw(thumb)
            scale = thumb.width / raster.width
            shown = candidates if len(candidates) <= 120 else [candidates[round(i*(len(candidates)-1)/119)] for i in range(120)]
            for candidate in shown:
                x, y = float(candidate['x']) * scale, float(candidate['y']) * scale
                color = '#f5b841' if candidate['elongated'] == '1' else '#b7e0f4'
                draw.ellipse((x-4, y-4, x+4, y+4), outline=color, width=1)
            examples = []
            for shape in ['1', '0']:
                group = [s for s in candidates if s['elongated'] == shape]
                if group:
                    examples.extend(group[i] for i in sorted({0, len(group)//2, len(group)-1}))
            crops = []
            for candidate in examples:
                x, y = float(candidate['x']), float(candidate['y'])
                left, top = int(round(x))-20, int(round(y))-20
                crop = raster.crop((left, top, left+41, top+41)).resize((164, 164), Image.Resampling.NEAREST)
                overlay = ImageDraw.Draw(crop)
                angle = math.radians(float(candidate['angle_degrees']))
                cx, cy = (x-left)*4, (y-top)*4
                length = float(candidate['major_sigma'])*8
                dx, dy = math.cos(angle)*length, math.sin(angle)*length
                overlay.line((cx-dx,cy-dy,cx+dx,cy+dy), fill='#f5b841', width=1)
                crops.append(f'<figure><img src="{embed(crop)}" alt="Candidate crop with major axis"/>'
                             f'<figcaption>#{escape(candidate["candidate_id"])} · ratio {float(candidate["elongation"]):.2f}'
                             f'<br>x {x:.0f}, y {y:.0f}</figcaption></figure>')
            visual = f'<img class="overview" src="{embed(thumb)}" alt="Measured candidates in {escape(path.name)}"/>'
            if crops:
                visual += '<p class="caption">Brightest, middle-ranked and faintest candidates in each shape group (elongated first, then other). Crops are 41×41 pixels enlarged 4×; the line shows the measured major axis.</p><div class="crops">' + ''.join(crops) + '</div>'
        else:
            visual = f'<p>Decode/analysis error: {escape(row["error"])}</p>'
        fraction = 'unavailable' if not row['elongated_fraction'] else f'{float(row["elongated_fraction"]):.1%}'
        median = 'unavailable' if not row['median_elongation'] else f'{float(row["median_elongation"]):.2f}'
        cards.append(f'''<section class="frame" data-decision="{escape(decision)}" data-name="{escape(path.name)}" data-coverage="{escape(coverage)}">
<div class="frame-heading"><h2>{escape(path.name)}</h2><span class="badge {escape(decision)}">{readable}</span></div>
<p>{escape(row['review_reason'])}</p><p><strong>{escape(coverage_text)}</strong></p>
<p class="metrics">{escape(row['usable_stars'])} measured candidates · {fraction} elongated · median ratio {median} · {float(row['analysis_ms']):.1f} ms analysis</p>
<p class="caption">{escape(row['peak_count'])} initial peaks. These candidates are not confirmed stars. Excluded candidates did not pass the measurement checks; they were not automatically classified as elongated.</p>
{visual}
<div class="review"><label>Your assessment <select class="human"><option value="unreviewed">Unreviewed</option><option value="elongation_visible">Elongation visible</option><option value="no_obvious_elongation">No obvious elongation</option><option value="uncertain">Uncertain / unsuitable</option></select></label>
<label>Notes <input class="note" type="text" placeholder="Evidence or uncertainty"/></label></div></section>''')
    counts = {decision: sum(row['review_decision'] == decision for row in rows)
              for decision in ['review_suggested', 'no_elongation_flag', 'insufficient_evidence', 'not_analyzed']}
    stats = ' · '.join(f'{count} {key.replace("_", " ")}' for key, count in counts.items() if count)
    metadata = json.dumps({'summary': summary_path.name, 'candidates': candidates_path.name,
                           'analysis_version': version, 'threshold': 1.7, 'review_fraction': .4, 'minimum_candidates': 8}).replace('<', '\\u003c')
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>''' + escape(title) + '''</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#11171b;color:#e6edf0;font:16px/1.55 system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:40px 28px}h1{font-size:32px;margin:8px 0}h2{font-size:20px;margin:0}p{max-width:95ch}.eyebrow{color:#a2b4bd;font-size:13px;letter-spacing:.1em;text-transform:uppercase}.intro{border-bottom:1px solid #38474f;padding-bottom:28px}.caption{font-size:13px;color:#b4c2c9}.metrics{font-weight:600}.toolbar{display:flex;gap:20px;flex-wrap:wrap;align-items:center;padding:24px 0}.frame{padding:30px 0;border-top:1px solid #38474f}.frame-heading{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}.badge{padding:4px 10px;background:#2b3942;font-size:13px}.review_suggested{background:#5c431b;color:#ffe1a2}.insufficient_evidence{background:#403646;color:#ecdaed}.overview{max-width:100%;max-height:750px;display:block;margin:20px auto;object-fit:contain}.crops{display:flex;gap:12px;flex-wrap:wrap}figure{margin:0}figure img{width:144px;height:144px}figcaption{font-size:12px;color:#c3cfd5}select,input,button{font:inherit;background:#1e2a31;color:#e6edf0;border:1px solid #687b86;padding:8px}button{cursor:pointer}.review{display:flex;gap:20px;margin-top:24px;flex-wrap:wrap}label{display:flex;gap:10px;align-items:center}.review input{width:300px}a{color:#a5d7f2}[hidden]{display:none!important}@media(max-width:600px){main{padding:20px 14px}h1{font-size:26px}.review label{display:block}.review input{width:100%}}
</style><main><div class="intro"><div class="eyebrow">Astro Image Analyzer · Milestone 2 · experimental</div><h1>''' + escape(title) + '''</h1><p>''' + escape(stats) + '''</p>
<p>This report measures the shape of candidate stars. It does not diagnose a tracking fault or certify a frame as good. Sky motion, optics and processing can all affect the result. The supplied phone photos were taken on a fixed tripod; synthetic controls are labeled separately.</p>
<p><strong>Provisional rule:</strong> at least 8 usable candidates; suggest review when at least 40% have a long-to-short axis ratio ≥ 1.7. A ratio near 1 is round. Coverage is reported separately from shape. By default all detected peaks are examined; an optional cap limits the result to the examined subset. Insufficient evidence means fewer than 8 measurable candidates.</p>
<p class="caption">Stored-raster orientation (EXIF rotation ignored). Overview shows at most 120 measured candidates sampled across the contrast range: amber = elongated, pale blue = other. Examples span bright to faint candidates, not human ground truth. No auto-stretch is applied. Repeated/edited phone images are not independent validation observations.</p>
<p class="caption">Source: locally supplied images and the accompanying CSV files. Algorithm: ''' + escape(version) + '''. Summary: ''' + escape(summary_path.name) + '''. Full candidate measurements: ''' + escape(candidates_path.name) + '''.</p></div>
<div class="toolbar"><label>Show <select id="filter"><option value="all">All frames</option><option value="review_suggested">Review suggested</option><option value="insufficient_evidence">Insufficient evidence</option><option value="no_elongation_flag">No elongation flag</option><option value="not_analyzed">Not analyzed</option></select></label><button id="export">Export human assessments</button><span class="caption">Edits stay in this tab until exported.</span></div>
''' + ''.join(cards) + '''<footer><p>Measurements use background-subtracted second moments. <a href="https://photutils.readthedocs.io/en/stable/api/photutils.segmentation.SourceCatalog.html">Reference definition of elongation</a>. This implementation does not depend on Photutils.</p><p class="caption">No photos are uploaded by this report. Decisions are provisional; no real-world accuracy claim has been established.</p></footer></main>
<script>const metadata=''' + metadata + ''';
document.querySelector('#filter').addEventListener('change',e=>{document.querySelectorAll('.frame').forEach(s=>{s.hidden=e.target.value!=='all'&&s.dataset.decision!==e.target.value})});
document.querySelector('#export').addEventListener('click',()=>{const data={...metadata,reviewed_at:new Date().toISOString(),assessments:[...document.querySelectorAll('.frame')].map(s=>({file:s.dataset.name,algorithm_decision:s.dataset.decision,coverage:s.dataset.coverage,human_assessment:s.querySelector('.human').value,notes:s.querySelector('.note').value}))};const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='astro-human-assessments.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
</script></html>'''
    with output.open('x', encoding='utf-8') as handle:
        handle.write(document)
    print(f'Report written: {output} ({len(rows)} frames)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', type=Path)
    parser.add_argument('candidates', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--title', default='Phone-photo elongation review')
    args = parser.parse_args()
    build(args.summary, args.candidates, args.output, args.title)
