"""Local face indexing; originals are read only. Each scan runs on one worker."""
from pathlib import Path
import hashlib
import sqlite3
import urllib.request
import os
import cv2
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
MODELS = {
    "face_detection_yunet_2023mar.onnx": "face_detection_yunet",
    "face_recognition_sface_2021dec.onnx": "face_recognition_sface",
}
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def prepare_models(progress=lambda message: None):
    folder = ROOT / "models"
    folder.mkdir(exist_ok=True)
    for filename, family in MODELS.items():
        target = folder / filename
        if target.exists():
            continue
        progress(f"Downloading {family} model (first run only)…")
        url = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/{family}/{filename}"
        temp = target.with_suffix(".download")
        try:
            with urllib.request.urlopen(url, timeout=60) as response, temp.open("wb") as out:
                while block := response.read(1024 * 1024):
                    out.write(block)
            if temp.stat().st_size < 100_000:
                raise ValueError("Model download was incomplete. Please retry.")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
    return folder


class Store:
    def __init__(self, folder=None):
        self.folder = Path(folder or ROOT / "data")
        self.folder.mkdir(parents=True, exist_ok=True)
        self.thumbs = self.folder / "faces"
        self.thumbs.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.folder / "library.sqlite", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS people(id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS photos(
                id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, digest TEXT NOT NULL,
                size INTEGER NOT NULL, modified INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS faces(
                id INTEGER PRIMARY KEY, photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
                person_id INTEGER NOT NULL REFERENCES people(id), embedding BLOB NOT NULL, thumb TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS faces_person ON faces(person_id);
            CREATE INDEX IF NOT EXISTS photos_digest ON photos(digest);
        """)

        columns = {row[1] for row in self.db.execute('PRAGMA table_info(photos)')}
        if 'selection_version' not in columns:
            self.db.execute('ALTER TABLE photos ADD COLUMN selection_version INTEGER NOT NULL DEFAULT 0')
            self.db.commit()

        columns = {row[1] for row in self.db.execute('PRAGMA table_info(people)')}
        if 'hidden' not in columns:
            self.db.execute('ALTER TABLE people ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0')
        self.db.execute("""CREATE TABLE IF NOT EXISTS hidden_examples(
            person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
            embedding BLOB NOT NULL, thumb TEXT NOT NULL)""")
        self.db.commit()

    def close(self):
        self.db.close()

    def people(self, hidden=False):
        return self.db.execute("""SELECT p.id,p.name,p.hidden,COUNT(DISTINCT f.photo_id) AS count,
            COALESCE(MIN(f.thumb), (SELECT thumb FROM hidden_examples h WHERE h.person_id=p.id LIMIT 1)) AS thumb
            FROM people p LEFT JOIN faces f ON f.person_id=p.id
            WHERE p.hidden=? GROUP BY p.id HAVING COUNT(f.id)>0 OR p.hidden=1
            ORDER BY count DESC,p.id""", (int(hidden),)).fetchall()

    def set_hidden(self, person, hidden):
        with self.db:
            if not self.db.execute('SELECT id FROM people WHERE id=?', (person,)).fetchone():
                raise ValueError('Person no longer exists')
            self.db.execute('UPDATE people SET hidden=? WHERE id=?', (int(hidden), person))
            self.db.execute('DELETE FROM hidden_examples WHERE person_id=?', (person,))
            if hidden:
                # Retain matching examples even if a later rescan filters out these faces.
                import shutil
                rows = self.db.execute('SELECT embedding,thumb FROM faces WHERE person_id=? ORDER BY id DESC LIMIT 8', (person,)).fetchall()
                for index, row in enumerate(rows):
                    thumb = row['thumb']
                    if (self.thumbs / thumb).exists():
                        saved = f'hidden-{person}-{index}.jpg'
                        shutil.copyfile(self.thumbs / thumb, self.thumbs / saved)
                        thumb = saved
                    self.db.execute('INSERT INTO hidden_examples(person_id,embedding,thumb) VALUES(?,?,?)',
                                    (person, row['embedding'], thumb))

    def photos(self, person):
        return self.db.execute("""SELECT ph.id,ph.path,MIN(f.id) AS face_id,MIN(f.thumb) AS thumb
            FROM photos ph JOIN faces f ON f.photo_id=ph.id WHERE f.person_id=?
            GROUP BY ph.id ORDER BY ph.id DESC""", (person,)).fetchall()

    def counts(self):
        return tuple(self.db.execute("SELECT (SELECT COUNT(*) FROM photos), (SELECT COUNT(*) FROM faces)").fetchone())

    def rename(self, person, name):
        with self.db:
            self.db.execute("UPDATE people SET name=? WHERE id=?", (name.strip()[:100], person))

    def merge(self, source, target):
        if source == target:
            return
        with self.db:
            if not self.db.execute("SELECT id FROM people WHERE id=?", (target,)).fetchone():
                raise ValueError("Target group no longer exists")
            self.db.execute("UPDATE faces SET person_id=? WHERE person_id=?", (target, source))
            self.db.execute("DELETE FROM people WHERE id=?", (source,))

    def separate(self, face_id):
        with self.db:
            if not self.db.execute("SELECT id FROM faces WHERE id=?", (face_id,)).fetchone():
                raise ValueError("Face no longer exists")
            person = self.db.execute("INSERT INTO people DEFAULT VALUES").lastrowid
            self.db.execute("UPDATE faces SET person_id=? WHERE id=?", (person, face_id))
        return person

    def prototypes(self):
        result = []
        for person in self.people() + self.people(hidden=True):
            # A bounded set of examples retains variation without quadratic comparison to every face.
            rows = self.db.execute("SELECT embedding FROM faces WHERE person_id=? ORDER BY id DESC LIMIT 8", (person['id'],))
            examples = [np.frombuffer(row[0], dtype=np.float32) for row in rows]
            examples.extend(np.frombuffer(row[0], dtype=np.float32) for row in self.db.execute(
                'SELECT embedding FROM hidden_examples WHERE person_id=?', (person['id'],)))
            if not examples:
                continue
            vectors = np.stack(examples)
            result.append((person['id'], vectors))
        return result


def choose_group(feature, prototypes, excluded=(), threshold=0.45):
    best_id, best_score = None, threshold
    for person, vectors in prototypes:
        if person in excluded:
            continue
        score = float(np.max(vectors @ feature))
        if score > best_score:
            best_id, best_score = person, score
    return best_id


def select_main_face(detections, width, height):
    """Keep at most one prominent face. Size dominates; centering breaks near ties.

    This is a composition heuristic, not a semantic understanding of the subject.
    A tiny lone background face is rejected instead of promoted automatically.
    """
    if detections is None:
        return []
    minimum = max(24, min(width, height) * 0.04)
    candidates = [face for face in detections if min(face[2:4]) >= minimum]
    if not candidates:
        return []
    def prominence(face):
        x, y, w, h = face[:4]
        distance = ((float(x + w / 2) / width - 0.5) ** 2
                    + (float(y + h / 2) / height - 0.5) ** 2) ** 0.5
        centrality = max(0.0, 1.0 - distance / 0.707107)
        return float(w * h) * (1.0 + 0.2 * centrality)
    return [max(candidates, key=prominence)]


class Indexer:
    def __init__(self, progress=lambda message: None, data=None):
        folder = prepare_models(progress)
        self.detector = cv2.FaceDetectorYN.create(str(folder / 'face_detection_yunet_2023mar.onnx'), '', (320, 320), 0.85)
        self.recognizer = cv2.FaceRecognizerSF.create(str(folder / 'face_recognition_sface_2021dec.onnx'), '')
        self.store = Store(data)

    def extract(self, path):
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert('RGB')
            image.thumbnail((1600, 1600))
        frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        self.detector.setInputSize((frame.shape[1], frame.shape[0]))
        _, detections = self.detector.detect(frame)
        found = []
        if detections is not None:
            for face in select_main_face(detections, frame.shape[1], frame.shape[0]):
                aligned = self.recognizer.alignCrop(frame, face)
                feature = self.recognizer.feature(aligned).reshape(-1).astype(np.float32)
                feature /= max(float(np.linalg.norm(feature)), 1e-12)
                crop = Image.fromarray(cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB))
                found.append((feature, crop))
        return found

    def scan(self, folder, progress, cancelled, paths=None):
        store = self.store
        if paths is None:
            paths = sorted(p for p in Path(folder).rglob('*') if p.is_file() and p.suffix.lower() in EXTENSIONS)
        totals = dict(imported=0, skipped=0, faces=0, errors=[], cancelled=False)
        prototypes = store.prototypes()
        for number, path in enumerate(paths, 1):
            if cancelled.is_set():
                totals['cancelled'] = True
                break
            progress(f"Photo {number} of {len(paths)} · {path.name}")
            try:
                stat = path.stat()
                old = store.db.execute('SELECT * FROM photos WHERE path=?', (str(path.resolve()),)).fetchone()
                if old and old['selection_version'] == 1 and old['size'] == stat.st_size and old['modified'] == stat.st_mtime_ns:
                    totals['skipped'] += 1
                    continue
                with path.open('rb') as source:
                    digest = hashlib.file_digest(source, 'sha256').hexdigest()
                duplicate = store.db.execute('SELECT id FROM photos WHERE digest=? AND path<>?', (digest, str(path.resolve()))).fetchone()
                if duplicate and not old:
                    totals['skipped'] += 1
                    continue
                faces = self.extract(path)
                # Preserve labels and manual group assignments for retained faces.
                previous = []
                if old and old['digest'] == digest:
                    previous = [(row['person_id'], np.frombuffer(row['embedding'], dtype=np.float32)[None, :])
                        for row in store.db.execute('SELECT person_id,embedding FROM faces WHERE photo_id=?', (old['id'],))]
                with store.db:
                    if old:
                        store.db.execute('DELETE FROM photos WHERE id=?', (old['id'],))
                        prototypes = store.prototypes()
                    photo = store.db.execute('INSERT INTO photos(path,digest,size,modified,selection_version) VALUES(?,?,?,?,1)',
                        (str(path.resolve()), digest, stat.st_size, stat.st_mtime_ns)).lastrowid
                    assigned = set()
                    for index, (feature, crop) in enumerate(faces):
                        person = choose_group(feature, previous, assigned, threshold=0.999)
                        if person is None:
                            person = choose_group(feature, prototypes, assigned)
                        if person is None:
                            person = store.db.execute('INSERT INTO people DEFAULT VALUES').lastrowid
                        assigned.add(person)
                        thumb = f'{digest}_{index}.jpg'
                        crop.save(store.thumbs / thumb, quality=90)
                        store.db.execute('INSERT INTO faces(photo_id,person_id,embedding,thumb) VALUES(?,?,?,?)',
                            (photo, person, feature.tobytes(), thumb))
                prototypes = store.prototypes()
                totals['imported'] += 1
                totals['faces'] += len(faces)
            except Exception as exc:
                totals['errors'].append(f'{path.name}: {exc}')
                prototypes = store.prototypes()
        return totals

    def refresh_library(self, progress, cancelled):
        from datetime import datetime
        # Snapshot includes names/corrections, allowing recovery of the old index.
        backup = self.store.folder / ('before-subject-filter-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite')
        target = sqlite3.connect(backup)
        try:
            self.store.db.backup(target)
        finally:
            target.close()
        paths = [Path(row[0]) for row in self.store.db.execute('SELECT path FROM photos ORDER BY id')]
        return self.scan(None, progress, cancelled, paths=paths)
