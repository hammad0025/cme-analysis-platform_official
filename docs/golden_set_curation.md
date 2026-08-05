# Golden Set Curation (v1)

This document describes how the v1 evaluation clips under `tests/fixtures/golden_set/`
were selected and labeled. It exists so that future reviewers can tell at a glance
whether a regression against the golden set reflects a real model regression or a
weakness in the gold labels themselves.

## Source material

All v1 clips are drawn from a single real case: **Osborn, 2021-03-09** (defense
CME of Wendy Scammon by Dr. Brett Osborn DO). The source artifacts are:

- Frames: `cme_projects/osborn_2021_03/analysis_run_halfsec/frames/` (2617 frames
  sampled at 0.5s for a ~21.8 minute video).
- Existing analyzer output, used **as a reference, not as ground truth**:
  - `cme_projects/osborn_2021_03/analysis_run_halfsec/comprehensive/comprehensive_frame_analyses.json`
  - `cme_projects/osborn_2021_03/analysis_run_halfsec/behavior/behavior_analysis.json`
  - `cme_projects/osborn_2021_03/analysis_run_halfsec/comprehensive/analysis_report.txt`

The `cme_projects/Green_Tracy/` directory contains frames as well but they were
not used in v1; the Osborn run has both higher frame count and a complete
side-by-side `behavior` + `comprehensive` analysis to cross-check against, so
limiting v1 to a single case keeps the bootstrap manageable. Adding clips from
`Green_Tracy` (and the Stephen Jacobs MD video) is the obvious next step for v2.

## Clip selection criteria

Each clip is meant to exercise a distinct dimension of the analyzer output so
that a regression in any one direction shows up loudly:

- **Behavior signals** (engagement, distraction, eye contact, distress).
- **Test taxonomy** (`conversation`, `strength`, `rom`, `gait`, `palpation`,
  `sensory`, `none`).
- **Attire flags** (`regular_clothes`, `partial`).
- **Visibility paths** (`full`, `partial`, `obscured`).
- **Technique red flags** (`testing_through_clothing`, `no_goniometer`,
  `patient_not_in_gown`).

Within those buckets, individual frames were chosen by:

1. Filtering the Osborn comprehensive JSON for the target `test_type` /
   `visibility` / behavior flag.
2. Preferring frames with `confidence >= 0.7` from the existing analyzer, so the
   moment was likely well-lit and unambiguous on its face.
3. Cross-checking the 2 frames before and 2 frames after the candidate. Where
   the surrounding frames showed wildly different `test_type` or behavior
   flags, the candidate was rejected as a noisy moment. The `patient_distress`
   and `rom_no_goniometer` clips include both the central and an adjacent
   frame to confirm the labeled signal is sustained.
4. Manual re-inspection of every chosen frame against the analyzer's
   `notes` field and adjacent frames to ensure the call survives a defense-side
   "this is a single noisy frame" objection.

## How labels were derived

Labels in `manifest.json`'s `expected` blocks were derived as follows:

1. The existing analyzer output was read **as a starting reference** for each
   chosen frame: `test_type`, `body_region`, `patient_attire`, `visibility`,
   the booleans (`doctor_facing_patient`, `doctor_making_eye_contact`,
   `doctor_on_phone_or_distracted`, `patient_visible_distress`), and
   `technique_issues`.
2. Each call was then re-evaluated against (a) the analyzer's own free-form
   `notes` field for the frame, (b) the same fields on the 2 adjacent frames
   on either side, and (c) the case-level `analysis_report.txt` which summarizes
   the human-relevant red flags for the Osborn case (no goniometer, testing
   through clothing, patient not in gown, doctor on phone, dismissive
   gestures, distress moments).
3. **Where a categorical decision could not be defended without leaning on
   the analyzer's own confidence, it was omitted from `expected`.** The
   `obscured_hallway` clip is the clearest example: nothing about the doctor
   or the patient is visible, so only `test_type`, `body_region`, `visibility`,
   and `notes` are populated. This is deliberate: a v1 golden label with three
   strong fields is more useful for regression testing than ten guessed ones.
4. The per-clip `notes` field is in plain English and explains why each label
   was chosen, so the manifest is reviewable without re-running the analyzer.

This is **explicitly not** auto-accepting the analyzer's calls. The whole
point of a golden set is that it must be independent of the system under test;
otherwise the eval becomes a self-consistency check. The analyzer's output was
useful as a "rough draft" of labels - particularly for narrowing 2617 frames
down to a few candidates per scenario - but every label in `manifest.json` is
one a human reviewer agreed with after looking at the frame and its context.

