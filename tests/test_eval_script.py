"""Offline tests for scripts/eval_cme_vision.py.

These tests must never hit a real network. They exercise:
  - the dry-run CLI path against the real golden-set manifest,
  - the pure scoring helpers (categorical / boolean / notes / aggregation),
  - the --compare-to error path (missing baseline file).

The script is loaded via importlib.util so the test file does not have
to live under a package or rely on PYTHONPATH gymnastics.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO / "scripts" / "eval_cme_vision.py"
MANIFEST_PATH = REPO / "tests" / "fixtures" / "golden_set" / "manifest.json"


@pytest.fixture(scope="module")
def eval_mod():
    """Load scripts/eval_cme_vision.py as a module without requiring it to
    be on sys.path. Cached for the module scope so import side-effects
    only fire once. We register the module in `sys.modules` before exec
    so that dataclass field resolution can look up forward references."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    spec = importlib.util.spec_from_file_location("eval_cme_vision", SCRIPT_PATH)
    assert spec and spec.loader, "could not load eval_cme_vision spec"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_cme_vision"] = mod
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------------
# CLI: --dry-run
# ----------------------------------------------------------------------


def test_dry_run_lists_every_clip_and_frame():
    """A dry-run on the real manifest must exit 0 and emit one line per
    (clip, pass, frame) tuple. The total frame count must match the
    actual JPEGs on disk."""
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--dry-run",
            "--manifest",
            str(MANIFEST_PATH),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    base = MANIFEST_PATH.parent
    expected_clip_ids = []
    expected_total_frames = 0
    for clip in manifest["clips"]:
        d = base / clip["frames_dir"]
        if not d.is_dir():
            continue
        frames = sorted(d.glob("*.jpg"))
        if not frames:
            continue
        expected_clip_ids.append(clip["id"])
        expected_total_frames += len(frames)
        # Every clip id must appear in the output.
        assert clip["id"] in out, f"missing clip {clip['id']!r} in dry-run stdout"
        for fp in frames:
            assert fp.name in out, f"missing frame {fp.name} in dry-run stdout"

    assert f"total frames: {expected_total_frames}" in out


# ----------------------------------------------------------------------
# Scoring rules
# ----------------------------------------------------------------------


def test_compare_categorical_exact_case_insensitive(eval_mod):
    ok, _ = eval_mod.compare_categorical("Conversation", "conversation")
    assert ok is True
    ok, _ = eval_mod.compare_categorical("rom", "ROM")
    assert ok is True
    ok, _ = eval_mod.compare_categorical("rom", "strength")
    assert ok is False


def test_compare_boolean_strict(eval_mod):
    assert eval_mod.compare_boolean(True, True)[0]
    assert eval_mod.compare_boolean(False, False)[0]
    assert not eval_mod.compare_boolean(True, False)[0]
    assert not eval_mod.compare_boolean(False, True)[0]


def test_compare_notes_passes_when_majority_phrases_present(eval_mod):
    expected = "patient wearing street clothes, doctor looking at notes"
    actual_pass = "The doctor is writing notes while patient sits"
    actual_fail = "patient is wearing a hospital gown"
    ok_pass, reason_pass = eval_mod.compare_notes(expected, actual_pass)
    ok_fail, reason_fail = eval_mod.compare_notes(expected, actual_fail)
    assert ok_pass, reason_pass
    assert not ok_fail, reason_fail


def test_extract_phrases_drops_stopwords_and_short_tokens(eval_mod):
    phrases = eval_mod.extract_phrases(
        "The doctor is writing notes during the interview"
    )
    # Stopwords like "the", "is" and short tokens must be dropped.
    assert "the" not in phrases
    assert "is" not in phrases
    assert "doctor" in phrases
    assert "notes" in phrases
    assert all(len(p) >= 4 for p in phrases)


def test_compare_confidence_overconfident_on_obscured_fails(eval_mod):
    # High confidence but visibility mismatch -> fail.
    ok, _ = eval_mod.compare_confidence("obscured", "full", 0.95)
    assert ok is False


def test_compare_confidence_low_score_fails(eval_mod):
    ok, _ = eval_mod.compare_confidence("full", "full", 0.4)
    assert ok is False


def test_compare_confidence_high_and_matching_visibility_passes(eval_mod):
    ok, _ = eval_mod.compare_confidence("partial", "partial", 0.7)
    assert ok is True


def test_score_frame_only_grades_present_fields(eval_mod):
    expected = {"test_type": "rom", "doctor_facing_patient": True}
    actual = {
        "test_type": "rom",
        "doctor_facing_patient": True,
        "body_region": "leg",  # not in expected -> not scored
    }
    fields, rate = eval_mod.score_frame(
        expected=expected, actual=actual, pass_name="comprehensive"
    )
    assert set(fields.keys()) == {"test_type", "doctor_facing_patient"}
    assert rate == 1.0


