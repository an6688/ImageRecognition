# First recorded-video experiment — 2026-10-20

The video demo is separate from the photo library. It uses the existing ONNX
Medium detector plus BoT-SORT with sparse optical-flow camera motion compensation.
The two supplied drone clips are development examples, not a labeled evaluation.

## Overhead road clip

Source: `12166977-hd_1080_1920_60fps.mp4`, 1080x1920, 60 fps, 18.53 seconds.
At 10 analyzed frames per source second, 186 frames were processed.

- Original orientation: only 9 frames contained confirmed tracks. PyTorch also
  confused cars with phones in sampled overhead frames; increasing resolution to
  1280 and trying native crops did not solve the initial-frame detection problem.
- Counterclockwise 90-degree detector view: 161/186 frames contained confirmed
  tracks. Several IDs lasted around 10 seconds of observations. This does not
  establish identity correctness: boxes still disappear and IDs can fragment.
- The rotated run produced 25 observed IDs, which must NOT be reported as 25
  unique vehicles. Parked cars are included, and a vehicle can receive new IDs.
- Approximately 34 seconds processing time, 5.5 processing FPS. Startup excluded.
  Saved output plays at the source pace using a 10 fps output stream, without audio.
- Visual checks at 0, 5, 10 and 17 seconds confirmed mapped boxes on cars, but also
  substantial missed detections later in the clip. Rotation is exposed as a user
  choice, not claimed as a universal fix or automatically selected per frame.

Local evidence: `data/videos/20261020T171447977384Z/` (rotated) and
`data/videos/20261020T171218298563Z/` (original).

## Wider drone clip

Source: `11512441-hd_1080_1920_60fps.mp4`, actual 720x1280, 60 fps, 24.02 seconds.
Original orientation produced tracks in 161/241 sampled frames, with 85 observed
IDs and considerable fragmentation. About 6.5 processing FPS. This clip remains
a harder development check, not a successful unique-vehicle counting evaluation.
Local evidence: `data/videos/20261020T171311899696Z/`.

## What the measurements mean

Frames with tracks is a coverage observation, NOT recall or accuracy. No ground
truth boxes/IDs exist yet. These single runs establish that the pipeline executes;
they are not a controlled timing comparison. The original/rotated differences
show why drone footage needs its own detection evaluation. The next quality work
should label a short segment, measure misses and ID switches, and evaluate a
better detector or augmentation strategy against an unchanged validation clip.

Validation: 39 tests passed, including tracker continuity/recovery on synthetic
boxes, per-clip reset, rotation coordinates, cancellation, output timing and GUI
worker events. Shared ONNX changes preserved detections on all 50 photo benchmark
images within the existing numerical tolerance. Source videos were not modified.
