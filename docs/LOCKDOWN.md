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

No `CME_ALLOW_LOCAL_ANALYSIS` needed for `--offline`? Actually the gate runs before offline check. Let me verify - _check_local_gate runs at start regardless. So offline still needs CME_ALLOW_LOCAL_ANALYSIS=1 OR --force.

That's correct for lockdown - even offline path goes through gate. User might want offline without gate for CI - but user asked for lockdown. The test file and docs should reflect this.

Actually re-read run_claim_verifier - _check_local_gate runs before everything. So --offline still needs the gate. For CI that's fine if they set the env in CI or use --force.

For demo doc I'll mention --offline with gate or --force for CI.

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