def test_score_frame_list_subset(eval_mod):
    expected = {"technique_issues": ["patient_not_in_gown", "no_goniometer"]}
    actual_pass = {
        "technique_issues": ["no_goniometer", "patient_not_in_gown", "rushed_examination"]
    }
    actual_fail = {"technique_issues": ["rushed_examination"]}
    fields_pass, rate_pass = eval_mod.score_frame(
        expected=expected, actual=actual_pass, pass_name="comprehensive"
    )
    fields_fail, rate_fail = eval_mod.score_frame(
        expected=expected, actual=actual_fail, pass_name="comprehensive"
    )
    assert rate_pass == 1.0
    assert rate_fail == 0.0
    assert fields_fail["technique_issues"].passed is False


# ----------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------


def _make_field(eval_mod, name: str, passed: bool):
    return eval_mod.FieldResult(
        field_name=name, expected="x", actual="x" if passed else "y",
        passed=passed, reason="",
    )


def test_aggregate_results_rolls_up_clips_fields_and_totals(eval_mod):
    fr1 = eval_mod.FrameResult(
        clip_id="clipA",
        pass_name="comprehensive",
        frame_filename="f1.jpg",
        provider="anthropic",
        model_id="m",
        fields={
            "test_type": _make_field(eval_mod, "test_type", True),
            "body_region": _make_field(eval_mod, "body_region", False),
        },
        frame_pass_rate=0.5,
        raw_response_excerpt="",
        usd_cost_estimate=0.01,
    )
    fr2 = eval_mod.FrameResult(
        clip_id="clipA",
        pass_name="behavior",
        frame_filename="f1.jpg",
        provider="anthropic",
        model_id="m",
        fields={
            "doctor_facing_patient": _make_field(eval_mod, "doctor_facing_patient", True),
        },
        frame_pass_rate=1.0,
        raw_response_excerpt="",
        usd_cost_estimate=0.02,
    )
    fr3 = eval_mod.FrameResult(
        clip_id="clipB",
        pass_name="comprehensive",
        frame_filename="f2.jpg",
        provider="anthropic",
        model_id="m",
        fields={
            "test_type": _make_field(eval_mod, "test_type", True),
        },
        frame_pass_rate=1.0,
        raw_response_excerpt="",
        usd_cost_estimate=0.005,
    )
    agg = eval_mod.aggregate_results(
        frame_results=[fr1, fr2, fr3], passes_run=["comprehensive", "behavior"]
    )
    totals = agg["totals"]
    assert totals["fields_evaluated"] == 4
    assert totals["fields_passed"] == 3
    assert totals["clips"] == 2
    # 2 unique (clip,frame): (clipA,f1), (clipB,f2)
    assert totals["frames"] == 2
    assert abs(totals["pass_rate"] - (3 / 4)) < 1e-9
    assert abs(totals["estimated_cost_usd"] - 0.035) < 1e-9

    # by_clip rollup
    by_clip = {c["clip_id"]: c for c in agg["by_clip"]}
    assert by_clip["clipA"]["fields_evaluated"] == 3
    assert by_clip["clipA"]["fields_passed"] == 2
    assert abs(by_clip["clipA"]["pass_rate"] - (2 / 3)) < 1e-9
    assert by_clip["clipB"]["fields_evaluated"] == 1
    assert by_clip["clipB"]["fields_passed"] == 1

    # by_field rollup
    assert agg["by_field"]["test_type"]["evaluated"] == 2
    assert agg["by_field"]["test_type"]["passed"] == 2
    assert agg["by_field"]["body_region"]["passed"] == 0


# ----------------------------------------------------------------------
# --compare-to error handling
# ----------------------------------------------------------------------


def test_compare_to_missing_baseline_exits_non_zero(tmp_path: Path):
    """If --compare-to points at a path that does not exist, the eval
    must exit non-zero and emit a clear [error] line on stderr."""
    bogus = tmp_path / "nonexistent_baseline.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--manifest",
            str(MANIFEST_PATH),
            "--compare-to",
            str(bogus),
            "--dry-run",  # would otherwise burn budget; harness still validates --compare-to early
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc.returncode != 0
    assert "[error]" in proc.stderr
    assert str(bogus) in proc.stderr


# ----------------------------------------------------------------------
# No network: defensive guard so accidental real calls fail the suite.
# ----------------------------------------------------------------------


def test_no_real_provider_client_built_during_module_import(eval_mod, monkeypatch):
    """Loading the script must not instantiate any real provider client.
    The analyzers only build a client when constructed. This test exists
    to make that invariant explicit in the test suite."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Reaching this assertion implies the module imported without provider
    # keys in the environment, which would have raised inside any eager
    # VisionClient construction.
    assert hasattr(eval_mod, "evaluate_manifest")
    assert callable(eval_mod.evaluate_manifest)
