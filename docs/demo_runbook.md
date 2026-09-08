# Demo runbook – local frontend walkthrough

This is the script for the Tim demo. The frontend runs entirely locally; no
live analyzers are kicked off. The two demo paths are (1) the new-case upload
flow, end-to-end except for actual processing, and (2) the sample completed
case showing what the deliverable looks like.

## Before the demo

```bash
cd /Users/hammadhaque/Documents/cme-analysis-platform/frontend
cp .env.example .env.local   # keep defaults: DEV_MODE=true, USE_MOCK_API=true
npm install                  # first time only
npm start                    # opens http://localhost:3000
```

Confirm the browser tab opens directly to the dashboard (dev mode auto-signs
in a local demo user — Cognito is bypassed). The footer should read
"Mock API · Dev mode".

If you have network access and want to point at the deployed API instead:

```bash
# .env.local
REACT_APP_API_URL=https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod
REACT_APP_DEV_MODE=false
REACT_APP_USE_MOCK_API=false
```

## Path 1 – Upload a new case (the "this is the intake" story)

Honest disclaimer for Tim before clicking around:

> The actual vision and behavior analysis takes roughly two to three hours of
> wall time at half-second sampling for a 20-30 minute recording. The flow you
> are about to see is the intake side. The deliverable side is the sample
> case in path 2.

Walk-through:

1. From the dashboard, click **Start a new case**.
2. Step 1 (Case details): fill in plaintiff name, examiner name (e.g.
   `Dr. Brett Osborn DO`), exam date, date of injury, date of birth.
   - Inline validation catches future dates, missing fields, and DOB after
     exam date.
3. Step 2 (Video): drag-and-drop or browse to attach one `.mp4` / `.mov`
   recording. The card shows file name, size, and a Remove button. The
   production workflow currently supports one recording per case; combine split
   exam segments before upload.
4. Step 3 (Reports): drop in one or more PDFs. Tag each as Defense expert
   report / Initial IME / Plaintiff's medical history / Other.
5. Step 4 (Review and submit): everything you entered. Submit fires
   per-file simulated uploads with progress bars, then lands you on the
   case processing page.
6. The processing page shows the case metadata, what was submitted,
   "Expected wall time: 2 to 3 hours", and a CTA to see the sample case.

You can cancel during upload — files are aborted, the case state is
discarded, and the form remains editable.

## Path 2 – View the sample completed case

From the dashboard, the hero or the side nav, click **View sample case**.
This loads the Osborne 2021 run from static files in `frontend/public/sample-case/`.

The sample case page shows:

- The plaintiff/examiner header and CTAs to open the standard report (HTML
  and PDF) plus the behavior dashboard.
- Three top-finding cards (doctor attention 96%, examination quality 50/100,
  issues identified).
- An Overview tab with examination summary, behavior scores, tests
  performed, and the worst technique / behavior issues.
- A Standard report tab embedding the HTML version inline (with PDF and
  "open in new tab" actions).
- A Behavior dashboard tab embedding the dark dashboard view.
- A Run metadata footer (model, prompt versions, frame count, bundle hash,
  cost). All of this is read from `MANIFEST.json` at runtime.

## Things that will work even if the network is down

- Both demo paths above. Everything lives in `localStorage` and `public/`.
- Sign-out and re-sign-in (dev mode just re-mints the fake user).

## Things that will fail without the network

- Live API mode (the deployed backend at `g4dzem9rtk.execute-api.us-east-1`).
  If the API is unreachable, production surfaces a live API error instead of
  falling back to local demo cases.
- Real Cognito sign-in when `REACT_APP_DEV_MODE=false`.

## Honest disclaimer language for the demo

If Tim asks "is this really running the analyzer right now?":

> No — for the demo we are not kicking off the live pipeline. The intake
> flow you see is the production upload experience. The completed case you
> see in path 2 is a real Osborne 2021 run we generated overnight at
> half-second sampling. Wall time for a fresh case at that sampling rate is
> 2 to 3 hours; we did not want to subject the demo to that.

## What to check if the dev server misbehaves

- `npm install` failed: `rm -rf node_modules package-lock.json && npm install`.
- Sample case page shows a red error banner: make sure
  `frontend/public/sample-case/` still contains `MANIFEST.json`,
  `comprehensive_analysis.json`, and `behavior_summary.json`.
- Mock cases keep stacking up: open dev tools and run
  `localStorage.removeItem('cme_mock_cases_v1')`.
