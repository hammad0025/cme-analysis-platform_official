# CME Vision Eval Runbook

This document describes the paid evaluation harness in
`scripts/eval_cme_vision.py` and the gated GitHub Actions workflow in
`.github/workflows/eval.yml`. Pair this runbook with
`docs/golden_set_curation.md` for the rationale behind the gold labels
themselves.

## What gets evaluated

The eval grades the production analyzers against
`tests/fixtures/golden_set/manifest.json`:

| Pass            | Module                                            | Method                              | What is scored                                                                 |
|-----------------|---------------------------------------------------|-------------------------------------|--------------------------------------------------------------------------------|
| comprehensive   | `backend.lambda_functions.cme_comprehensive_analyzer` | `CMEComprehensiveAnalyzer.analyze_frame` | Categorical labels (`test_type`, `body_region`, `patient_attire`, `visibility`), the doctor / patient booleans, the `notes` field, and `confidence` paired with `visibility`. |
| behavior        | `backend.lambda_functions.cme_behavior_analyzer`  | `CMEBehaviorAnalyzer.analyze_frame_behavior` | Behavior booleans (`doctor_looking_at_*`, `doctor_facing_patient`, distress / rushed / dismissive flags), plus shared categorical / notes fields when present in `expected`. |
| claims          | `backend.lambda_functions.cme_claim_verifier`     | `verify_all_claims`                  | No-op today. The golden-set schema does not yet declare a `claims` block; the pass prints `[skip] no claims labels in golden set yet` and contributes zero fields. When the schema is extended this pass will light up automatically. |

For each pass we read every `*.jpg` under each clip's `frames/` directory
and only compare the fields present in the clip's `expected` block. Fields
omitted from `expected` are intentional (see the curation doc) and are
never penalized.

### Scoring rules

- **Categorical** (`test_type`, `body_region`, `patient_attire`,
  `visibility`): exact match, case-insensitive.
- **Boolean** (`doctor_facing_patient`, `doctor_making_eye_contact`,
  `doctor_on_phone_or_distracted`, `patient_visible_distress`, behavior
  pass adds `doctor_looking_at_*` and a few more): strict equality.
- **`notes`** (free-text): the eval extracts 3-6 noun-ish phrases from the
  gold note (split on punctuation, drop a small stopword list, keep tokens
  of length >= 4) and passes when at least 50% of those phrases appear
  case-insensitively in the model's `notes` output. Reviewers can tune
  the 50% threshold in `scripts/eval_cme_vision.py::compare_notes`.
- **`confidence`**: passes when the reported confidence >= 0.5 AND the
  reported `visibility` matches the gold `visibility`. This catches the
  failure mode where the model is overconfident on an obscured frame.
- **List-valued fields** (`technique_issues`, `equipment_visible`):
  subset match - every gold token must appear in the actual list.

The frame-level `frame_pass_rate` is `passed / evaluated`. The overall
`pass_rate` rolls those up across every (clip, frame, pass, field) tuple.

## Running locally

