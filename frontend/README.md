# CME Analysis Platform – Frontend

React (Create React App) + Tailwind front-end for the CME Analysis Platform.
This README only covers running the UI locally for demos and development. See
`docs/demo_runbook.md` for the demo script Tim will see.

## Quick start

```bash
cd frontend
cp .env.example .env.local   # then edit if needed
npm install
npm start
```

The dev server boots on `http://localhost:3000`. With the default
`.env.example` values, the app runs in **dev mode** with the **mock API**
enabled, so you do not need backend access to walk through the upload flow or
view the sample case.

## Environment variables

All variables live in `.env.local` (gitignored). Reference defaults are in
`.env.example`:

| Variable | Purpose |
| --- | --- |
| `REACT_APP_API_URL` | Live backend base URL. If blank, the app uses the deployed CME API default. |
| `REACT_APP_DEV_MODE` | `true` skips Cognito and signs in a local demo user. Ignored in production builds. |
| `REACT_APP_USE_MOCK_API` | `true` simulates uploads and processing locally. Ignored in production builds unless `REACT_APP_ALLOW_PRODUCTION_MOCK_API=true` is also set. |
| `REACT_APP_ALLOW_PRODUCTION_MOCK_API` | Emergency/demo override for production mock mode. Leave unset for the live app. |
| `REACT_APP_USER_POOL_ID` / `REACT_APP_USER_POOL_WEB_CLIENT_ID` | Only used when dev mode is `false`. |

When `REACT_APP_DEV_MODE=true` and `REACT_APP_API_URL` is empty during local
development, the mock layer activates automatically. Uploads are simulated
(with realistic per-file progress) and case state persists in `localStorage`.
Clearing site data resets the demo cases.

## Routes

| Path | Purpose |
| --- | --- |
| `/` | Dashboard with case list, hero CTAs, and stats. |
| `/cases/new` | Multi-step upload wizard (metadata → video → reports → review). |
| `/cases/:caseId` | Processing landing page for a newly-uploaded case. |
| `/cases/sample` | Static viewer for the Osborne 2021 deliverable. |
| `/sessions/:sessionId` | Legacy detailed session view (live backend only). |
| `/login` | Auth page. Dev mode lets any credentials through. |

Production uploads currently support one recording per case. Use MP4, MOV,
M4V, WEBM, or supported audio (MP3, M4A, WAV, FLAC, OGG, AMR). Combine split
exam segments into one file before upload.

## Sample case artifacts

The Osborne run is served statically from
`frontend/public/sample-case/`:

- `standard_report.html`, `standard_report.pdf`
- `behavior_dashboard.html`
- `comprehensive_analysis.json`, `behavior_summary.json`
- `analysis_report.txt`, `behavior_report.txt`
- `cost_actual.json`, `MANIFEST.json`

Do not delete files in `public/sample-case/`; `SampleCase` fetches the
manifest at load time and falls back to an error banner if any are missing.

## Build

```bash
npm run build
```

CRA's standard production build. CI promotes warnings to errors via `CI=true`,
so keep the tree clean. The build output lands in `frontend/build/`.
