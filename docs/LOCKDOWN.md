# CME Platform Lockdown

One-page reference for environment keys, cost gates, AI providers, and safe demo runs.

## Quick validate

```bash
python scripts/validate_env.py --demo      # frontend / sample-case
python scripts/validate_env.py --analyze   # analyze_cme_full.py
python scripts/validate_env.py --verifier  # run_claim_verifier.py
```

Prints `SET` / `MISSING` only — never secret values. Exits `1` if critical keys are missing for the mode.

## Required keys

| Key | Required for | Notes |
|-----|--------------|-------|
| `CME_ALLOW_LOCAL_ANALYSIS=1` | Local analyze + verifier | Cost gate; must be exactly `1` |
| `ANTHROPIC_API_KEY` | Local analyze + verifier LLM | Default vision + text provider |
| `REACT_APP_API_URL` | Frontend live mode | Required when `REACT_APP_USE_MOCK_API=false` |

Copy `.env.example` → `.env` (gitignored). Never commit `.env`.

## Optional keys (opt-in only)

| Key | When used |
|-----|-----------|
| `PERPLEXITY_API_KEY` | Only with `--with-research` on analyze or verifier scripts |
| `OPENAI_API_KEY` | Only with `analyze_cme_full.py --providers openai,...` |
| `GOOGLE_API_KEY` | Only with `analyze_cme_full.py --providers gemini,...` |

**Perplexity is never auto-enabled** when a key is present. You must pass `--with-research`.

## AI provider policy

| Provider | Local scripts | Production |
|----------|---------------|------------|
| **Anthropic** | Default; required for paid local runs | Via API key in Lambda env |
| **Perplexity** | Opt-in `--with-research` only | Same opt-in pattern |
| **OpenAI / Gemini** | Only via `--providers` flag | Configured per deploy |
| **AWS Bedrock** | Not used locally | IAM role on Lambda; no local key |

## Cost gates

### `analyze_cme_full.py`

- Refuses unless `CME_ALLOW_LOCAL_ANALYSIS=1`
- Prints cost estimate before vision passes
- Estimates over **$5** require `--confirm-cost` or `--yes`
- Typical full run: **$5–$50+** depending on video length and `--interval`

Preview without spending:

```bash
python scripts/estimate_cme_cost.py path/to/video.mp4
```

### `run_claim_verifier.py`

- Refuses unless `CME_ALLOW_LOCAL_ANALYSIS=1` (or `--force`)
- Prints cost estimate before LLM batch (~$0.025/claim heuristic)
- `--dry-run` loads inputs and prints counts + estimate, no API calls
- `--offline` uses keyword heuristics (no LLM, free)
- Osborne sample (~11 claims): ~**$0.28** LLM; +~**$0.11** with `--with-research`

## Safe demo (no API spend)

### Frontend only

```bash
cd frontend
cp .env.example .env.local
# REACT_APP_USE_MOCK_API=true  OR  leave API_URL blank in dev mode
npm start
```

Open `/sample-case` — uses bundled JSON artifacts, no backend, no AI keys in frontend env.

### Verifier offline (CI / demo bundle refresh)

```bash
python scripts/run_claim_verifier.py --offline --dry-run   # preview
python scripts/run_claim_verifier.py --offline             # rewrite sample-case JSON
```

Note: `--offline` still requires `CME_ALLOW_LOCAL_ANALYSIS=1` (or `--force`) — the cost gate runs before the offline check. For CI, set the env var in the workflow or pass `--force`.

## Production API auth (added 2026-08-05)

All non-OPTIONS methods on the CME Analysis API (`g4dzem9rtk`, stage `prod`) require a
Cognito ID token from the `cme-analysis-users` pool (`us-east-1_t8m33Ihhq`), sent as
`Authorization: Bearer <IdToken>`. Authorizer: `cme-cognito-authorizer` (API Gateway,
type COGNITO_USER_POOLS). OPTIONS remains open for CORS preflight.

Consequences:

- Production frontend works unchanged — it logs in via Cognito and attaches the token.
- **Localhost dev mode (`REACT_APP_DEV_MODE=true`) can no longer hit the live API** —
  its fake `dev-mode-token` is rejected with 401. Use mock mode, or set
  `REACT_APP_DEV_MODE=false` and log in with real pool credentials.
- Operator scripts in `scripts/` authenticate via `scripts/cme_api_auth.py`.
  Set `CME_API_USERNAME` / `CME_API_PASSWORD` (a `cme-analysis-users` pool
  login) in the environment before running them. S3 presigned URLs are
  still fetched without the bearer header — S3 rejects requests carrying
  two auth mechanisms.
- The MediaConvert completion Lambda no longer calls the public API; it
  invokes the `cme-api-handler` Lambda directly (IAM), override with
  `API_HANDLER_FUNCTION`.

## Frontend lockdown

- **No AI keys** in `REACT_APP_*` variables (grep verified clean)
- `REACT_APP_USE_MOCK_API=false` without `REACT_APP_API_URL` → falls back to mock with console warning
- Cognito only when `REACT_APP_DEV_MODE=false`

## Key rotation

If a key may have leaked (committed, logged, shared screen):

1. Revoke it in the provider console immediately
2. Issue a new key and update `.env` only (never commit)
3. Rotate Lambda env vars via CDK/deploy for production
4. Review AWS CloudTrail / provider usage for unexpected calls

Treat `.env` like a password file.
