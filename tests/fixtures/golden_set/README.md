# Golden set (evaluation clips)

Use this folder to **measure** vision quality over time without guessing.

## Layout

- `manifest.json` — list of clips, path to extracted frames (relative to this directory), and `expected` field values from human review.
- One folder per clip, e.g. `example_rom/frames/*.jpg`.

## Curating real clips

1. Export a **30–120s** segment (FFmpeg) covering the scenario you care about.
2. Extract frames at the same `--interval` you use in production.
3. A reviewer fills `expected` with **minimal** labels (e.g. `test_type`, `patient_attire`, `goniometer_visible` if you add that field).
4. Run `python scripts/eval_cme_vision.py --manifest tests/fixtures/golden_set/manifest.json`.

Do not commit **PHI** or privileged video; keep real golden data internal or redacted.
