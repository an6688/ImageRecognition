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
All photo processing is local. Network access is used for initial face and pet model downloads.
Photo inference stays on your computer.

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

## Milestone 2: choose people yourself

Click **All photos** to browse every indexed image, including photos with no saved
faces. Click a photo or **Choose faces** to open the editor. Click a green detected
face box, or drag a rectangle around a missed face. Choose an existing person
(including named groups with zero photos), or enter a name for a new person, and
save. This adds Mom alongside Ani; it does not replace the other person.

Manual selections are retained across rescans of unchanged image content. Selecting
the same face again updates its assignment. If a drawn crop cannot be recognized,
it is still saved as a manual photo tag, but is not used to recognize future photos.
If an original's image content changes, rescanning reports it and preserves existing
manual selections; restore the original or import the changed image at a new path.

The header separates photos scanned, photos with/without saved faces, and saved
face appearances (including a separate hidden count). A photo can have multiple
people, so person photo counts need not add up to total photos. Named empty groups
remain available. **Move saved face to new group** moves the existing indexed face;
use **Choose faces** to select a different face in the picture.

## Photo names and group thumbnails

Photo cards and the face editor list everyone tagged in the photo, including hidden
people (marked hidden) and unnamed groups (shown as Person N). The editor labels
saved face boxes when their position is available or can be matched exactly to a
current detection; the full name list remains visible even when a box cannot be located.

Open a person group and click **Use face as group thumbnail** beneath the desired
photo. This uses that group's saved face crop from the photo and persists across
restarts and rescans. A merge keeps the destination group's thumbnail. Selecting
a different photo changes it again.

Photos without saved tags show **! Identify someone** in All photos. The button
opens the face editor so you can select a missed face and assign an existing person
or create a new one. The prompt disappears once a face tag is saved.

## Cats and dogs

New imports also run local pet detection. Click **Cats** or **Dogs** to browse
virtual galleries (original files are not moved). Counts are unique photos, not
animal counts: one photo with two dogs counts once; a cat-and-dog photo belongs
to both galleries. Open a photo to see blue pet bounding boxes with model scores.

Use **Find pets in existing photos** to analyze previously indexed photos. This
pass does not modify face assignments, names, covers, or manual selections.
Successful results, including no-pet results, are cached by image digest and model
version. Errors remain retryable; stopping preserves completed work. The first
pet scan after an import also checks any pending photos already in the library.

The model detects the categories cat and dog, not individual pet identities.
Small, obscured, or unusual poses may be missed and false detections are possible.
Scores are model confidence, not calibrated probabilities. Detection uses a 0.5
confidence cutoff. Use **No cat in this photo** or **No dog in this photo** to correct false detections.

### Pet model provenance

