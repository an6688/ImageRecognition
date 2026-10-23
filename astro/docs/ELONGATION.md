Current version: elongation-v2 examines all detected peaks by default and reports coverage separately. See COVERAGE.md for current behavior and results. The v1 design and initial run below are retained as historical context.

# Milestone 2 — explainable, provisional elongation measurement

## Purpose and scope

Support an honest interview demonstration: show measurable round versus elongated
sources and explain when a real image is too ambiguous. Flag for human review;
never delete or automatically reject an image. This is shape measurement, not a
diagnosis of tracking error, star classification, or calibrated astrophotometry.

The implementation is C++17 in `src/quality.cpp`, independent of OpenCV, filesystem
access and Python. Analysis owns the result; decoding and CSV writing remain
separate. No threads or camera interfaces were introduced.

## Method (elongation-v1)

1. Estimate sky median and robust noise (1.4826 × median absolute deviation) in
   64×64 tiles, sampling every other pixel. Noise has a one-input-code floor.
2. Find deterministic 5×5 local maxima, at least 5 noise units and 2/255 normalized
   intensity above the tile background. Image-edge candidates lack a full window
   and are skipped. Retain at most 2,000 strongest peaks; exceeding the limit
   makes the frame decision insufficient evidence, not a clean bill of health.
3. Re-estimate background/noise from the outer three-pixel ring of a 21×21 window.
   Flood the connected source above background + max(3 noise units, 10% contrast).
   Measure only that connected region, rather than all bright pixels in the window.
4. Exclude regions touching the window boundary, saturated pixels (>=98% of the
   code range), fewer than 6 connected pixels, minor-axis sigma below 0.65 pixels,
   major-axis sigma above 5 pixels, centroids more than 3 pixels from the peak,
   or axis ratios above 6. Suppress later peaks within 20 pixels of an accepted
   candidate to avoid repeatedly measuring the same source.
5. Compute background-subtracted weighted centroid and covariance. Square roots
   of its two eigenvalues give major/minor widths. Their ratio is elongation;
   orientation comes from the covariance cross term. This standard definition is
   documented by [Photutils SourceCatalog](https://photutils.readthedocs.io/en/stable/api/photutils.segmentation.SourceCatalog.html).
   We implement the calculation directly; Photutils is not a dependency.
6. At least 8 measured candidates are required. At least 40% with ratio >=1.7
   produces `review_suggested`; otherwise `no_elongation_flag`. Sparse or capped
   detections produce `insufficient_evidence`. Decode failures are `not_analyzed`.

Thresholds were set before the first run on the user's phone photos and were not
changed to produce a desired outcome. They are engineering starting points, not
scientifically validated selection criteria. Fixed pixel windows are scale-sensitive.
Very long trails may be excluded, yielding insufficient evidence, rather than a
positive elongation flag. When enough other sources remain, those exclusions can
also hide defects: no flag is explicitly not a whole-image quality certification.
Close pairs, textured foregrounds, clouds, phone sharpening and correlated noise
can contaminate candidates. No sky mask, source deblending, learned classifier,
spatial coverage rule, or frame registration is implemented. Alignment consistency
of elongation angles is not used to infer motion cause.

## Actual phone-photo run — 2026-10-22

Input: 10 JPEG files from `C:\Users\GAME\Downloads\Photos-1-001`.
Six DNG files were skipped by the existing source adapter; originals were unchanged.
The user confirmed a fixed tripod. Night-mode/multi-frame processing is unknown.

- All 10 JPEGs decoded and completed analysis.
- 7 returned insufficient evidence because the initial-peak limit was exceeded.
  Uneven backgrounds and many local peaks expose a real limitation of this simple
  detector. Do not interpret their brightness-selected subsets as whole-frame stats.
- 3 returned no elongation flag: `20230922_212131.jpg`, its `(1)` variant, and
  `20230922_212601.jpg`. Their elongated-candidate fractions were approximately
  22.9%, 22.9%, and 32.0%. These are algorithm outputs, not human quality labels.
- 0 returned review suggested. We did not adjust thresholds to force a positive.
- Several files share capture times/appear to be edits, so ten files do not mean
  ten independent exposures. There is no accuracy percentage or held-out evaluation.

The report includes full-image overlays and six example crops per frame, selected
by contrast within elongated/other groups. It shows at most 120 overlay markers
for readability. Full measurements remain in the candidate CSV. Rendered images
use stored-raster orientation, not EXIF display orientation, to match coordinates.
For 16-bit report previews only, values map to 8-bit by dividing by 256; the C++
analysis retains 16-bit samples. Human labels start unreviewed and can be exported.

## Evidence and interpretation

Three CTest suites cover the original pipeline, quality measurement and CLI.
Quality controls include known Gaussian round/elongated/rotated sources, 16-bit
input, brightness gradients, sparse fields, noise, saturated sources, hot pixels,
long lines, the 40% mixed-field threshold and the candidate-limit guard.

Five separate synthetic demo images exercise the visible report: round, elongated,
mixed, sparse and no-star fields. Expected decisions are stored beside those
images. This establishes behavior on controlled inputs only.

For a fixed tripod, apparent sky movement is plausible; elongation alone does not
prove a faulty tracking mount. The next useful investment is better separation of
sky sources from texture plus independent human labels and another real sequence.
Do not tune a flagger to this small set and then call the same set validation.
