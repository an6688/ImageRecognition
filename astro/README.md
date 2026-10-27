# Astro Image Analyzer — Milestones 1 and 2

A standalone, sequential C++17 command-line pipeline inside the existing Python
photo-organizer repository. No Python runtime, models, UI, database, camera SDK,
or PhotoPeople dependency is required by this executable.

## Choose a folder and analyze it

In an open AstroTrack report, click **Choose image folder…** in the top bar.
A Windows folder picker opens; choose the captures to analyze. Progress and
**Cancel analysis** appear in the report, and the finished review opens in the same
tab. The current review remains available on cancellation or error. Decisions and
notes stay saved per image sequence in this browser. If browser saving is blocked,
the page asks you to download a backup before leaving the current review.

Launch the report through **Start AstroTrack.bat** or its generated .cmd launcher
and keep AstroTrack running. A standalone file:// HTML cannot launch the analyzer;
its folder button explains how to connect. The local connection accepts only
folders selected in the native picker, protects requests with a session token,
and invalidates old tabs' file actions when switching reports. Refreshing a page
during analysis resumes its progress display. File moves wait until analysis ends.

The desktop window also offers **Choose image folder…** for the first review.
The app validates the folder,
runs the existing C++ analyzer, prepares the previews, and opens the completed
review with folder access. No terminal command or upload is required.

Supported inputs are 8/16-bit PNG, JPEG and TIFF images directly inside the chosen
folder. Subfolders (including Rejected) are excluded. FITS files still require
conversion. Build the analyzer once using the instructions below; the desktop
workflow finds astro/build/Release/astro_analyze.exe or the equivalent single-
configuration build executable.

The analysis stage shows the input count and an activity indicator. Preview
preparation shows actual completed/total progress. **Cancel analysis** stops the
owned analyzer process or cancels pending preview work, then waits for current
preview work to finish. Source images are read without modification. Closing the
desktop app also requests cancellation of a running folder analysis.

Every run uses a new folder under data/astrotrack-runs, containing summary.csv,
candidates.csv, review.html, a launcher, analysis.log and run.json. The manifest
records ready, cancelled or error state. Existing runs are preserved. If some
images cannot be decoded, the review lists those failures; if none can be read,
the app explains the failure and retains the diagnostic files.

## Desktop launch and capture playback

Double-click **Start AstroTrack.bat** in the repository root, or select the
**AstroTrack** tab in the main Photos/Videos app. Open an existing report once.
The app remembers the report, applies the current review UI to its stored previews
and measurements, starts folder access, and opens it in your browser. No separate
server command or helper window is needed. Keep the desktop app open while moving
files. Use one AstroTrack instance at a time; close an older manual launcher if it
already occupies the review port.

**Capture playback** is collapsed initially. Expand it to play every capture embedded in the report in filename
order, independently of review filters and sorting. Play/Pause, 1/2/5/10 fps,
looping, a scrubber, and frame stepping are available. Each preview is decoded
before the next display delay begins, so playback may be slower on a busy machine.
The default display is Linear; switching either display menu updates both views.
Unreadable exposures remain in the timeline with their error shown.

Choose **Review this frame** to pause and open the selected capture in the inspector.
Inspector decisions and notes are disabled during playback to prevent marking a
different image. Playback pauses when its panel is collapsed or the browser tab is hidden. Previews are not
aligned, and filename order does not reproduce capture intervals. This does not
encode or export a video.

The existing aligned sequence explorer is accessible from the desktop panel:
open a saved explorer or create one from 2–40 matching exposures. Its difference
and projection views are complementary to full-sequence playback.

## Build on Windows

Install CMake 3.24+ and Visual Studio's Desktop development with C++ workload.
From the repository root (PowerShell):

