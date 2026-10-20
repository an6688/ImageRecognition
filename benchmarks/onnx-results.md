# Medium FP32 ONNX experiment — 2026-10-20

The application still uses PyTorch. This experiment adds an optional exporter and
benchmark backend, not an application runtime migration.

## Protocol

50 development photos, 3 seeded shuffled passes per run, batch 1, CPU, FP32,
640x640 square letterboxing, confidence 0.50, identical Ultralytics preprocessing
and postprocessing. Both runtimes use 8 intra-op threads and 1 inter-op thread;
ONNX Runtime uses sequential CPU execution. Startup and warm-up are excluded from
per-photo times. The full pet pipeline here includes decoding and filtering, but
excludes human recognition, hashing, database writes and UI work.

## Observations

- Fresh PyTorch control: median 212.63 ms/photo; mean 235.32 ms; p95 447.00 ms.
  Inference-only median: 190.65 ms.
- ONNX first run: median 150.75 ms/photo; mean 176.75 ms; p95 419.00 ms.
  Inference-only median: 130.57 ms.
- ONNX confirmation: median 149.68 ms/photo; mean 176.31 ms; p95 425.85 ms.
  Inference-only median: 128.25 ms.
- The fresh comparison shows about 29–30% lower median per-photo latency with
  ONNX (about 1.4x). An earlier PyTorch control before an overnight interruption
  measured 162.31 ms, so host conditions materially affect the apparent gain.
  This is a desktop observation, not a guaranteed speedup or embedded result.
- All four runs had identical photo hashes/labels, per-photo category predictions
  and detection counts on every pass. Each scored 41/50 exact category matches.
  Dogs: 20/25 detected, one false-positive photo. Cats: 8/10 detected, three
  false-positive photos. These are category-presence metrics, not box accuracy.
- The earlier PyTorch/first ONNX comparison had maximum absolute confidence
  difference 0.00000149 and normalized box-coordinate difference 0.000000358.
- PyTorch checkpoint: 40,684,120 bytes (38.8 MiB). ONNX FP32: 80,621,881 bytes
  (76.9 MiB). This export increased file size; it was not quantized.

This small development collection is not held out and includes similar photos.
No model was trained and no threshold was tuned in this experiment. ONNX preserved
existing mistakes as well as correct detections. The default remains unchanged;
a production switch should preserve the app's existing padding behavior and test
packaging, startup and memory as well as representative detection results.

## Local evidence

Raw manifests, predictions, timings, versions and model hashes are in ignored
`data/benchmarks/` directories (personal image paths stay outside Git):

- Earlier PyTorch: `20261020T011520262319Z`
- ONNX first: `20261020T164709816108Z`
- Fresh PyTorch: `20261020T164745691780Z`
- ONNX confirmation with verified runtime settings: `20261020T164852837897Z`

See the README for export and reproduction commands. ONNX model validation,
31 regression tests, and dependency compatibility checks passed.
