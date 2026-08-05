# CME Platform v2 — Orthopedic & Neurologic Test Index

**Last updated:** 2026-05-29  
**Source:** Tim demo feedback (May 2026)  
**Status:** Milestone A implemented (ledger + Tests tab UI)

---

## Problem statement

Defense teams reviewing CME video need a **structured test-by-test view**, not only a PDF narrative. Tim’s feedback:

1. Every orthopedic/neurologic test broken out individually (Hoffmann’s, Babinski, ROM by body part, gait, strength, sensory, Romberg variants, reflexes, cranial nerves).
2. **Click test name → jump to deposition timestamp** in synced video.
3. **Three-way reconciliation:** what the report claimed vs what video shows vs performed-but-not-reported.
4. **Technique verdict** per test: proper / modified / improper / inconclusive / not shown.
5. **Website UI is primary** — test index + synced video, not PDF-only.

---

## Taxonomy (v1)

| `test_type` | Display name | Body regions |
|-------------|--------------|--------------|
| `hoffmann` | Hoffmann sign | hand, arm |
| `babinski` | Babinski sign | foot, leg |
| `romberg` | Romberg test | full_body |
| `rom` | Range of motion | neck, shoulder, arm, leg |
| `gait` | Gait assessment | full_body, leg |
| `strength` | Manual muscle testing | hand, arm, leg, shoulder |
| `sensory` | Sensory examination | hand, arm, leg, foot |
| `reflex` | Deep tendon reflexes | arm, leg |
| `cranial_nerve` | Cranial nerve examination | face, head |
| `palpation` | Palpation (general exam) | neck, back, shoulder, … |

Variants are inferred from frame `test_details` (e.g. tandem gait, cervical flexion, pinprick).

---

## Three-way status

| Status | Meaning |
|--------|---------|
| `claimed_and_observed` | Report documents test; video shows performance |
| `claimed_not_observed` | Report documents test; no matching video segment |
| `observed_not_reported` | Video shows test; not clearly documented in report claims |
| `neither` | Reserved for future NLP extraction |

Claims are loaded from `cme_projects/osborn_2021_03/claims.json` (Osborne 2021).

---

## Technique verdict

| Verdict | Rule (Milestone A) |
|---------|-------------------|
| `proper` | Observed, clear visibility, no technique flags |
| `modified` | Observed with modifiable deviations (through clothing, no gown, street shoes) |
| `improper` | Observed with serious technique issues (e.g. no goniometer for ROM) |
| `inconclusive` | Observed but obscured/partial visibility |
| `not_shown` | Claimed in report or listed but no video evidence |

---

## Milestones

### Milestone A — Test ledger + Tests tab (this release)

- [x] `scripts/build_test_ledger.py` — aggregate half-second frames → `test_ledger.json`
- [x] Sample bundle: `frontend/public/sample-case/test_ledger.json`
- [x] **Tests** tab on Session Detail + Sample Case
- [x] Filterable index, verdict badges, click-to-seek video
- [x] Claims integration (Osborne `claims.json`)
- [x] Chatbot intents: cost, orthopedic tests, sample cost (~$47.45)

### Milestone B — Report NLP crosswalk

- Parse defense PDF/HTML for explicit test statements
- Map report sentences to ledger rows (not just `claims.json` stub)
- Highlight contradictions (e.g. “DTR 0/4” vs no hammer observed)

### Milestone C — Reflex / Hoffmann / Babinski frame prompts

- Extend vision taxonomy prompts to tag Hoffmann, Babinski, Romberg, DTR explicitly
- Re-run **not** required for demo; use new tags on future cases only

### Milestone D — Deposition export

- Export selected test clips (timestamp ranges) for trial prep
- Batch PDF appendix with QR links back to web Tests tab

---

## Success criteria (Tim next meeting)

| Criterion | Target |
|-----------|--------|
| Tests listed with body region | ≥ 30 distinct events on Osborne halfsec run |
| Click → video seek | Works on live session with `video_playback_url` |
| Three-way columns visible | Claimed / Observed / Status badge |
| Technique verdict | Badge on every row |
| No new API spend | Ledger built from existing `analysis_run_halfsec` only |
| Load time | Tests tab interactive in < 2s on sample bundle |

---

## How to rebuild ledger (no API cost)

```bash
cd /Users/hammadhaque/Documents/cme-analysis-platform
python3 scripts/build_test_ledger.py
```

Outputs:

- `frontend/public/sample-case/test_ledger.json`
- `tests/fixtures/test_ledger_osborne.json`

Optional session copy:

```bash
python3 scripts/build_test_ledger.py \
  --session-out cme_projects/osborn_2021_03/analysis_run_halfsec/test_ledger.json
```

Link to live session (optional, requires AWS creds):

```bash
python3 scripts/link_local_analysis_to_session.py \
  --session-id cme_6f506df9ebf9 \
  --analysis-dir cme_projects/osborn_2021_03/analysis_run_halfsec
```

(Add `test_ledger.json` to upload map when deploying artifacts.)

---

## Viewing locally

| Surface | URL | Video |
|---------|-----|-------|
| Sample case | http://localhost:3000/cases/sample → **Tests** tab | Ledger only (no bundled MP4) |
| Osborne session | http://localhost:3000/sessions/cme_6f506df9ebf9 → **Tests** tab | Presigned URL from API |

Use `.env.local` with live API (see `docs/DEMO_READY.md`).

---

## Data schema (`test_ledger.json`)

```json
{
  "schema_version": "1.0.0",
  "case_id": "osborn_2021_03",
  "total_events": 42,
  "events": [
    {
      "test_name": "Manual muscle testing — Hand / wrist",
      "test_type": "strength",
      "body_region": "hand",
      "start_sec": 90.0,
      "end_sec": 95.5,
      "claimed_in_report": true,
      "observed_on_video": true,
      "three_way_status": "claimed_and_observed",
      "technique_verdict": "modified",
      "technique_issues": ["testing_through_clothing"]
    }
  ]
}
```
