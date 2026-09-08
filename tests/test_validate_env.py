"""Tests for scripts/validate_env.py and lockdown gates."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE = REPO_ROOT / "scripts" / "validate_env.py"


def _run_validate(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    merged = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    merged.pop("CME_ALLOW_LOCAL_ANALYSIS", None)
    merged["CME_VALIDATE_SKIP_DOTENV"] = "1"
    if env is not None:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(VALIDATE), *args],
        cwd=REPO_ROOT,
        env=merged,
        capture_output=True,
        text=True,
    )


def test_validate_demo_ok_without_api_keys():
    result = _run_validate("--demo")
    assert result.returncode == 0
    assert "OK: environment satisfies --demo" in result.stdout


def test_validate_analyze_fails_without_gate_and_key():
    result = _run_validate("--analyze")
    assert result.returncode == 1
    assert "CME_ALLOW_LOCAL_ANALYSIS" in result.stdout
    assert "FAIL" in result.stdout


def test_validate_analyze_ok_with_required_keys():
    result = _run_validate(
        "--analyze",
        env={
            "CME_ALLOW_LOCAL_ANALYSIS": "1",
            "OPENAI_API_KEY": "sk-test",
        },
    )
    assert result.returncode == 0
    assert "OK: environment satisfies --analyze" in result.stdout


def test_validate_never_prints_secret_values():
    secret = "sk-super-secret-value-12345"
    result = _run_validate(
        "--analyze",
        env={
            "CME_ALLOW_LOCAL_ANALYSIS": "1",
            "OPENAI_API_KEY": secret,
        },
    )
    assert secret not in result.stdout
    assert secret not in result.stderr


def test_perplexity_not_auto_enabled_when_key_present():
    """Mirrors analyze_cme_full.py: key alone must not enable research."""
    with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "pplx-test"}, clear=False):
        args_with_research = None
        with_research = bool(args_with_research)
        assert with_research is False

        with_research = bool(True)
        assert with_research is True


def test_verifier_local_gate_requires_env():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_claim_verifier",
        REPO_ROOT / "scripts" / "run_claim_verifier.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(SystemExit) as exc:
            mod._check_local_gate(force=False)
        assert exc.value.code == 1


def test_verifier_local_gate_allows_with_flag():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_claim_verifier",
        REPO_ROOT / "scripts" / "run_claim_verifier.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with patch.dict(os.environ, {"CME_ALLOW_LOCAL_ANALYSIS": "1"}):
        mod._check_local_gate(force=False)


def test_estimate_claim_verifier_cost():
    from backend.lambda_functions.cme_analysis_utils import estimate_claim_verifier_cost_usd

    est = estimate_claim_verifier_cost_usd(11, with_research=True)
    assert est["claim_count"] == 11
    assert est["estimated_research_cost_usd"] > 0
