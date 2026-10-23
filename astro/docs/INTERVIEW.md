# Sightline interview — ten-minute demonstration

## 0:00–1:00 — Problem and claim

“Astrophotography produces many exposures. I am exploring a tool that highlights
questionable frames before stacking. The eventual target could be ARM Linux near
the camera, but today I can demonstrate reliable ingestion and explainable
star-shape measurement on Windows.”

This measures candidate elongation, not a confirmed tracking fault. It does not
automatically delete images or claim general classification accuracy.

## 1:00–3:00 — Architecture

Show `FileImageSource -> owned Frame -> analyze -> CSV -> review report`.
The source decodes JPEG/PNG/TIFF and preserves unsigned 8/16-bit values. Acquisition
failure is a record, distinct from exhaustion, so later images continue. Frame
and analysis have no OpenCV types. C++17/CMake provide a portable base; ARM has not
been executed. Serial processing is easy to inspect and measure. The optional
Python/Pillow report renders evidence outside the portable C++ processing core.

## 3:00–5:00 — Controlled demonstration

Open `synthetic-review-v2.html`. Clearly identify these as generated controls.
Show round, elongated and mixed fields, then sparse/no-star cases that abstain.
Elongated controls have known input axis ratio 2.4; sampling and thresholding
explain small differences in the measured ratio.

Explain: subtract local background, isolate a connected bright candidate, calculate
its weighted center and principal widths, then divide long width by short width.
Round is near 1. The provisional rule requires at least 8 usable candidates and
flags a frame when 40% have ratios >=1.7. Thresholds were fixed before phone testing.

## 5:00–7:00 — Real images and the limitation

Open `phone-review-v2.html`. All ten JPEGs decoded and now receive no elongation flag after examining every
detected peak. The earlier 2,000-peak cap caused seven frames to withhold judgment.
Show how user review exposed this coverage problem and prompted a controlled
comparison while keeping shape thresholds unchanged. No flag is not a quality certificate.

Show enlarged candidate crops with axes, coordinates and ratios. Candidates are
not confirmed stars: clouds, foreground texture, noise and phone processing can
interfere. Inspection of faint candidates shows that source selection still needs improvement;
full processing does not establish that every measured patch is a star.

The user used a fixed tripod. Elongation cannot establish a faulty tracking mount;
sky motion and camera processing remain possible explanations. Related edited
files also mean ten files are not ten independent observations.

## 7:00–9:00 — Evidence and tradeoffs

Three CTest suites cover ingestion, recovery, CSV/CLI and quality measurement.
Quality controls include round/rotated elongated sources, 16-bit gradients,
sparse/noisy fields, saturation, hot pixels, a long line, mixed fields, optional coverage limits and full processing.
Report checks cover embedded assets, CSV agreement, escaping, overwrite refusal
and filter/export logic. Full browser layout was not automatically verified:
the browser tool blocks local-file URLs.

Synthetic success demonstrates the calculation, not real-world accuracy. No
independent human labels exist yet. The report starts every human assessment as
unreviewed and can export judgments and notes; do not infer labels from scores.

## 9:00–10:00 — Next experiment

“I would improve sky-source selection, collect independent labels and add another
real exposure sequence before tuning thresholds. I would evaluate by held-out
capture session rather than split near-duplicate edits. Then I would decide
whether ARM optimization or camera integration is the right next investment.”

Moana and DUST remain documented dataset candidates; neither was downloaded or
used to validate this milestone. Their different imaging domains matter.
