# PhotoPeople

A local Windows desktop photo organizer: choose a folder, find faces, name people,
and browse their photos. Built with Python, Tkinter, OpenCV and SQLite.

## Run

Python 3.12 recommended. Run `powershell -ExecutionPolicy Bypass -File setup.ps1`
once, then double-click **Start PhotoPeople.bat**. For visible error output,
run `.venv\Scripts\python.exe app.py` from this directory.

## First library

1. Click **Add photo folder** and choose a small collection to start.
2. Wait for the scan. It includes subfolders; Stop scan keeps completed work.
3. Click a face group, then **Name person**.
4. Use **Merge into…** when two groups contain the same person.
5. Use **Different person** to move a mistaken face into a new group.
6. Click a photo to open its original in your default viewer.

Search filters person names. Libraries persist between launches. Unchanged files
and exact duplicate content are skipped; counts represent distinct indexed photos,
not the number of face detections. Photos with no detected faces are indexed but
have no people gallery entry. Originals are never edited, copied or deleted.

## How it works

YuNet detects faces and five landmarks. SFace aligns each face and creates a
128-value embedding. Normalized embeddings are compared by cosine similarity,
with a conservative initial cutoff of 0.45 and up to eight recent examples per
group. A group is assigned at most once in one photo. This is incremental matching,
not model training or a globally optimal clustering algorithm. Results depend on
scan order and image quality; merging and splitting are explicit user corrections.

Photos are EXIF-oriented and downscaled to 1600 pixels before detection. Faces
smaller than 24 pixels at that scale are ignored. SQLite stores original paths,
content hashes, face embeddings and person names; cropped face thumbnails live in
`data/faces/`. Models live in `models/`. Both locations are excluded from Git.
All photo processing is local. The only network operation is initial model download
from OpenCV's GitHub repository (roughly 40 MB).

## Current boundaries

- JPG, PNG, WebP, BMP and TIFF; HEIC and RAW are not yet supported.
- Face grouping is approximate. Side profiles, age changes, occlusion and small
  faces may split a person across groups or produce wrong matches.
- Manual corrections persist for unchanged photos. They do not retrain the model
  or establish permanent cannot-match constraints for future imports.
- This MVP targets small collections first. Several thousand photos may take time
  on a CPU. The UI shows 24 items at a time and scanning runs in a worker thread.
- Original files must remain at their indexed paths to be opened. No folder watch,
  moved-file reconciliation, library deletion UI or undo yet.
- Run one app instance at a time. Closing during a scan requests cancellation;
  close again once the current operation finishes.

## Model sources and licenses

- [OpenCV face detection / recognition tutorial](https://docs.opencv.org/doc/doxygen/html/d0/dd4/tutorial_dnn_face.html)
- [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) — MIT
- [SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) — Apache 2.0

The model license texts are included in `models/`. Models are pretrained third-party
assets, not trained by this project. Download uses the OpenCV Zoo main branch;
model hashes are not pinned yet.

## Tests

`.venv\Scripts\python.exe -m unittest discover -s tests -v`

## Main subject filtering

New scans keep **at most one face per photo**. Face area is the primary signal;
central positioning adds at most a 20% score bonus. Faces smaller than 4% of the
image's short side (or 24 pixels) are ignored. This reduces background strangers,
but cannot always identify the intended subject: a larger bystander can still win,
and group portraits currently keep only one person. Very distant subjects may be skipped.

Restart the app after updating, then click **Update existing photos** to apply this
to your library. It snapshots the database in `data/before-subject-filter-*.sqlite`
first. Unchanged retained faces keep their names and manual group assignments;
filtered faces disappear from groups without deleting original photos. Missing or
unreadable originals keep their previous index and are reported as errors. The
update can be stopped and resumed; already updated photos are skipped.

## People you do not want to remember

Click **Don't remember this person** on a face card to hide the whole group immediately.
**Hidden people** lets you browse hidden groups and **Remember this person** restores one.
Original photos are unchanged. This is a reversible hide/ignore action, not biometric
record deletion: local face examples are retained so future matching faces join the
hidden group. Those examples survive subject-filter rescans even if all its indexed
faces are removed. Recognition remains approximate; a sufficiently different-looking
face can still create a new group. Hide acts on one group, not all existing lookalike
groups. Changes are disabled during scans.
