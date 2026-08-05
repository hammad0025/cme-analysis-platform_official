"""Tests for aggressive main-issue ranking (trial-lawyer focus)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.lambda_functions.cme_egregious_ranking import (  # noqa: E402
    build_duration_finding,
    build_numbered_cross_examinations,
    classify_issue_type,
    compute_egregious_score,
    is_banned_noise,
    is_metadata_claim_id,
    passes_materiality_gate,
    rank_main_issues,
)


def _row(**kwargs):
    base = {
        "claim_id": "test",
        "test_name": "Test",
        "verdict": "insufficient_evidence",
        "confidence": 0.5,
        "report_quote": "Sample quote",
        "video_shows": "",
        "reasoning": "",
        "evidence": [],
    }
    base.update(kwargs)
    return base


def test_metadata_claims_filtered_from_ranking():
    verdicts = [
        _row(claim_id="plaintiff", verdict="not_shown", claim_text="Alan Deshefy"),
        _row(claim_id="exam_date", verdict="not_shown", claim_text="Feb 2026"),
        _row(claim_id="examiner", verdict="insufficient_evidence", claim_text="Dr. X"),
    ]
    ranked = rank_main_issues(verdicts)
    assert ranked == []


def test_contradictions_rank_highest():
    verdicts = [
        _row(
            claim_id="general_appearance",
            verdict="supported",
            confidence=0.9,
            report_quote="well appearing",
        ),
        _row(
            claim_id="mental_status",
            verdict="insufficient_evidence",
            confidence=0.4,
        ),
        _row(
            claim_id="skin",
            verdict="contradicted",
            confidence=0.95,
            report_quote="No abrasions",
            video_shows="Bruising visible on left knee",
        ),
        _row(
            claim_id="lower_extremity_strength",
            verdict="contradicted",
            confidence=0.85,
            report_quote="5/5 strength",
            video_shows="Patient states no leg strength",
        ),
    ]
    ranked = rank_main_issues(verdicts)
    assert len(ranked) == 2
    assert {r["claim_id"] for r in ranked} == {"skin", "lower_extremity_strength"}
    assert ranked[0]["egregious_score"] >= ranked[1]["egregious_score"]


def test_rom_partial_with_degrees_scores_high():
    row = _row(
        claim_id="rom_left_knee",
        verdict="partially_supported",
        confidence=0.65,
        report_quote="Active extension limited to 17 degrees (flexion contracture)",
        reasoning="ROM in wheelchair, no goniometer visible",
        video_shows="ROM tested in street clothes without goniometer",
    )
    assert classify_issue_type(row) == "rom_gap"
    assert compute_egregious_score(row) >= 50


def test_three_way_performed_not_reported_included():
    ledger = {
        "rows": [
            {
                "test_name": "Hoffmann sign",
                "named_test_key": "hoffmann_sign",
                "three_way_status": "performed_not_reported",
                "timestamp_sec": 1420.0,
                "frame_ids": ["video1_frame_0285"],
                "technique_notes": ["UE testing visible"],
                "deposition_prompt": "Doctor, Hoffmann sign on video but not in report — explain.",
            }
        ]
    }
    ranked = rank_main_issues([], three_way_ledger=ledger)
    assert len(ranked) == 1
    assert ranked[0]["verdict"] == "performed_not_reported"
    assert ranked[0]["egregious_score"] >= 50


def test_low_priority_supported_appearance_excluded():
    row = _row(claim_id="general_appearance", verdict="supported", confidence=0.9)
    assert compute_egregious_score(row) == 0
    assert is_metadata_claim_id("plaintiff") is True


# ----------------------------------------------------------------------
# Materiality gate + numbered cross-examination findings
# ----------------------------------------------------------------------


def test_transcription_name_noise_is_hard_banned():
    """The exact class of garbage the user complained about must never score."""
    row = _row(
        claim_id="patient_identification",
        verdict="contradicted",
        confidence=0.95,
        report_quote="Patient: A. Gadson",
        video_shows="At the 2 second mark the name was recorded improperly.",
        evidence=[{"kind": "quote", "timestamp_sec": 2.0, "quote": "name recorded improperly"}],
    )
    assert is_banned_noise(row)
    assert compute_egregious_score(row) == 0
    assert not passes_materiality_gate(row)
    assert build_numbered_cross_examinations([row]) == []


def test_demeanor_only_complaint_is_banned_but_exam_substance_passes():
    demeanor_only = _row(
        claim_id="bedside",
        verdict="contradicted",
        confidence=0.9,
        report_quote="The examination was professional.",
        video_shows="The doctor was not nice and seemed dismissive in tone.",
        evidence=[{"kind": "frame", "timestamp_sec": 100.0}],
    )
    assert is_banned_noise(demeanor_only)
    assert not passes_materiality_gate(demeanor_only)

    substantive = _row(
        claim_id="motor_strength",
        verdict="contradicted",
        confidence=0.9,
        report_quote="Manual muscle testing 5/5 throughout.",
        video_shows="Strength testing performed through clothing in a dismissive, rushed manner.",
        evidence=[{"kind": "frame", "timestamp_sec": 864.0}],
    )
    assert not is_banned_noise(substantive)
    assert passes_materiality_gate(substantive)


def test_finding_without_timestamp_rejected_unless_not_shown():
    no_ts = _row(
        claim_id="motor_strength",
        verdict="contradicted",
        confidence=0.9,
        report_quote="5/5 strength.",
        video_shows="Testing looked incomplete.",
        evidence=[],
    )
    assert not passes_materiality_gate(no_ts)

    not_shown = _row(
        claim_id="reflexes",
        verdict="not_shown",
        confidence=0.9,
        report_quote="DTRs 2+ throughout.",
        video_shows="No reflex testing visible anywhere on the video.",
        evidence=[],
    )
    assert passes_materiality_gate(not_shown)


def test_numbered_cross_examinations_format_and_ordering():
    verdicts = [
        _row(
            claim_id="reflexes",
            test_name="Deep tendon reflexes",
            verdict="not_shown",
            confidence=0.9,
            report_quote="DTRs 2+ at biceps, triceps, patella.",
            video_shows="No reflex hammer or reflex testing appears on the video.",
            evidence=[],
        ),
        _row(
            claim_id="motor_strength",
            test_name="Manual muscle testing",
            verdict="contradicted",
            confidence=0.9,
            report_quote="Manual muscle testing 5/5 throughout.",
            video_shows="Strength testing barely attempted; single brief resistance check.",
            evidence=[{"kind": "frame", "timestamp_sec": 1333.0}],
        ),
    ]
    findings = build_numbered_cross_examinations(verdicts)
    assert [f["number"] for f in findings] == [1, 2]
    # Contradiction must lead (most damning first).
    assert findings[0]["claim_id"] == "motor_strength"
    assert findings[0]["claim_statement"].startswith("Doctor stated in his report")
    assert "22:13" in findings[0]["fact_statement"] or "See" in findings[0]["fact_statement"]
    assert findings[0]["timestamps"][0]["label"] == "22:13"
    # not_shown finding still carries a FACT with a video citation.
    assert "FACT" not in findings[1]["fact_statement"]  # renderer adds the FACT label
    assert "video" in findings[1]["fact_statement"].lower()


def test_duration_finding_fires_only_on_material_discrepancy():
    summary = {
        "claimed_exam_time_min": 30,
        "actual_hands_on_exam_sec": 345.5,
        "total_video_duration_sec": 1308.4,
    }
    row = build_duration_finding(summary, exam_window={"start": "5:06", "end": "10:52"})
    assert row is not None
    assert row["verdict"] == "contradicted"
    assert passes_materiality_gate(row)
    assert compute_egregious_score(row) > 100

    ok = build_duration_finding(
        {"claimed_exam_time_min": 30, "actual_hands_on_exam_sec": 25 * 60},
        exam_window={"start": "5:06", "end": "30:06"},
    )
    assert ok is None
