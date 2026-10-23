# Real-world test imagery

Sources and terms checked 2026-10-22. No image datasets have been downloaded or
redistributed as part of this milestone. Freely downloadable is not the same as
openly licensed. Keep a manifest with original URL, creator, license, filename,
capture sequence, filter/exposure, checksum and every conversion applied.

## Best ground-based starting point: Moana

[Moana open datasets](https://erellaz.com/moana/open-datasets/) links its license
to [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and requests attribution
to **Moana Project**. Preserve credit, license link and modification notices.
These are real ground-based raw exposures, but the main library has undergone
SubFrameSelector and visual quality control: it is not a labeled reject-frame set.

- [WASP-36b](https://erellaz.com/moana/open-datasets/exoplanet-wasp-36b/):
  98 one-minute red-filter exposures, plus calibration frames. Good for repeatable
  sequential ingestion and brightness variation. Keep science frames separate
  from calibration frames.
- [M45](https://erellaz.com/moana/open-datasets/m45/): four download parts and
  calibration data; over 1,000 minutes of RGB integration, prominent stars and
  diffraction patterns. Pick one filter/session for a consistent test sequence.
- [Defects examples](https://erellaz.com/moana/open-datasets/difficulties-defects-and-disappointment/):
  demonstrates frame-to-frame bad seeing and optical reflections. It presents a
  video/examples, not a verified downloadable raw sequence labeled for tracking
  blur. Seeing-induced bloating is also distinct from tracking elongation.

Moana's raw FITS files need conversion to unsigned 16-bit grayscale TIFF/PNG for
this milestone. Use the same fixed scaling for every frame, record clipping and
scaling, and retain originals. Do not independently auto-stretch each frame if
comparing brightness. FITS ingestion belongs to a later source adapter.

## Best documented blur/jitter sequence candidate: DUST

[DUST Zenodo record v2](https://zenodo.org/records/20255672) and the
[authors' dataset page](https://vithurshansuthakar.github.io/DUST/) describe 1,378
real on-orbit near-infrared frames across 22 sessions, with motion blur, jitter,
stray light and lens flare. PNG images are organized by session; point the CLI
at one session's `Images` directory, not its annotations or thresholded outputs.
The archive is about 861 MB. No download was needed to verify the description.

Zenodo's [record API](https://zenodo.org/api/records/20255672) reports license
`cc-by-4.0` (the rendered page did not expose the license name). Attribute Suthakar,
Kunalakantha, Lee and Sohn, link the license, mark changes, and cite the dataset
and [data paper](https://doi.org/10.1038/s41597-026-07736-9) as requested.

This is star-tracker imagery from a spacecraft, not terrestrial long-exposure
astrophotography. Its RSO/star annotations do not constitute good/bad stacking
labels. Inspect frames and create separately documented quality labels before
using it to validate future tracking-rejection accuracy.

## NASA / ESA / STScI options

[MAST search](https://mast.stsci.edu/portal/Mashup/Clients/Mast/Portal.html) offers
real mission observations. Select individual exposures from the same target,
instrument/filter and visit, rather than combined mosaics. Most mission data are
FITS and need a documented conversion for this CLI. This is useful for science
imagery, but not automatically representative of backyard tracking failures.

[MAST data-use policy](https://archive.stsci.edu/publishing/data-use): most hosted
data are public domain; some community products are CC BY 4.0; exclusive-access
and copyrighted collections have separate terms. DSS/Guide Star Catalog data have
commercial-use restrictions. Check the chosen collection and its acknowledgments.

[ESA/Hubble educational datasets](https://esahubble.org/projects/fits_liberator/eagledata/)
are convenient FITS processing examples, but multi-filter examples and processed
composites are not a bad-frame exposure-sequence benchmark.

[NASA media policy](https://www.nasa.gov/nasa-brand-center/images-and-media/) is
not a blanket license for every picture on a NASA page: check third-party credits,
logos and endorsement restrictions. In particular, do not assume an amateur
astrophotograph featured on a NASA page is NASA-owned. Prefer provenance from
the actual dataset rather than a press-image gallery.

## Practical validation plan

Start with a small single-session sequence and label it manually before examining
algorithm scores. Add a known empty file and obvious corrupt bytes to copies in
a separate test directory; never damage originals. Synthetic streak/blur variants
can validate a later metric's direction, but label them synthetic and do not
present them as real tracking failures. Hold out complete sessions when testing
future thresholds to avoid near-duplicate leakage. Milestone 1 validates plumbing
only: it has no quality classifier, stacking, or accuracy claim.