The app now uses [Ultralytics YOLO11 Medium](https://docs.ultralytics.com/models/yolo11/),
with official `yolo11m.pt` weights from the v8.3.0 assets release, verified by SHA-256
in `pets.py`. Ultralytics software and model usage follow its AGPL-3.0 / enterprise
licensing options; see [Ultralytics licensing](https://www.ultralytics.com/license).
The approximately 41 MB model downloads once. Inference is local on CPU, using
640-pixel input with aspect-preserving letterboxing and a 0.50 confidence cutoff.
Model scores are not calibrated probabilities. Images are never uploaded; optional
Ultralytics sync is disabled and runtime settings live inside ignored `data/`.

Restart the app and click **Find pets in existing photos** after upgrading. Cached
results from the previous MobileNet-SSD version are automatically rechecked. Each
photo's pet results are replaced transactionally; human face assignments are untouched.
Run setup.ps1 on a fresh checkout to install the added Ultralytics/PyTorch dependencies.

### Detector comparison

The old MobileNet-SSD implementation is preserved in `benchmarks/legacy_detector.py`.
Run `.venv\Scripts\python.exe benchmarks/compare_pets.py --model yolo11m.pt <dog-photo-paths>`
to compare at the same 0.50 cutoff. It adds three upstream pet controls and two
non-pet controls, then saves outputs under ignored `data/pet-evaluation/`. Personal
photos and their paths are not committed. Alternate weights must already be in models/.

In the development smoke comparison, the old detector missed all three supplied
Newfoundland photos. YOLO11 Medium detected dogs in two (scores 0.892 and 0.868),
correctly detected the animals in the three pet controls, and returned no pets in
two non-pet controls. The darkest close-up remains a miss. Nano/Small missed a dog
in the mixed-pet control; Extra Large misclassified the dark close-up as a cat and
missed the control cat. Medium was selected from this limited comparison.

These are development examples, including two near-duplicate photos, not an
independent accuracy benchmark. Broader held-out evaluation is still needed. No
threshold was tuned to force the dark close-up into Dogs, and no model was trained.

### Correct false pet detections

Photo cards and the editor have **No cat in this photo** / **No dog in this photo**
actions. These reject that species for the entire photo, immediately updating gallery
membership, counts, labels and boxes. Other species and human tags are unchanged.
Rejections are stored separately from model output and survive rescans and model
upgrades for unchanged photo content. If the image content changes, the old rejection
no longer applies. From All photos, open the editor and click **Undo: no cat/dog**
to restore model detections. Corrections do not retrain the detector or generalize
to other photos of similar clothing.

## Repeatable folder benchmark

`benchmarks/benchmark_folder.py <folder> --labels <labels.json> --repeats 3`
benchmarks the current pet detector without importing images into the app library.
The labels JSON maps filename prefixes (trailing digits removed) to category lists,
for example `{"dog":["dog"],"cat":["cat"],"negative":[]}` for dog1.jpg, cat1.jpg,
and negative1.jpg. Every image must have a label; unknown prefixes stop the run.
Labels describe category presence, not the number of animals.

Each run writes a hashed image manifest, per-image predictions/timings, and summary
JSON into an isolated timestamped folder under ignored `data/benchmarks/`. Model
startup and three warm-up calls are measured separately. Each measured pass uses
a seeded shuffle of the same image set. Per-photo timing separates image decode,
EXIF orientation/RGB conversion, prediction wall time, and result filtering.
Ultralytics preprocess, inference, and postprocess timings are nested diagnostics
inside prediction wall time, not additional costs. Mean, median and p95 timings
are reported. Accuracy uses the first pass only; prediction changes across passes
are flagged. Reports record runtime versions, model hash, settings and CPU threads.

This is a warm CPU **pet-only** baseline; it excludes face recognition, file hashing,
database/UI work and report serialization. File caching can affect decode timings.
It is not an embedded-device benchmark or a held-out accuracy evaluation. Keep
separate held-out images when tuning against the development collection.

### Compare model sizes

Pass `--model yolo11m.pt`, `--model yolo11s.pt`, or `--model yolo11n.pt` to the
folder benchmark. Each model file must already exist in `models/`. The report
records the selected file's SHA-256 and size. Input resolution (640), confidence
cutoff (0.50), CPU execution, seeded image order, and repeat count stay fixed.
Run models sequentially to avoid concurrent inference skewing the comparison.
`--compact` prints a short console summary; full JSON is always saved.
This experiment does not change the app's default model or library.

### Compare PyTorch with ONNX Runtime

Install optional tools with `.venv\Scripts\python -m pip install -r benchmarks/requirements-onnx.txt`,
then run `.venv\Scripts\python benchmarks/export_onnx.py`. This exports the verified
Medium checkpoint to `models/yolo11m.onnx`: FP32, fixed batch 1, fixed 640x640,
opset 17, without embedded NMS or slimming. ONNX's checker validates the result.
The export explicitly selects the legacy PyTorch exporter expected by Ultralytics
8.3.203. The application continues to use its existing PyTorch model.

Run the folder benchmark twice, sequentially, with the same folder and labels:
add `--model yolo11m.pt --square --compact` for the control and
`--model yolo11m.onnx --square --compact` for ONNX. Both use the same Ultralytics
preprocessing, square letterboxing, FP32 CPU execution, confidence cutoff, and
postprocessing. PyTorch and ONNX Runtime each use 8 intra-op threads and 1 inter-op
thread; ONNX executes sequentially. A temporary session-constructor override sets
these options during initialization, including its I/O bindings, and is removed
before measured passes. This override is confined to the benchmark process.

Use this new square PyTorch control when comparing runtimes. Earlier default
benchmarks use minimum rectangular padding, which changes the inference workload.
Startup is split between wrapper creation and the warm-up block: backend session
initialization is lazy and is included in warm-up, not per-photo timings. Model
file size is reported separately; exporting to FP32 does not imply compression.

### One-click benchmark comparison

Double-click **Benchmark Pets.bat**, choose the photo folder, then its labels JSON
(for the existing collection, select `data/benchmarks/labels.json`). It runs the
PyTorch and ONNX square-input controls sequentially and prints each result folder.
The optional ONNX dependencies must be installed first, as described above. A
missing ONNX model is exported automatically. Closing either chooser cancels.
For unattended use:

```powershell
.venv\Scripts\python benchmarks/run_comparison.py --folder "C:\path\to\photos" --labels "C:\path\to\labels.json"
```

Measured results and limitations are recorded in [ONNX experiment notes](benchmarks/onnx-results.md).
