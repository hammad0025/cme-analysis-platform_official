"""Tests for scripts/build_test_ledger.py"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests/fixtures/test_ledger_osborne.json"


@pytest.fixture(scope="module")
def ledger():
    assert FIXTURE.is_file(), "Run scripts/build_test_ledger.py first"
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_ledger_schema(ledger):
    assert ledger["schema_version"] in ("1.0.0", "1.1.0")
    assert ledger["case_id"] == "osborn_2021_03"
    assert ledger["total_events"] == len(ledger["events"])
    assert ledger.get("report_summary_count", 0) >= 7 or ledger["total_events"] >= 7


def test_report_summary_rows(ledger):
    summaries = [e for e in ledger["events"] if e.get("row_kind") == "report_summary"]
    assert len(summaries) >= 7
    assert all(e["claimed_in_report"] for e in summaries)
    # Palpation must not appear as a false "undocumented test" summary row.
    assert not any(e["test_type"] == "palpation" for e in summaries)


def test_no_palpation_false_undocumented(ledger):
    palpation = [e for e in ledger["events"] if e.get("test_type") == "palpation"]
    for row in palpation:
        assert row.get("three_way_status") != "observed_not_reported"


def test_events_have_required_fields(ledger):
    sample = ledger["events"][0]
    for key in (
        "test_name",
        "test_type",
        "body_region",
        "claimed_in_report",
        "observed_on_video",
        "three_way_status",
        "technique_verdict",
    ):
        assert key in sample


def test_claim_only_events_present(ledger):
    claim_only = [e for e in ledger["events"] if e["three_way_status"] == "claimed_not_observed"]
    assert len(claim_only) >= 1
    assert all(not e["observed_on_video"] for e in claim_only)


def test_observed_events_have_timestamps(ledger):
    observed = [e for e in ledger["events"] if e["observed_on_video"]]
    assert observed
    assert all(e["start_sec"] is not None for e in observed)


def test_build_script_import():
    import sys

    scripts_dir = str(REPO / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from build_test_ledger import build_ledger, group_frames

    frames_path = REPO / "cme_projects/osborn_2021_03/analysis_run_halfsec/comprehensive/comprehensive_frame_analyses.json"
    if not frames_path.is_file():
        pytest.skip("Osborne frame analyses not present")
    built = build_ledger(
        frames_path=frames_path,
        claims_path=REPO / "cme_projects/osborn_2021_03/claims.json",
    )
    assert built["report_summary_count"] >= 7
    assert built["claimed_only_count"] >= 1
    assert group_frames([]) == []
