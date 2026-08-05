# CME Analysis Runbook

End-to-end steps to take a CME video + doctor's report and produce:

1. `STANDARD_CME_REPORT.pdf` / `.html` (the deliverable report)
2. A linked live session at `https://<app>/sessions/{session_id}` with the video, "Report vs video" verdicts, named-test index, and three-way ledger.

All commands run from the repo root. Costs are estimated up front and every paid step is gated.

---

## 0. Prerequisites

- `.env` (or exported env vars) with:
  - `ANTHROPIC_API_KEY` — vision + LLM verifier (Tim's account for client runs)
  - `PERPLEXITY_API_KEY` — literature research (Tim's enterprise account; opt-in via `--with-research`)
  - AWS credentials with access to the `cme-analysis-recordings-*` bucket and `cme-sessions` table (for session linking)
- `CME_ALLOW_LOCAL_ANALYSIS=1` must be set to run any paid local analysis (hard cost gate).
- `ffmpeg` installed (frame extraction), `python3` with `backend/requirements.txt` installed.
- Validate before starting:

```bash
python3 scripts/validate_env.py
```

HIPAA note: client-facing runs go through the AWS pipeline where Macie anonymizes PII before AI calls. Perplexity is on Tim's enterprise license (no training on our data). Do not commit videos, reports, or `.env`.

## 1. Set up the case directory

```bash
CASE=cme_projects/<Lastname_Firstname>
mkdir -p "$CASE"
# Put the CME video and the doctor's report (PDF or .txt) in $CASE
```

## 2. Estimate cost (free)

```bash
python3 scripts/estimate_cme_cost.py "$CASE/video.mp4" --preset standard
```

Presets: `standard` (5s interval), `high`, `max`, `half_second`. A ~40-minute video at `standard` is roughly $14 in vision calls; `half_second` is ~10x that. Get a yes on the number before proceeding.

## 3. Extract claims from the doctor's report (cheap, one LLM call)

```bash
python3 scripts/extract_report_claims.py "$CASE/report.txt" \
  --out "$CASE/claims.json" \
  --atomic-out "$CASE/claims_atomic.json"
```

- Accepts a text file, PDF, or `--text "..."`. Use `--no-llm` for a free heuristic pass (lower quality).
- `claims_atomic.json` carries per-claim `report_page`, `report_quote`, and deposition prompts used later by the cross-examination block.
- Skim the output: every claim should have a real quote and page number.

## 4. Run the full analysis (the paid step)

```bash
export CME_ALLOW_LOCAL_ANALYSIS=1
python3 analyze_cme_full.py "$CASE/video.mp4" \
  --plaintiff "Lastname, Firstname" \
  --examiner "Dr. <Examiner>" \
  --date "MM/DD/YYYY" \
  --claims "$CASE/claims.json" \
  --report-format standard \
  --preset standard \
  --auto-transcribe true \
  --with-research true \
  --output "$CASE/analysis_run"
```

- The script prints a cost estimate and requires confirmation above $5 (`--confirm-cost` / `-y` to acknowledge).
- `--with-research true` enables Perplexity literature lookups; the citation URLs it returns are cached in `research_cache.json` and flow into the report's `literature_refs`. Keep this ON for client deliverables.
- If it dies mid-run (network, rate limit), re-run with `--resume` — it checkpoints per frame and will not re-bill completed frames.
- Outputs land in `$CASE/analysis_run/`: `frames/`, `comprehensive/`, `behavior/`, `transcript_0.json`, `STANDARD_CME_REPORT.html` + `.pdf`, `cost_actual.json`.

## 5. Verify claims against the video (Report vs video verdicts)

```bash
python3 scripts/run_claim_verifier.py \
  --analysis-dir "$CASE/analysis_run" \
  --claims "$CASE/claims.json" \
  --atomic-claims "$CASE/claims_atomic.json" \
  --out-dir "$CASE/analysis_run" \
  --with-research --no-sample
```

`--no-sample` matters for non-Osborne cases: without it the script copies this case's verdicts into `frontend/public/sample-case/`, overwriting the public demo data.

- Use `--dry-run` first to see the LLM verifier cost (typically well under $1).
- `--offline` runs the free heuristic verifier (labels are weaker; fine for smoke tests, not for client reports).
- Produces `claim_verdicts.json` with per-claim verdict, evidence, timestamps, and the `cross_examination` block (leading question, report citation, video finding, literature refs).

## 6. Build the ledgers and named-test index

```bash
python3 scripts/build_test_ledger.py \
  --frames "$CASE/analysis_run/comprehensive/frame_analyses.json" \
  --claims "$CASE/claims.json" \
  --case-id "<case_id>" \
  --session-out "$CASE/analysis_run/test_ledger.json"

python3 scripts/build_named_test_index.py \
  --frames "$CASE/analysis_run/comprehensive/frame_analyses.json" \
  --out "$CASE/analysis_run/named_test_index.json" \
  --case-id "<case_id>"

python3 scripts/build_three_way_ledger.py \
  --frames "$CASE/analysis_run/comprehensive/frame_analyses.json" \
  --atomic-claims "$CASE/claims_atomic.json" \
  --out "$CASE/analysis_run/three_way_ledger.json" \
  --case-id "<case_id>"
```

The three-way ledger is what catches "performed on video but not in the report" — check it, that category is deposition gold.

## 7. Link everything to a live session

Create (or reuse) a session in the web app, then:

```bash
python3 scripts/link_local_analysis_to_session.py \
  --session-id cme_XXXXXXXXXXXX \
  --analysis-dir "$CASE/analysis_run" \
  --include-video \
  --video-local-path "$CASE/video.mp4"
```

- Uploads artifacts + video to S3 and updates the DynamoDB session record.
- `--dry-run` shows what would be uploaded without touching AWS.
- After linking, open `https://<app>/sessions/cme_XXXXXXXXXXXX` — the "Report vs video" tab should show verdicts with clickable timestamps that seek the video.
- Deep links have the form `/sessions/{id}?t={seconds}` — the same links embedded in the PDF report timestamps.

## 8. Deliver

Send Dorothy + Tim:

1. `STANDARD_CME_REPORT.pdf` (timestamps in it deep-link into the session player)
2. The session URL
3. `cost_actual.json` total, for billing transparency

Ask them to line the report up against Oregon's manual analysis and mark anything the software missed, over-called, or mis-timed — those notes feed the golden set (`tests/fixtures/golden_set/`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Local analysis disabled" error | `export CME_ALLOW_LOCAL_ANALYSIS=1` |
| Run stops mid-vision-pass | Re-run same command with `--resume` |
| All verdicts "insufficient evidence — model output unparseable" | Model ID is stale; check `DEFAULT_SONNET_MODEL` in `backend/lambda_functions/cme_analysis_utils.py` |
| `--with-research` warning about missing key | Set `PERPLEXITY_API_KEY` (Tim's enterprise account) |
| H.264 decode warnings during frame extraction | Usually harmless; if frames come out corrupt, re-encode first: `ffmpeg -i in.mkv -c:v libx264 -crf 18 out.mp4` |
| `.mpg` or other odd container fails | Re-encode to mp4 as above before running |
