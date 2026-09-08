#!/usr/bin/env python3
"""
Validate CME platform environment variables (no secret values printed).

Exit 0 when the requested mode is satisfied; exit 1 when critical keys are missing.

Modes:
  --demo      Frontend / sample-case demo (no paid API keys required)
  --analyze   Local analyze_cme_full.py (vision + optional research)
  --verifier  Local scripts/run_claim_verifier.py (text LLM verdicts)

AI provider policy (single source of truth):
  - OpenAI: required for --analyze and --verifier LLM paths (default provider)
  - Perplexity: optional; only used when scripts are run with --with-research
  - Anthropic / Gemini: off unless analyze_cme_full.py --providers includes them
  - AWS Bedrock: production Lambda only (IAM role; no local API key)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOW_LOCAL_ENV = "CME_ALLOW_LOCAL_ANALYSIS"

# (env_var, label, critical_for_modes)
ENV_CHECKS: List[Tuple[str, str, frozenset]] = [
    (ALLOW_LOCAL_ENV, "local analysis cost gate (must be 1)", frozenset({"analyze", "verifier"})),
    ("OPENAI_API_KEY", "OpenAI (default vision + verifier LLM)", frozenset({"analyze", "verifier"})),
    ("ANTHROPIC_API_KEY", "Anthropic fallback (only with --providers anthropic,...)", frozenset()),
    ("PERPLEXITY_API_KEY", "Perplexity Sonar (only with --with-research)", frozenset()),
    ("GOOGLE_API_KEY", "Google Gemini (only with --providers gemini,...)", frozenset()),
    ("GEMINI_API_KEY", "Gemini alias (optional fallback)", frozenset()),
]

FRONTEND_VARS = [
    ("REACT_APP_API_URL", "live backend URL (required when mock API is off)"),
    ("REACT_APP_USE_MOCK_API", "mock vs live API toggle"),
    ("REACT_APP_DEV_MODE", "skip Cognito for local demo"),
]


def _load_dotenv() -> None:
    if os.environ.get("CME_VALIDATE_SKIP_DOTENV") == "1":
        return
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _is_set(name: str) -> bool:
    val = os.environ.get(name, "").strip()
    if name == ALLOW_LOCAL_ENV:
        return val == "1"
    return bool(val)


def _status(name: str) -> str:
    return "SET" if _is_set(name) else "MISSING"


def _print_provider_policy() -> None:
    print("\nAI provider policy:")
    print("  OpenAI        required for --analyze / --verifier LLM runs (default provider)")
    print("  Anthropic     optional fallback; set CME_VISION_PROVIDER=anthropic")
    print("  Perplexity    optional; only when --with-research is passed explicitly")
    print("  Gemini        optional fallback; set --providers gemini or CME_VISION_PROVIDER=gemini")
    print("  AWS Bedrock   production Lambda only (IAM; no local key)")


def validate_mode(mode: str) -> int:
    critical_missing: List[str] = []
    print(f"Mode: {mode}")
    print(f"Repo: {REPO_ROOT}")
    print("\nBackend / local analysis (.env):")
    for env_var, label, modes in ENV_CHECKS:
        tag = "REQUIRED" if mode in modes else "optional"
        print(f"  [{_status(env_var):7}] {env_var:24} — {label} ({tag})")
        if mode in modes and not _is_set(env_var):
            critical_missing.append(env_var)

    if mode == "demo":
        print("\nFrontend (frontend/.env.local or build env):")
        for env_var, label in FRONTEND_VARS:
            present = "SET" if os.environ.get(env_var, "").strip() else "MISSING"
            print(f"  [{present:7}] {env_var:24} — {label}")
        mock = os.environ.get("REACT_APP_USE_MOCK_API", "").strip().lower()
        api_url = os.environ.get("REACT_APP_API_URL", "").strip()
        if mock == "false" and not api_url:
            print(
                "\n  WARNING: REACT_APP_USE_MOCK_API=false requires REACT_APP_API_URL "
                "(frontend falls back to mock when URL is missing)."
            )
        ai_in_frontend = [
            k for k in os.environ
            if k.startswith("REACT_APP_") and any(
                x in k.upper() for x in ("ANTHROPIC", "OPENAI", "PERPLEXITY", "GOOGLE", "GEMINI", "API_KEY")
            )
        ]
        if ai_in_frontend:
            print(f"\n  ERROR: AI keys must not be in frontend env: {', '.join(sorted(ai_in_frontend))}")
            critical_missing.extend(ai_in_frontend)

    _print_provider_policy()

    if critical_missing:
        print(f"\nFAIL: critical missing for --{mode}: {', '.join(critical_missing)}")
        return 1

    print(f"\nOK: environment satisfies --{mode}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate CME platform environment")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="Frontend / offline demo")
    group.add_argument("--analyze", action="store_true", help="Local analyze_cme_full.py")
    group.add_argument("--verifier", action="store_true", help="Local run_claim_verifier.py")
    args = parser.parse_args()

    _load_dotenv()

    if args.demo:
        mode = "demo"
    elif args.analyze:
        mode = "analyze"
    else:
        mode = "verifier"

    sys.exit(validate_mode(mode))


if __name__ == "__main__":
    main()
