# Astro Image Analyzer — Milestones 1 and 2

A standalone, sequential C++17 command-line pipeline inside the existing Python
photo-organizer repository. No Python runtime, models, UI, database, camera SDK,
or PhotoPeople dependency is required by this executable.

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

Open the HTML report in a browser. It embeds the overview images and candidate
crops, supports filtering, and lets a reviewer export manual assessments as JSON.
There are no network requests or uploads; reviewer edits last only until the tab
is closed unless exported. The report script requires Pillow (already a dependency
of the existing app); the C++ executable remains independent of Python.
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