```powershell
cmake -S astro -B astro/build -DASTRO_FETCH_OPENCV=ON
cmake --build astro/build --config Release --parallel
ctest --test-dir astro/build -C Release --output-on-failure
New-Item -ItemType Directory -Force astro/results
& ./astro/build/Release/astro_analyze.exe 'E:/your/night-sky-sequence' 'astro/results/run-01.csv'
```

Fetch mode downloads SHA-256-pinned OpenCV 4.12.0 and builds static core/imgproc/
imgcodecs with JPEG, PNG and TIFF codecs. First build takes longer. The existing
Python opencv wheel does **not** provide the C++ development package.
For an existing C++ OpenCV installation, omit fetch mode and pass
`-DOpenCV_DIR=<folder-containing-OpenCVConfig.cmake>`; ensure its runtime libraries
are available if that installation uses DLLs. OpenCV is Apache-2.0; bundled codecs
have their own notices in OpenCV's `3rdparty` directory. Preserve dependency notices
when distributing binaries. No third-party images are bundled.

## Linux / future ARM target

With a native C++17 compiler, CMake, and the distribution's `libopencv-dev`:

```sh
cmake -S astro -B astro/build -DCMAKE_BUILD_TYPE=Release
cmake --build astro/build --parallel 2
ctest --test-dir astro/build --output-on-failure
./astro/build/astro_analyze /path/to/sequence /path/to/new-results.csv
```

The standard-library processing code is architecture independent. For ARM, use a
native ARM build or a CMake toolchain file plus ARM-built dependencies. No x86-only
application intrinsics or Windows imaging APIs are used. ARM execution, memory,
and throughput still need measurement on the target; Windows results are not Pi
performance claims.

## Data flow and contract

`FileImageSource -> Acquisition / Frame -> analyze -> CSV`

- `ImageSource::next()` returns one acquisition or exhaustion. A failed item is
  distinct from exhaustion, allowing later images to continue. Future camera
  acquisition can implement the same interface without changing analysis.
- Files are snapshotted from **one directory**, sorted by UTF-8 path bytes.
  JPEG/JPG, PNG, TIF/TIFF suffix matching is case insensitive. Other suffixes and
  subdirectories are skipped. Order is lexical, not EXIF time or natural numeric
  order; use zero-padded filenames to represent a sequence.
- `Frame` owns row-major grayscale samples, dimensions, original 8/16-bit depth,
  source path and sequence index. There is no retained batch of pixel buffers.
  The current decoder temporarily holds encoded bytes, decoded color/gray and
  the owned samples; memory scales with the largest image, plus the path list.
- OpenCV decoding is isolated in `file_source.cpp`. Color uses OpenCV's BGR/BGRA
  grayscale conversion (approximately 0.299 R + 0.587 G + 0.114 B); alpha is ignored.
  EXIF rotation is ignored so dimensions match stored raster coordinates.
  Multi-page TIFF reads its first page. Float TIFF, RAW and FITS are unsupported.
- Analysis validates frame shape/depth and returns width, height and mean encoded
  grayscale value divided by 255 or 65535. This is a placeholder brightness
  measurement, not calibrated flux, exposure normalization, a star count, or a
  calibrated quality score. JPEG gamma/compression and stretching affect comparisons.
  Milestone 2 additionally measures candidate-star elongation; see below.
- Ordinary read/decode/analysis failures become `error` rows. OpenCV may tolerate
  some damaged JPEGs and emit warnings while returning pixels; successful decode
  is not a guarantee of file integrity. Decoder crashes or process-level resource
  exhaustion are not isolated in this in-process milestone.
- No application threads, queues, parallel frame processing, or camera acquisition.

## CSV and exit codes

The original columns remain first:
`index,path,status,width,height,bit_depth,mean_brightness,decode_ms,analysis_ms,total_ms,error`.
Milestone 2 appends `review_decision,measured_candidates,peak_count,rejected_candidates,median_elongation,elongated_fraction,review_reason,analysis_version,coverage,examined_peaks,skipped_peaks,peak_limit`.
Index is zero-based; text is UTF-8, quoted with doubled quotes, numbers use a dot
decimal separator. Failed rows leave image metrics empty. Path/error fields may
contain embedded newlines; use a real CSV reader. Treat text columns as text when
importing untrusted filenames into spreadsheets.