## Vocabulary notes

Labels use the production analyzer's vocabulary, defined in
`backend/lambda_functions/prompts/production.py`:

- `test_type`: `strength`, `sensory`, `reflex`, `rom`, `gait`, `coordination`,
  `romberg`, `palpation`, `cranial_nerve`, `conversation`, `none`.
- `body_region`: `neck`, `shoulder`, `arm`, `hand`, `back`, `hip`, `leg`,
  `foot`, `face`, `full_body`, `none`.
- `patient_attire`: `gown`, `regular_clothes`, `partial`. The roadmap-spec
  document referred to a `mixed` / `unclear` shape; the production prompt uses
  `partial` / (omit), so the labels follow the production prompt to keep
  regression diffs directly comparable to analyzer output.
- `visibility`: `full`, `partial`, `obscured` (production also emits `unknown`
  but no v1 clip required it).
- `technique_issues`: free-form list, but in practice drawn from the prompt's
  enumerated set: `testing_through_clothing`, `no_goniometer`,
  `improper_romberg`, `patient_not_in_gown`, `rushed_examination`,
  `incomplete_test`.

## Bootstrap limitations

This is a **v1 set bootstrapped from a single case by a non-clinical reviewer**.
Known limitations:

- All clips come from one examiner and one patient, so the model could overfit
  to lighting, room layout, and clothing for that case if the golden set is the
  only thing it is trained or tuned against.
- No clip exercises `test_type` values `reflex`, `coordination`, `romberg`, or
  `cranial_nerve`, because those tests either do not appear in the Osborn run
  or only appear at low confidence / partial visibility.
- No clip exercises `patient_attire = "gown"`. The Osborn case never had the
  patient in a gown - that is itself a documented red flag for this case but it
  means the gold set cannot regression-test the gown path.
- No clip contains visible equipment (goniometer, reflex hammer) because the
  Osborn examiner did not use any. The `rom_no_goniometer` clip therefore tests
  the **absence** of equipment, not its detection.
- Labels for behavior booleans rest on a single still frame; for fast-changing
  states (e.g. a one-frame blink, a half-turned head) this is inherently lossy.
  Future labels should come from human reviewer corrections collected via the
  planned HITL workflow (roadmap item D1), which lets reviewers see motion
  context.

When v2 lands those gaps should be filled with clips from `Green_Tracy`,
`Gadson_Alethea`, and the Stephen Jacobs MD case, and labels should be
collected from at least two independent reviewers per clip with inter-rater
agreement tracked.

## Clips

| clip_id                          | source case        | source frame(s)        | source timestamps    | labeled fields | scenario                                                      |
|----------------------------------|--------------------|------------------------|----------------------|----------------|---------------------------------------------------------------|
| conversation_eye_contact         | osborn_2021_03     | 0103, 0104             | 51.0s, 51.5s         | 9              | Interview phase, doctor facing patient with eye contact.      |
| doctor_taking_notes              | osborn_2021_03     | 0102                   | 50.5s                | 9              | Doctor turned to desk writing, no eye contact, not on phone.  |
| doctor_on_phone                  | osborn_2021_03     | 0111                   | 55.0s                | 9              | Doctor on phone during exam time while patient waits.         |
| patient_distress                 | osborn_2021_03     | 0349, 0350             | 174.0s, 174.5s       | 9              | Patient visibly emotionally distressed, doctor not engaging.  |
| strength_test_through_clothing   | osborn_2021_03     | 0181                   | 90.0s                | 9              | Strength testing of the arm with patient in street clothes.   |
| rom_no_goniometer                | osborn_2021_03     | 1885, 1886             | 942.0s, 942.5s       | 9              | Leg ROM assessment with no measurement device visible.        |
| gait_in_street_clothes           | osborn_2021_03     | 1493                   | 746.0s               | 8              | Hallway gait test, patient in street clothes.                 |
| palpation_neck                   | osborn_2021_03     | 1687                   | 843.0s               | 8              | Two-handed neck palpation through street clothes.             |
| sensory_through_clothing         | osborn_2021_03     | 1907                   | 953.0s               | 8              | Sensory testing over a cardigan sleeve, partial gowning.      |
| obscured_hallway                 | osborn_2021_03     | 1487                   | 743.0s               | 4              | Empty hallway transition shot, no doctor or patient visible.  |

Total: 10 clips, 13 frames, ~764 KB on disk.
