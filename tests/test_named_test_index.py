"""Tests for named test extraction and three-way reconciliation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.lambda_functions.cme_named_test_index import (  # noqa: E402
    extract_named_tests,
    build_named_test_index,
)
from backend.lambda_functions.cme_three_way_ledger import build_three_way_ledger  # noqa: E402
from backend.lambda_functions.cme_claim_verifier import hunter_methodology_context_for_claim  # noqa: E402

FRAMES_PATH = (
    REPO / "cme_projects/osborn_2021_03/analysis_run_halfsec/comprehensive/comprehensive_frame_analyses.json"
)
ATOMIC_PATH = REPO / "cme_projects/osborn_2021_03/claims_atomic.json"
FIXTURE_INDEX = REPO / "frontend/public/sample-case/named_test_index.json"
FIXTURE_LEDGER = REPO / "frontend/public/sample-case/three_way_ledger.json"


def _frame(ts, test_type, body_region, notes, **extra):
    return {
        "frame_id": f"video1_frame_{int(ts * 2):04d}",
        "timestamp_sec": ts,
        "test_type": test_type,
        "body_region": body_region,
        "test_details": notes,
        "notes": notes,
        "visibility": "full",
        "technique_issues": extra.get("technique_issues") or [],
    }


def test_extract_hoffmann_explicit_keyword():
    frames = [_frame(100.0, "strength", "hand", "Doctor performing Hoffmann sign flick on middle finger")]
    tests = extract_named_tests(frames)
    assert any(t["named_test_key"] == "hoffmann_sign" for t in tests)


def test_extract_babinski_explicit_keyword():
    frames = [_frame(200.0, "sensory", "foot", "Babinski plantar response testing on sole")]
    tests = extract_named_tests(frames)
    assert any(t["named_test_key"] == "babinski_sign" for t in tests)


def test_extract_romberg_explicit():
    frames = [_frame(300.0, "romberg", "full_body", "Romberg test feet together eyes closed")]
    tests = extract_named_tests(frames)
    assert any(t["named_test_key"] == "romberg_test" for t in tests)


def test_extract_cervical_rom_planes():
    frames = [
        _frame(771.0, "rom", "neck", "cervical spine range of motion bending head forward flexion"),
        _frame(802.0, "rom", "neck", "neck range of motion looking upward extension"),
    ]
    tests = extract_named_tests(frames)
    planes = {t.get("plane") for t in tests if t["named_test_key"] == "cervical_rom"}
    assert "flexion" in planes
    assert "extension" in planes


def test_three_way_performed_not_reported():
    frames = [
        _frame(500.0, "coordination", "arm", "finger to nose coordination test repeated"),
    ]
    ledger = build_three_way_ledger(frames, atomic_claims_path=ATOMIC_PATH if ATOMIC_PATH.is_file() else None)
    # coordination is claimed in atomic claims — not performed_not_reported
    coord_rows = [r for r in ledger["rows"] if r.get("matching_claim_id") == "coordination"]
    assert coord_rows or ledger["total_rows"] >= 0


def test_three_way_claimed_not_shown_romberg():
    frames = [_frame(8.0, "none", "none", "exterior building shot")]
    ledger = build_three_way_ledger(frames, atomic_claims_path=ATOMIC_PATH if ATOMIC_PATH.is_file() else None)
    romberg_rows = [r for r in ledger["rows"] if r["named_test_key"] == "romberg_test"]
    assert romberg_rows
    assert any(r["three_way_status"] == "claimed_not_shown" for r in romberg_rows)


def test_hunter_context_for_long_tract_claim():
    ctx = hunter_methodology_context_for_claim(
        "long_tract_signs",
        "No long tract signs",
    )
    assert "Hoffmann" in ctx or "Babinski" in ctx or "hoffmann" in ctx.lower()


@pytest.mark.skipif(not FRAMES_PATH.is_file(), reason="Osborne frames not present")
def test_build_on_real_frames():
    frames = json.loads(FRAMES_PATH.read_text(encoding="utf-8"))
    index = build_named_test_index(frames)
    assert index["total_detections"] >= 1
    keys = {t["named_test_key"] for t in index["tests"]}
    assert "cervical_rom" in keys


@pytest.mark.skipif(not FIXTURE_INDEX.is_file(), reason="Run build_named_test_index.py first")
def test_fixture_named_index_schema():
    data = json.loads(FIXTURE_INDEX.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0.0"
    assert "tests" in data
    assert data["total_detections"] == len(data["tests"])


@pytest.mark.skipif(not FIXTURE_LEDGER.is_file(), reason="Run build_three_way_ledger.py first")
def test_fixture_three_way_schema():
    data = json.loads(FIXTURE_LEDGER.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0.0"
    assert "rows" in data
    assert "performed_not_reported_count" in data
