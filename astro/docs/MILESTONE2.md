# Milestone 2: explainable star-elongation review

## Accepted direction

Interview credibility is the current priority, ahead of a complete prototype.
Demonstrate an explainable measurement of elongated stars, with questionable
frames flagged for human review. Do not automatically discard images.

## Supplied images inspected

Folder: `C:\Users\GAME\Downloads\Photos-1-001`.
The user confirms the phone was fixed on a tripod. Night/astrophotography mode
has not been confirmed.

- 10 JPEGs and 6 DNG files; originals were read only.
- Existing Milestone 1 executable processed all 10 JPEGs successfully, with
  results in `phone-photo-baseline.csv`. DNG is unsupported and was skipped.
- Images contain visible stars, variable cloudy/bright backgrounds, foreground
  obstructions and some apparent repeated/edited views.
- EXIF capture timestamps repeat across several filenames, including rotated
  images. Do not count these as independent observations without checking provenance.
- JPEG EXIF reports exposure times of approximately 3.9–18 seconds. These fields
  do not establish the full capture/processing history of a phone image.
- Full-resolution central crops of `20230922_211143.jpg` and
  `20230922_212131.jpg` show compact bright points and irregular/extended points
  against uneven backgrounds. This is visual inspection, not a validated quality
  label or proof of tracking failure.

## Claim boundary

A fixed tripod does not track the sky. Star elongation may be consistent with sky
motion during exposure; a shape measurement alone cannot distinguish that from
camera movement, optical effects or image processing. Report observable elongation
and evidence, not a confirmed tracking-mount diagnosis.

These photos are suitable development/demo inputs. They are too few, and too
interrelated, to establish general rejection accuracy. Keep a separate real
sequence for later validation; do not invent accuracy claims from this collection.

## Next implementation contract

1. Select candidate stars above a locally estimated sky background, with explicit
   safeguards against saturated blobs, image boundaries and obvious long lines.
2. Measure candidate elongation and summarize evidence across multiple candidates.
3. Report three outcomes: review suggested, no elongation flag, or insufficient
   evidence. The last two must not be presented as certification of image quality.
4. Produce a small visual evidence report showing the measured candidates and
   enlarged examples, alongside the CSV metrics and declared provisional thresholds.
5. Test round and elongated synthetic sources, noise/background changes, sparse
   fields and corrupt files. Clearly distinguish controlled synthetic tests from
   the user's real photographs.

The interview acceptance criterion is a reproducible example that explains what
was measured, why a frame was flagged, and where the method remains uncertain.
No percentage-accuracy target is justified until independent labels exist.

This turn inspected inputs and ran the existing pipeline; it did not implement
the new elongation detector.

Implementation update (2026-10-22): Milestone 2 is now implemented. See ELONGATION.md for measured outcomes and INTERVIEW.md for the updated walkthrough. The earlier inspection-only statement above describes the scope-setting turn.
