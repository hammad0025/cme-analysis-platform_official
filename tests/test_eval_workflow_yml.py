"""Static structural tests for .github/workflows/eval.yml.

The eval workflow burns API budget. These tests pin the trigger rules so
a future edit cannot silently turn the workflow into something that runs
on every push. They also assert the cheap CI workflow (`ci.yml`) was not
touched in lock-step with the eval workflow.

When pyyaml is available we parse the file properly. When it is not (a
stripped-down CI image), we fall back to a substring-shaped structural
check so the assertions still mean something.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EVAL_WORKFLOW = REPO / ".github" / "workflows" / "eval.yml"
CI_WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


def _load_yaml(path: Path):
    """Return the parsed YAML if pyyaml is importable, else None."""
    try:
        import yaml  # type: ignore
    except ImportError:
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _on_block(workflow: dict):
    """PyYAML parses the bare `on:` key as the boolean True. Return whichever
    of the two is actually present."""
    if True in workflow:
        return workflow[True]
    return workflow.get("on")


# ----------------------------------------------------------------------
# File existence
# ----------------------------------------------------------------------


def test_eval_workflow_file_exists():
    assert EVAL_WORKFLOW.exists(), f"missing {EVAL_WORKFLOW}"


def test_ci_workflow_file_exists():
    assert CI_WORKFLOW.exists(), f"missing {CI_WORKFLOW}"


# ----------------------------------------------------------------------
# Trigger rules
# ----------------------------------------------------------------------


def test_eval_workflow_has_workflow_dispatch_trigger():
    parsed = _load_yaml(EVAL_WORKFLOW)
    if parsed is None:
        body = EVAL_WORKFLOW.read_text(encoding="utf-8")
        assert "workflow_dispatch" in body
        return
    on = _on_block(parsed)
    assert on is not None, "workflow has no `on:` block"
    assert "workflow_dispatch" in on, "missing workflow_dispatch trigger"


def test_eval_workflow_pull_request_trigger_is_label_gated():
    """The pull_request trigger must be guarded by the `eval-ok` label
    via either an explicit `types: [labeled, ...]` block AND a job-level
    `if:` check, or both. We assert both for safety."""
    body = EVAL_WORKFLOW.read_text(encoding="utf-8")
    assert "eval-ok" in body, "no eval-ok label gate present in workflow"
    parsed = _load_yaml(EVAL_WORKFLOW)
    if parsed is None:
        # Without yaml we still need to see the literal trigger types and
        # the label gate somewhere in the file.
        assert "pull_request" in body
        assert re.search(r"types:\s*\[", body), "pull_request trigger must declare event types"
        return

    on = _on_block(parsed)
    pr = on.get("pull_request") if isinstance(on, dict) else None
    assert pr is not None, "missing pull_request trigger"
    types = pr.get("types") if isinstance(pr, dict) else None
    assert isinstance(types, list) and "labeled" in types, (
        "pull_request.types must include 'labeled' so adding the eval-ok label retriggers the run"
    )

    # The job-level `if:` must explicitly check for the eval-ok label.
    jobs = parsed.get("jobs") or {}
    assert jobs, "no jobs declared"
    job_keys = [j for j in jobs.values() if isinstance(j, dict)]
    if_clauses = [str(j.get("if") or "") for j in job_keys if j.get("if")]
    assert if_clauses, "expected at least one job to declare an `if:` guard"
    assert any("eval-ok" in clause for clause in if_clauses), (
        "no job-level `if:` clause references the eval-ok label; this is the actual gate"
    )


def test_eval_workflow_does_not_run_unconditionally_on_push():
    """The eval workflow must NOT have a push trigger. If a future commit
    adds one, this test should fail loudly."""
    parsed = _load_yaml(EVAL_WORKFLOW)
    if parsed is None:
        body = EVAL_WORKFLOW.read_text(encoding="utf-8")
        # Crude but effective: there must be no `push:` top-level key.
        assert not re.search(r"^\s*push\s*:", body, re.MULTILINE)
        return
    on = _on_block(parsed)
    assert isinstance(on, dict), f"expected `on:` to be a mapping, got {type(on)!r}"
    assert "push" not in on, "eval workflow must NOT have a push trigger"


def test_eval_workflow_does_not_run_on_main_via_pull_request_branches():
    """Even when the pull_request trigger fires, the workflow must not
    auto-run on main. The label gate already enforces this; here we also
    confirm there's no `branches: [main]` push-style trigger sneaking in."""
    parsed = _load_yaml(EVAL_WORKFLOW)
    if parsed is None:
        body = EVAL_WORKFLOW.read_text(encoding="utf-8")
        assert "branches: [main" not in body
        assert "branches: [master" not in body
        return
    on = _on_block(parsed)
    assert isinstance(on, dict)
    assert "push" not in on


# ----------------------------------------------------------------------
# Existing CI must remain free + fast (not touched by this change set)
# ----------------------------------------------------------------------


def test_ci_workflow_is_unchanged_in_shape():
    """The cheap CI workflow must still trigger on push and pull_request
    to main/master, and must NOT carry any of the paid eval markers."""
    body = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "name: CI" in body or "name: ci" in body.lower()
    assert "push:" in body
    assert "pull_request:" in body
    assert "Eval (paid)" not in body
    assert "eval-ok" not in body
    assert "scripts/eval_cme_vision.py" not in body


# ----------------------------------------------------------------------
# Secrets surface (lightweight assertion to catch accidental drops)
# ----------------------------------------------------------------------


def test_eval_workflow_uses_openai_api_key_secret():
    body = EVAL_WORKFLOW.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" in body, "eval workflow must reference OPENAI_API_KEY"
    assert "secrets.OPENAI_API_KEY" in body, (
        "OPENAI_API_KEY must be sourced from a GitHub Actions secret"
    )
    assert "inputs.providers || 'openai'" in body


def test_eval_workflow_invokes_eval_script_with_thresholds():
    body = EVAL_WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/eval_cme_vision.py" in body
    assert "--threshold-pass-rate" in body
    assert "--json-out" in body
    assert "--markdown-out" in body