`steady_clock` timing is milliseconds. Decode includes file reading, decode,
conversion and frame copy. Analysis times validation, brightness and elongation measurement; total is
their sum. Directory enumeration and CSV writing are excluded. These are per-image
latencies, not an end-to-end throughput benchmark.

Exit 0: all selected images succeeded. Exit 1: one or more image failures, with
remaining images processed. Exit 2: usage/setup/output failure or no supported
images. Empty directories produce a header-only CSV and exit 2. Existing output
paths are refused; choose a new `.csv` name. Output parents must already exist.
Use one writer per output path. A fatal output failure may leave a partial CSV.

## Tests

CTest runs three suites with deterministic generated fixtures (no downloads or large images):
8/16-bit statistics and invalid frames; RGB JPEG/PNG/TIFF handling; 16-bit PNG/TIFF;
alpha handling; Unicode names; sorted and nonrecursive enumeration; empty/missing
input; corrupt/empty files followed by good images; exhaustion; error CSV rows;
quote/comma/newline escaping; and output-stream errors. Assertions remain active
in Release builds. See `docs/DATASETS.md` for real-world validation sources and
`docs/INTERVIEW.md` for a ten-minute explanation.

## Milestone 2: candidate elongation and human review

```powershell
& ./astro/build/Release/astro_analyze.exe 'C:/Users/GAME/Downloads/Photos-1-001' 'astro/results/phone.csv' 'astro/results/phone-stars.csv'
& ./.venv/Scripts/python.exe astro/report.py astro/results/phone.csv astro/results/phone-stars.csv astro/results/review.html
& ./.venv/Scripts/python.exe -m unittest discover -s astro/tests -p test_report.py -v
```

Open the HTML report in a browser. The offline workspace includes an exposure list,
issue filters, filename search, sorting, native-pixel candidate crops, review notes,
and JSON assessment export. Click a candidate thumbnail to show a cyan arrow and
ring at its location in the full-image preview. This pointer stays visible when
**Show markers** is off; **Hide pointer** removes it. Zooming keeps the selected
location in view. Changing exposure resets the pointer.

**Linear · original scale** maps the full numeric pixel range directly to the
display. **Enhanced · brighter preview** uses a per-exposure percentile/asinh
stretch to reveal faint detail. Both are grayscale previews matching the analysis
luminance. The stretch is applied to 16-bit data before making the 8-bit display
image, and all crops in an exposure share the same stretch. Brightness and marker
controls affect display only; source images, measurements and decisions are unchanged.
Different exposures use separate display ranges, so their preview brightness is
not a photometric comparison.

The analyzer does not identify objects: a galaxy, close pair or other extended
source can be measured as an elongated star candidate. A review suggestion is not
a confirmed trail or a reason to automatically reject an exposure. The brightest-
quarter fraction is a descriptive cross-check, not a calibrated confidence score.

The report embeds previews and requires no server or uploads. Decisions and notes
save in browser storage when available; export a portable backup before switching
browsers. See the review workflow below. The generator requires NumPy, OpenCV and Pillow (already
in the app requirements), and uses the adjacent `astro_report_template.html`. Keep
that template beside `report.py`. The C++ analyzer remains independent of Python.
Generated reports, measurements, photos and build products stay in ignored folders.

Run the report tests with:

```powershell
.venv\Scripts\python.exe -m unittest discover -s astro/tests -p test_report.py -v
node astro/tests/report_controls.cjs astro/astro_report_template.html
```
The optional fourth CLI argument creates a candidate CSV with stored-raster
coordinates, axis lengths, orientation, ratios and contrast. Both output files
must be new, distinct `.csv` paths. Fatal output errors can leave partial outputs.

