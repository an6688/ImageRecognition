"""Experimental aligned sequence previews; independent of the C++ quality detector.

Requires numpy and opencv-python. Reads originals without changing them.
"""
import argparse
import base64
import html
import json
from pathlib import Path

import cv2
import numpy as np

SUFFIXES = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}


def decode(path, size):
    pixels = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if pixels is None or pixels.dtype not in (np.uint8, np.uint16):
        raise ValueError('Cannot decode as an 8/16-bit image')
    original_shape = pixels.shape[:2]
    if pixels.ndim == 3:
        pixels = cv2.cvtColor(pixels, cv2.COLOR_BGRA2GRAY if pixels.shape[2] == 4 else cv2.COLOR_BGR2GRAY)
    pixels = pixels.astype(np.float32) / (65535 if pixels.dtype == np.uint16 else 255)
    scale = min(1., size / max(pixels.shape))
    if scale < 1:
        pixels = cv2.resize(pixels, (round(pixels.shape[1]*scale), round(pixels.shape[0]*scale)), interpolation=cv2.INTER_AREA)
    return pixels, original_shape


def align(anchor, moving):
    """Small translation/rotation only; reject low correlation or overlap.

    Returns warped samples, interpolation-safe validity mask, diagnostics.
    ECC optimizes correlation; this is not a star-matched astrometric solution.
    """
    if anchor.shape != moving.shape:
        raise ValueError('Image dimensions differ from the alignment anchor')
    if min(float(anchor.std()), float(moving.std())) < 1e-4:
        raise ValueError('Too little contrast for alignment')
    matrix = np.eye(2, 3, dtype=np.float32)
    try:
        score, matrix = cv2.findTransformECC(anchor, moving, matrix, cv2.MOTION_EUCLIDEAN,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 150, 1e-6), None, 5)
    except cv2.error as error:
        raise ValueError('Alignment did not converge; use the same sky region with small motion') from error
    h, w = anchor.shape
    angle = float(np.degrees(np.arctan2(matrix[1, 0], matrix[0, 0])))
    if not np.isfinite(matrix).all() or not np.isfinite(score) or score < .7:
        raise ValueError('Alignment correlation below experimental 0.70 cutoff')
    if abs(angle) > 10 or np.linalg.norm(matrix[:, 2]) > .2 * min(h, w):
        raise ValueError('Motion exceeds preview limit (10 degrees / 20% of short dimension)')
    flags = cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP
    warped = cv2.warpAffine(moving, matrix, (w, h), flags=flags)
    support = cv2.warpAffine(np.ones_like(moving), matrix, (w, h), flags=flags)
    valid = support > .999
    if valid.mean() < .75:
        raise ValueError('Less than 75% valid overlap')
    return warped, valid, dict(correlation=round(float(score), 4), angle=round(angle, 3),
        dx=round(float(matrix[0, 2]), 3), dy=round(float(matrix[1, 2]), 3), overlap=round(float(valid.mean()), 4))


def encode(array):
    return base64.b64encode(array.astype(np.uint8).tobytes()).decode('ascii')


def prepare(folder, size=640, limit=40):
    paths = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES), key=lambda p: p.name)
    if len(paths) < 2:
        raise ValueError('Choose at least two supported images of the same sky region')
    if len(paths) > limit:
        raise ValueError(f'{len(paths)} images found; preview limit is {limit}. Select a smaller sequence folder.')
    anchor = original_shape = None
    frames, rejected = [], []
    for path in paths:
        try:
            pixels, shape = decode(path, size)
            if anchor is None:
                if pixels.std() < 1e-4:
                    raise ValueError('Too little contrast to anchor a sequence')
                anchor, original_shape = pixels, shape
                valid = np.ones_like(anchor, dtype=bool)
                info = dict(correlation=1., angle=0., dx=0., dy=0., overlap=1.)
            else:
                if shape != original_shape:
                    raise ValueError('Stored image dimensions differ from the alignment anchor')
                pixels, valid, info = align(anchor, pixels)
            frames.append(dict(name=path.name, pixels=encode(np.rint(np.clip(pixels, 0, 1)*255)),
                               mask=encode(valid), **info))
        except (ValueError, OSError, cv2.error) as error:
            rejected.append(dict(name=path.name, reason=str(error)))
    if not frames:
        raise ValueError('No usable alignment anchor')
    return dict(width=anchor.shape[1], height=anchor.shape[0], frames=frames, rejected=rejected,
                original_width=original_shape[1], original_height=original_shape[0])


def build(folder, output, title='Astro sequence explorer', size=640):
    if output.exists():
        raise ValueError('Output already exists; choose a new filename')
    data = prepare(folder, size)
    template = Path(__file__).with_name('sequence_view.html').read_text(encoding='utf-8')
    document = template.replace('__TITLE__', html.escape(title)).replace('__DATA__', json.dumps(data).replace('<', '\\u003c'))
    with output.open('x', encoding='utf-8') as handle:
        handle.write(document)
    print(f'{len(data["frames"])} aligned previews, {len(data["rejected"])} excluded: {output}')
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--title', default='Astro sequence explorer')
    parser.add_argument('--size', type=int, default=640, choices=range(128, 1025), metavar='128..1024')
    args = parser.parse_args()
    try:
        build(args.folder, args.output, args.title, args.size)
    except (ValueError, OSError) as error:
        parser.exit(2, f'{error}\n')