The default invocation is Anthropic-only and requires only one secret:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/eval_cme_vision.py
```

This:

1. Validates `tests/fixtures/golden_set/manifest.json` against
   `tests/fixtures/golden_set/schema/manifest.schema.json` (via
   `jsonschema` if installed, otherwise a minimal structural check).
2. Lands per-frame outputs under
   `eval_runs/<utc-timestamp>/raw/<pass>/<clip_id>/<frame>.json`.
3. Writes `eval_runs/<utc-timestamp>/eval_summary.json` (machine-readable)
   and `eval_summary.md` (human-readable).
4. Exits 0 when the overall `pass_rate >= 0.70` (the default
   `--threshold-pass-rate`), otherwise 1.

### Useful flags

- `--dry-run` prints the planned set of `(clip, pass, frame)` tuples and
  exits 0. No API calls. Used by CI smoke tests and by anyone vetting the
  manifest expansion.
- `--passes comprehensive` runs only the comprehensive pass.
- `--providers anthropic,openai` will evaluate the primary provider
  (`anthropic`) and is wired for future per-provider grading; the current
  scorer only grades the primary provider.
- `--resume` skips per-frame outputs that already exist on disk under
  `<output-dir>/raw/<pass>/<clip>/<frame>.json`. Useful when an earlier
  run died partway through.
- `--compare-to <eval_summary.json>` grades the run as a delta against an
  earlier summary. The eval exits non-zero when the pass rate regresses
  by more than `--threshold-regression` (default 0.05 = 5 percentage
  points).

### Cost expectation per run

The v1 golden set is 10 clips, 13 frames, 2 passes per frame. That is
**26 vision API calls** plus a handful of (currently zero) text-only
claim-verifier calls.

Per the `PROVIDER_PRICING` table in
`backend/lambda_functions/vision_client.py`:

- Anthropic Claude Sonnet 4: ~$3/M input tokens, ~$15/M output tokens.
  A single frame analysis call typically uses ~1500 input + ~600 output
  tokens, so each call is roughly $0.014. **26 frames ~ $0.35-0.40 per
  full eval run** in the steady state.
- OpenAI `gpt-4o`: $2.50/M input + $10.00/M output. Order-of-magnitude
  the same.
- Gemini `gemini-2.5-pro`: $1.25/M input + $10.00/M output. Slightly
  cheaper.

Always read the `totals.estimated_cost_usd` field in
`eval_summary.json` for the exact number; the eval sums
`AnalyzeResult.usd_cost_estimate` over every call.

## Triggering the paid CI workflow

`.github/workflows/eval.yml` (named `Eval (paid)`) runs in one of two
ways:

1. **Add the `eval-ok` label to a pull request.** The label is the only
   gate; pushes to the PR branch without the label do nothing. Toggling
   the label off and back on retriggers the run via the `labeled` event.
2. **Manually from the Actions tab** via `workflow_dispatch`. Inputs:
   - `providers` (default `anthropic`)
   - `threshold-pass-rate` (default `0.70`)
   - `compare-to-main` (default `true`; pull_request only)

The workflow:

- Checks out the PR head, installs `backend/requirements.txt` plus
  `jsonschema` and `anthropic`.
- Runs the eval against the PR head with the chosen threshold.
- When `compare-to-main` is true and the trigger is a PR, attempts a
  second run against `origin/main` via `git worktree`, then re-runs the
  head eval with `--compare-to baseline_summary.json` to produce a delta
  block. This step is `continue-on-error: true`; if the baseline build
  is brittle (missing dependency on the base branch, transient API
  outage, etc.), the workflow falls through to the absolute eval and
  documents that in the job log.
- Uploads `eval_summary.json`, `eval_summary.md`, and the `eval_runs/`
  directory as build artifacts.
- Posts (or updates) a sticky comment on the PR containing
  `eval_summary.md`. The sticky marker is the comment-level HTML comment
  `<!-- cme-eval-sticky -->`.
- Fails the job when the eval script exits non-zero.

The cheap CI workflow (`.github/workflows/ci.yml`) is unchanged. It runs
pytest on every push and pull_request to `main` / `master`, makes zero
API calls, and is the gate that should stay green at all times.

## Interpreting the output

`eval_summary.json` is the source of truth. Key fields:

- `verdict`: `pass` or `fail`. A `fail` triggers a non-zero exit and a
  red check.
- `verdict_reasons`: human-readable list of why the run failed (e.g.
  `"overall pass rate 0.62 below threshold 0.70"`).
- `totals`: high-level rollup with `pass_rate`,
  `fields_evaluated`, `fields_passed`, `frames`, `clips`,
  `estimated_cost_usd`.
- `by_clip`: per-clip rollup with per-frame breakdown including the raw
  field-level pass/fail list and a short `raw_response_excerpt` for
  spot-checking the model output.
- `by_field`: per-field rollup. Look here first when triaging a regression
  - a single field tanking from 100% to 30% tells you exactly which
  prompt or label needs attention.
- `baseline`: if `--compare-to` was set, the full baseline summary is
  embedded so the delta is computed from a known reference.
- `prompt_versions`: `technique_frame`, `behavior_visual`, and
  `claim_verifier` versions in this run. Bump these whenever the prompts
  change so eval diffs are attributable.
- `manifest_sha256`: hash of the manifest file. If this changes between
  runs, the gold labels themselves moved.

`eval_summary.md` is the same data shaped for the PR comment: a clip
table, a field table, the top-20 failures, and (when a baseline was
provided) a delta section. The PR comment is sticky so reruns overwrite
the previous comment rather than piling up.

## Known limitations

These limitations all live one layer down in the golden set. See
`docs/golden_set_curation.md` for the full discussion:

- **Single-case sample.** All v1 clips come from the Osborn 2021-03-09
  case. Lighting, room layout, and clothing for that one exam may bias
  the eval.
- **No gown coverage.** The Osborn patient never wore a gown; the v1 set
  cannot regression-test the `patient_attire = "gown"` path.
- **No equipment coverage.** The Osborn examiner used no goniometer or
  reflex hammer; we test the absence of equipment, not its detection.
- **No reflex / coordination / romberg / cranial_nerve clips.** Those
  tests either do not appear in the source case or only appear at low
  confidence.
- **Behavior labels rest on single frames.** Fast-changing states like a
  one-frame blink are inherently lossy. Future labels should come from
  the planned HITL workflow with motion context.
- **No claim labels yet.** The schema does not declare a `claims` block
  on each clip; the claims pass cleanly no-ops until that is added.

A regression against the v1 golden set therefore answers "did we get
worse on the cases we already curated", not "did we get worse on CME
exams in general". Use it as one signal among several.
