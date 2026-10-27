"""Preview or apply moves for images explicitly rejected in an AstroTrack review."""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

DECISIONS = {'keep', 'reject', 'revisit', 'unreviewed'}
IMAGE_TYPES = {'.png', '.jpg', '.jpeg', '.tif', '.tiff'}


def inside(path, root):
    return path != root and path.is_relative_to(root)


def plan_moves(document, source_dir):
    """Validate the entire plan before creating folders or moving any files."""
    root = Path(source_dir).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Source folder must be a directory.')
    if (not isinstance(document, dict) or document.get('kind') != 'astrotrack-review'
            or document.get('schema_version') != 1
            or not isinstance(document.get('assessments'), list)):
        raise ValueError('Expected an AstroTrack review export (astro-review.json).')
    rejected = root / 'Rejected'
    if rejected.is_symlink() or rejected.resolve() != rejected:
        raise ValueError('Rejected must be an ordinary folder inside the source folder.')
    if rejected.exists() and not rejected.is_dir():
        raise ValueError('Rejected exists and is not a directory.')
    moves, seen = [], set()
    for item in document['assessments']:
        if not isinstance(item, dict) or item.get('review_decision') not in DECISIONS:
            raise ValueError('Invalid review decision.')
        if not isinstance(item.get('path'), str) or not item['path']:
            raise ValueError('Each review entry must contain its original image path.')
        source = Path(item['path'])
        if not source.is_absolute() or '..' in source.parts:
            raise ValueError('Export must contain absolute paths without parent traversal.')
        source = source.absolute()
        if source in seen:
            raise ValueError('Duplicate review path: '+str(source))
        seen.add(source)
        if item['review_decision'] != 'reject':
            continue
        resolved = source.resolve(strict=True)
        if not inside(resolved, root) or resolved.is_relative_to(rejected):
            raise ValueError('Rejected image is outside the source folder or already in Rejected: '+str(source))
        if source.is_symlink() or resolved != source or not source.is_file():
            raise ValueError('Only ordinary image files can be moved: '+str(source))
        if source.suffix.lower() not in IMAGE_TYPES:
            raise ValueError('Not a supported report image: '+str(source))
        destination = rejected / source.relative_to(root)
        if destination.resolve() != destination or not inside(destination.resolve(), rejected):
            raise ValueError('Destination escapes the Rejected folder: '+str(destination))
        if destination.exists() or destination.is_symlink():
            raise FileExistsError('Destination already exists: '+str(destination))
        parent = destination.parent
        while parent != root:
            if parent.exists() and not parent.is_dir():
                raise ValueError('Destination parent is not a directory: '+str(parent))
            parent = parent.parent
        stat = source.stat()
        moves.append((source, destination, (stat.st_size, stat.st_mtime_ns, stat.st_ino)))
    return root, moves


def move_no_replace(source, destination, expected):
    """Exclusive destination creation; retain the source if copying fails."""
    stat = source.stat()
    if (stat.st_size, stat.st_mtime_ns, stat.st_ino) != expected:
        raise ValueError('Image changed since the move preview: '+str(source))
    created = False
    try:
        with source.open('rb') as original, destination.open('xb') as target:
            created = True
            shutil.copyfileobj(original, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        shutil.copystat(source, destination)
        stat = source.stat()
        if (stat.st_size, stat.st_mtime_ns, stat.st_ino) != expected:
            raise ValueError('Image changed while copying: '+str(source))
        source.unlink()
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise


def organize(review_path, source_dir, apply=False):
    with Path(review_path).open(encoding='utf-8-sig') as handle:
        document = json.load(handle)
    root, moves = plan_moves(document, source_dir)
    for source, destination, _ in moves:
        print(f'{source} -> {destination}')
    print(f'{len(moves)} rejected image(s). '+('Moving files.' if apply else 'Preview only; no files changed. Add --apply to move them.'))
    if not apply or not moves:
        return None
    # All targets are verified to remain inside the explicitly selected image folder.
    rejected = root / 'Rejected'
    rejected.mkdir(exist_ok=True)
    journal = rejected / ('astro-moves-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]+'.jsonl')
    with journal.open('x', encoding='utf-8') as log:
        for source, destination, expected in moves:
            if not inside(source.resolve(strict=True), root) or source.is_symlink():
                raise ValueError('Source location changed: '+str(source))
            if destination.resolve() != destination or not inside(destination.resolve(), rejected):
                raise ValueError('Destination location changed: '+str(destination))
            destination.parent.mkdir(parents=True, exist_ok=True)
            entry = {'source':str(source), 'destination':str(destination)}
            log.write(json.dumps({**entry, 'status':'planned'})+'\n')
            log.flush()
            os.fsync(log.fileno())
            move_no_replace(source, destination, expected)
            log.write(json.dumps({**entry, 'status':'moved'})+'\n')
            log.flush()
            os.fsync(log.fileno())
    print('Move log: '+str(journal))
    return journal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review', type=Path, help='Exported astro-review.json')
    parser.add_argument('source_dir', type=Path, help='Original image folder shown in the report')
    parser.add_argument('--apply', action='store_true', help='Move rejected files; otherwise preview only')
    args = parser.parse_args()
    try:
        organize(args.review, args.source_dir, args.apply)
    except (OSError, ValueError, TypeError) as exc:
        print('organize_review: '+str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
