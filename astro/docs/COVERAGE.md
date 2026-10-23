# Coverage correction — elongation-v2

The 2,000-peak processing limit previously hid the shape result behind an
“insufficient evidence” decision. The default now examines **all detected peaks**.
Coverage is a separate field; an optional cap explicitly labels the shape result
as applying only to the examined subset. The 1.7 axis-ratio, 40% fraction and
8-candidate thresholds are unchanged.

## The photo you questioned

For `20230921_010311.jpg`:

- Detected peaks: 6,102 in both runs.
- Capped comparison: 2,000 examined, 777 excluded, 1,223 measured;
  298 elongated (24.4%). Shape: no elongation flag, **coverage limited**.
- Full run: 6,102 examined, 3,876 excluded, 2,226 measured;
  703 elongated (31.6%), 1,523 below the elongation threshold.
  Shape: **no elongation flag**, all detected peaks examined.
- Analysis time in this comparison: 76.2 ms capped, 110.5 ms full.
  These are single-run Windows observations, not a rigorous performance benchmark.

All ten phone JPEGs now receive no elongation flag with all detected peaks
examined. That result is not a certification of good images or confirmed stars.

## What changed

The C++ API accepts an optional peak limit; 0 means all and is the default. The
CLI accepts `--peak-limit N` at the end, with or without a candidate CSV. Use
`--peak-limit 2000` to reproduce the sampled comparison.

CSV version is `elongation-v2`. The misleading `usable_stars` field is renamed
`measured_candidates`; new fields are `coverage`, `examined_peaks`, `skipped_peaks`
and `peak_limit`. Decode errors use coverage `not_analyzed`. Sparse detections
still return insufficient evidence, because too few measurable candidates remain.

The report separately displays shape and coverage. Limited results say “sample
only” and disclose examined/skipped counts. Overlays sample up to 120 candidates
across brightness ranks; crops show brightest, middle-ranked and faintest examples
in each shape group, rather than only the strongest examples. Candidate exports
retain all measurements. Human-assessment JSON includes coverage and the actual
analysis version. Legacy CSVs remain readable, with unknown coverage marked as such.

## Inspection and remaining limitation

Eight examples spread across the 1,003 newly measured candidates were inspected
at enlarged scale. Some contain compact visible bright sources; several are low
contrast or textured patches whose identity cannot be established visually from
the crop. This small inspection cannot establish their proportions in the full
set. Removing the cap fixes coverage handling, **not star identification**.

Full processing uses more CPU/memory on dense or noisy frames. The optional cap
remains available for resource-constrained runs, now without concealing coverage.
No thresholds were tuned to force these photos to pass. Originals and old reports
were preserved, so an already-open old report still shows the earlier results.

## Verification

Windows Release build and all three CTest suites passed. New regression checks
cover all-peak processing, limited coverage, independent shape decisions and count
accounting. Invalid/negative CLI limits are rejected. Report checks cover separate
coverage wording, schema handling and filtering/JSON export. Full browser rendering
remains unverified because the browser automation policy blocks local-file URLs.

For current results, open `phone-review-v2.html`; accompanying data are
`phone-elongation-v2.csv`, `phone-candidates-v2.csv` and `phone-capped-v2.csv`.
