# Localhost Demo Runbook

**Last updated:** 2026-05-30

Use **localhost:3000** for the Tim demo. No Vercel deploy required.

---

## Quick start (2 minutes)

```bash
cd /Users/hammadhaque/Documents/cme-analysis-platform/frontend
cp .env.example .env.local    # skip if .env.local already exists
npm install
npm start
```

Open **http://localhost:3000**

| Variable | Value |
|----------|--------|
| `REACT_APP_API_URL` | `https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod` |
| `REACT_APP_DEV_MODE` | `true` |
| `REACT_APP_USE_MOCK_API` | `false` |

Footer should show **Live API** (not “Mock API”).

**Offline fallback:** clear `REACT_APP_API_URL` and set `REACT_APP_USE_MOCK_API=true` — sidebar + sample case still work; live Osborne session will not load.

---

## Login

> **Since 2026-08-05 the live API requires real Cognito auth** (see
> `LOCKDOWN.md`, "Production API auth"). Dev mode's fake token gets 401s
> from the live API. To demo against the live API, set
> `REACT_APP_DEV_MODE=false` and log in at `/login` with real
> `cme-analysis-users` pool credentials. Dev mode still works fully with
> the mock API (`REACT_APP_USE_MOCK_API=true`).

Dev mode (`REACT_APP_DEV_MODE=true`): app auto-signs in as **Demo Reviewer** — mock API only.

---

## 5-minute script for Tim — Report vs video tab

1. **Dashboard** — Sidebar: Dashboard, New case, Sample case, recent cases. Point to **CME OSBOURNE** (completed, live API).
2. **Open Osborne** — http://localhost:3000/sessions/cme_6f506df9ebf9  
   Lands on **Report vs video** tab (11 neurologic/spinal claims from Dr. Osborn’s report).
3. **Report vs video** — Walk one row end-to-end:
   - **Report quote** (e.g. “Manual muscle testing 5/5 throughout”)
   - **Verdict badge** (Supported / Not on video / Insufficient)
   - **What video shows** — deposition evidence or “Not shown on video”
   - **Deposition prompt** — ready-made cross-exam question
   - **Click timestamp** → video seeks to that moment (strength through clothing, sensory over sleeve, etc.)
   - Filter by verdict; search by test name
4. **Analysis / Timeline / Reports** — Brief findings, embedded standard report, **Download PDF**.
5. **Sample case** — `/cases/sample` — static Osborne 2021 bundle; works without API.
6. **Chatbot** — Ask “What technique issues were found?” or “What was the analysis cost?” ($47.45, no re-run).

**Do not click Start processing** on a new case unless you accept AWS spend.

---

## Demo URLs

| Surface | URL |
|---------|-----|
| **Localhost** | http://localhost:3000 |
| **Osborne session (primary)** | http://localhost:3000/sessions/cme_6f506df9ebf9 |
| **Sample case (offline)** | http://localhost:3000/cases/sample |
| **Live API** | https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod |

---

## What works today (localhost + live API)

| Feature | Status |
|---------|--------|
| Dev login, sidebar, dashboard | ✅ |
| Osborne session load + 14 S3 artifacts | ✅ |
| Report vs video tab (11 claim rows) | ✅ |
| Click-to-seek deposition video | ✅ |
| Named tests + deposition prompts | ✅ |
| Sample case (offline) | ✅ |
| New case wizard (upload UI) | ✅ — don’t start processing |
| Chatbot (rule-based, context-aware) | ✅ |
| Standard report PDF download | ✅ |
| Test ledger fallback (354 events) | ✅ if claim_verdicts missing |

Verify Osborne artifacts:

```bash
curl -s "https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod/cme/sessions/cme_6f506df9ebf9" \
  | python3 -c "import sys,json; s=json.load(sys.stdin)['session']; u=s.get('artifact_urls') or {}; print(s['status'], 'claim_verdicts' in u, 'test_ledger' in u, 'video' in str(s.get('recordings')))"
```

Expected: `completed True True True`

---

## Claim verdict quality (11 rows)

Smoke-tested 2026-05-30:

- **32/32** pytest passes on `test_evidence_quality_gates.py` + `test_claim_verifier.py`
- Live S3 `claim_verdicts.json`: 11 rows, `provider=offline` (text/heuristic verifier — **not** a new $47 vision run)
- Cranial nerves → head/cranial frames only (no gait/hallway bleed)
- Gait → hallway walking frames only on gait row
- No building-exterior B-roll on physical-exam claims
- Reflexes / coordination → `not_shown` with empty evidence (honest)

Regenerate claim verdicts (~$0.05–0.20 text-only, **not** vision):

```bash
cd /Users/hammadhaque/Documents/cme-analysis-platform
python3 scripts/extract_report_claims.py --no-llm
CME_ALLOW_LOCAL_ANALYSIS=1 python3 scripts/run_claim_verifier.py --resume
python3 scripts/link_local_analysis_to_session.py --session-id cme_6f506df9ebf9
```

---

## What NOT to click

- **Do not** run `python analyze_cme_full.py` (~$20–50 Anthropic + vision).
- **Do not** re-trigger `/process` on **cme_6f506df9ebf9** — analysis is linked.
- **Do not** click **Start processing** on a new upload unless you intend Transcribe/Lambda cost.

---

## Pre-demo checks

```bash
# Backend quality gates
cd /Users/hammadhaque/Documents/cme-analysis-platform
python3 -m pytest tests/test_evidence_quality_gates.py tests/test_claim_verifier.py -q

# Frontend
cd frontend
CI=true npm test -- --watchAll=false
npm run build   # optional sanity check
```

---

## Known limitations (say honestly)

- **Claim verifier is offline/heuristic** — verdicts are deposition prompts + frame matching, not a second LLM pass on every row. Some rows show `insufficient_evidence` when transcript-only cues exist but no clean video timestamp.
- **Gait evidence is hallway B-roll** — appropriate for gait row, but doctor often not facing patient; good cross-exam angle, not “supported.”
- **Hunter methodology brain** — knowledge base exists in backend scripts; not yet surfaced as a dedicated UI tab (behavior dashboard + comprehensive JSON cover partial Hunter themes).
- **354-event test ledger** — fallback tab if claim_verdicts missing; noisier than Report vs video for Tim’s deposition narrative.
- **Chatbot** — rule-based, not GPT; answers from loaded session context.
- **New case processing** — Transcribe + pipeline costs money; polling fallback runs NLP only, not full multi-hour vision Map.
- **Vercel** — optional later; localhost is the demo path for now.

---

## Cost controls

| Action | Cost |
|--------|------|
| View Osborne / sample case | **$0** |
| Open Report vs video tab | **$0** |
| Regenerate claim verdicts (text) | ~$0.05–0.20 |
| Full vision re-analysis | ~**$47** — requires explicit approval |
| New case Start processing | Transcribe + Lambda — **$$** |

---

## Optional: Vercel (not required for demo)

```bash
cd frontend && npm run build && npx vercel --prod --yes
```

Only needed if you want a public URL instead of screen-sharing localhost.