The `elongation-v2` rule retains the provisional shape thresholds: at least 8
measurable candidates, with at least 40% having axis ratio >= 1.7 to suggest review.
The default examines all detected peaks. Coverage and shape are separate: an
optional trailing `--peak-limit 2000` restricts processing and labels the shape
result as describing only that brightest subset. `--peak-limit 0` means all.
Insufficient evidence means too few measurable candidates, not too many peaks.
The CSV field is now `measured_candidates`, replacing v1's misleading `usable_stars`.
Report generation supports both schemas. No images are deleted. See
`docs/COVERAGE.md` for the capped/full comparison and current results.

Generate separate synthetic controls with
`python astro/make_demo.py astro/samples/new-controls`, then analyze that directory
and generate a report with `--title 'Synthetic controls'`. The generator refuses
existing directories and writes known construction labels. Synthetic tests do not
establish real-world accuracy. See `docs/ELONGATION.md` for the algorithm, safeguards
and the measured phone-photo results.


## Review decisions and rejected files

Use **Keep**, **Reject**, or **Revisit** above the preview. These are your decisions;
the algorithm's flag and optional shape assessment remain separate. The exposure
list shows your decision, and its review filter works alongside the issue filter.
**Next unreviewed** clears other filters and finds the next unreviewed exposure.
K / R / V are shortcuts when you are not typing or using another control.
**Clear decision** returns an exposure to Not reviewed and keeps its notes.

Decisions and notes save automatically in this browser, separately for each set
of source image paths. Local-file storage availability depends on the browser;
a visible warning appears if saving fails. **Review backup > Download backup** downloads
astro-review.json as a portable backup. **Review backup > Restore backup** restores that backup
and replaces the current review for the same image sequence. Export first if
you want to retain the current decisions. Moving the HTML or changing browsers
can require importing a backup. Clearing browser data removes browser saves.

### Rejected-image actions

**Linear · original scale** is the default display. Enhanced remains available
in the same menu.

Expand **Rejected images** above the exposure browser. This section contains
only images you explicitly marked Reject, independent of the algorithm flag and
the current exposure filter. Choose an action:

- **Export rejected list** downloads astro-rejected.json with only rejected
  entries and their original paths. It excludes Keep, Revisit and unreviewed images.
- **Put rejected images in a folder** previews the pending moves. Check the count,
  filenames and destination, then choose **Move these N images**. The files move
  into the source folder's Rejected subfolder. Completed moves are marked and are
  excluded from later move requests. Changing a review decision does not undo a
  completed move; restore those files in Explorer if needed.

The full review backup is separate, under **Review backup** in the top bar.

### Open with folder access on Windows

Use **Start AstroTrack.bat** or the **AstroTrack** tab in the main desktop app.
A generated report's matching **.cmd** shortcut also opens the desktop app for
that report. The desktop app owns the local service and shuts it down on exit.

The direct HTML supports reviewing, playback and exporting. Folder moves require
opening the report through AstroTrack. Browser saves belong to that browser and
address. If you already reviewed images in a standalone HTML, download a backup
there and restore it in the desktop-opened review once. The default local port is
8765, so later visits use the same browser storage.

Advanced/manual launch remains available:

~~~bat
.venv\Scripts\python.exe astro\review_server.py "C:\path\to\review.html" "C:\path\to\image-folder"
~~~

The service accepts only paths embedded in its report and inside the selected
image folder. A move requires a one-use preview token, matching file metadata,
and the current local session. Existing targets are refused. It does not expose
a general file browser.

### Optional command-line organizer

To apply an exported rejected list (or a full review backup) without the local app, run from the repository root:

~~~bat
.venv\Scripts\python.exe astro\organize_review.py "C:\path\to\astro-review.json" "C:\path\to\image-folder"
~~~

This is a preview: no images change. Check the listed moves, then repeat with
**--apply** to move only explicitly rejected images into a **Rejected** subfolder.
Keep, Revisit and unreviewed images stay in their original locations. The tool
uses the exact paths from the report: it does not also move corresponding FITS
files, and it does not infer decisions from an algorithm flag or a shape note.

The entire plan is checked for missing sources, duplicate paths, unsupported
files, paths outside the chosen folder and existing destinations before moving.
Subfolders are preserved. Files are copied to exclusively created destinations,
then removed from their original locations only after a successful copy.
A JSONL move log in Rejected records planned and completed moves. If execution
is interrupted, inspect that log and the two locations before retrying; completed
moves are not automatically rolled back. To undo, move files from Rejected back
to their logged original locations in Explorer. Existing files are never replaced.
The report retains its embedded previews after source images move.

Checks for this workflow:

~~~bat
.venv\Scripts\python.exe -m unittest discover -s astro/tests -p test_organize_review.py -v
node astro/tests/review_workflow.cjs astro/astro_report_template.html
.venv\Scripts\python.exe -m unittest discover -s astro/tests -p test_review_server.py -v
~~~

## Experimental sequence explorer

The optional Python sequence viewer treats matching exposures as a width × height ×
frame-index cube. It is separate from the C++ elongation analyzer and does not
change its decisions. Requires `numpy` and `opencv-python` (already in this repo's
Python environment). No additional JavaScript packages or network access are needed.

```powershell
& ./.venv/Scripts/python.exe astro/sequence.py 'C:/path/to/same-target-exposures' 'astro/results/sequence.html'
```

Open the generated HTML. Use the exposure slider or Play, select a comparison
reference, and choose current frame, absolute difference, maximum, minimum,
median, or variation (population standard deviation). Checkboxes select the frames
used in projections. Display gain affects rendering only. An empty selection is
explicitly flagged; projections show black outside the intersection of valid masks.
Reference selection changes the comparison image, not the alignment coordinate system.

Inputs are sorted by filename, not capture timestamps. Unsupported extensions are
skipped; corrupt files and failed alignments are listed as excluded. Use individual
exposures of the same field, orientation, and dimensions, not a collection of
unrelated finished images. Originals are never changed and output overwrite is refused.

For a reproducible demonstration:

```powershell
& ./.venv/Scripts/python.exe astro/make_sequence_demo.py astro/samples/time-sequence
& ./.venv/Scripts/python.exe astro/sequence.py astro/samples/time-sequence astro/results/sequence-demo.html --title 'Synthetic time sequence'
& ./.venv/Scripts/python.exe -m unittest discover -s astro/tests -p 'test_*.py' -v
node astro/tests/sequence_controls.cjs astro/sequence_view.html
```

The six synthetic exposures contain baseline sources, noise, a transient streak,
dimming, elongated sources, and return to baseline, with small known motions.
They demonstrate behavior and are not real-world validation.

Limits: at most 40 supported files, previews default to a 640-pixel long side
(`--size 128..1024`), grayscale encoded brightness converted to 8 bits for browser
use. Alignment uses OpenCV ECC with translation/rotation, anchored to the first
usable file. It requires correlation >= 0.70, valid overlap >= 75%, rotation <=
10 degrees, and translation <= 20% of the preview short dimension. These are
experimental safeguards, not calibrated confidence estimates. Scale changes,
large shifts, distortions, weak sources, and unrelated images are unsupported.
EXIF orientation is ignored; TIFF uses its first decoded image. All source frames
are decoded sequentially; full source decoding still requires memory for one image,
while the browser stores the bounded preview cube. Projection changes are synchronous.

No photometric normalization, scientific stacking export, automatic defect diagnosis,
real-time camera input, or guaranteed star-based registration is provided. Interpolation
and downsampling affect shape. Use the original-resolution C++ analyzer for its
existing candidate-shape measurements. A median can inherit a defect present in most
frames; max/min can be dominated by outliers. These are exploratory views.
