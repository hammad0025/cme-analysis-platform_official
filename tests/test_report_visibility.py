"""Tests for the visibility / confidence / per-claim caveat surface in
the standard CME report (A7).

All tests run fully offline: the helpers in cme_report_builder are pure
Python (no subprocess, no Chrome), and the end-to-end HTML assertion
exercises only build_standard_html which is also pure Python."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.lambda_functions.cme_report_builder import (  # noqa: E402
    build_standard_html,
    compute_visibility_breakdown,
    merge_frame_rows,
)


def _make_comp_frame(
    frame_id: str,
    *,
    timestamp_sec: float = 0,
    visibility: str = "full",
    confidence: float = 0.9,
    test_type: str = "rom",
    body_region: str = "cervical_spine",
    notes: str = "",
    distress: bool = False,
    occlusion_notes: str = "",
) -> dict:
    return {
        "frame_id": frame_id,
        "timestamp_sec": timestamp_sec,
        "test_type": test_type,
        "body_region": body_region,
        "patient_attire": "gown",
        "doctor_making_eye_contact": True,
        "patient_visible_distress": distress,
        "equipment_visible": [],
        "notes": notes,
        "visibility": visibility,
        "occlusion_notes": occlusion_notes,
        "confidence": confidence,
    }


def _make_behavior_obs(
    frame_id: str,
    *,
    visibility: str = "full",
    confidence: float = 0.8,
    notes: str = "",
    doctor_looking_at_patient: bool = True,
) -> dict:
    return {
        "frame_id": frame_id,
        "timestamp_sec": 0,
        "doctor_looking_at_patient": doctor_looking_at_patient,
        "visibility": visibility,
        "confidence": confidence,
        "notes": notes,
    }


# ----------------------------------------------------------------------
# Helper: percentages
# ----------------------------------------------------------------------


def test_compute_visibility_breakdown_mostly_full_with_some_partial_and_obscured():
    """Mixed visibility rows: ten frames where mostly `full`, two
    `partial`, one `obscured`. Percentages must be integer-rounded over
    the full count and ordered as documented."""
    rows = [
        {"visibility": "full"},
        {"visibility": "full"},
        {"visibility": "full"},
        {"visibility": "full"},
        {"visibility": "full"},
        {"visibility": "full"},
        {"visibility": "full"},
        {"visibility": "partial"},
        {"visibility": "partial"},
        {"visibility": "obscured"},
    ]
    bd = compute_visibility_breakdown(rows)
    assert bd["full"] == 7
    assert bd["partial"] == 2
    assert bd["obscured"] == 1
    assert bd["unknown"] == 0
    assert bd["total"] == 10
    assert bd["full_pct"] == 70
    assert bd["partial_pct"] == 20
    assert bd["obscured_pct"] == 10


def test_compute_visibility_breakdown_unknown_token_falls_through_to_unknown_bucket():
    """Tokens outside the canonical set (`unknown`, ``, None) all roll
    into `unknown` and do NOT inflate any of the three named buckets."""
    rows = [
        {"visibility": "full"},
        {"visibility": "unknown"},
        {"visibility": ""},
        {"visibility": None},
        {"visibility": "garbage"},
    ]
    bd = compute_visibility_breakdown(rows)
    assert bd["full"] == 1
    assert bd["partial"] == 0
    assert bd["obscured"] == 0
    assert bd["unknown"] == 4
    assert bd["full_pct"] == 20


# ----------------------------------------------------------------------
# merge_frame_rows propagates visibility / confidence
# ----------------------------------------------------------------------


def test_merge_frame_rows_propagates_visibility_and_confidence_from_both_passes():
    """The merged row schema must carry visibility/occlusion_notes/
    confidence from the comprehensive pass and visibility/confidence
    from the behavior pass under suffixed keys."""
    comp = [
        _make_comp_frame(
            "video1_frame_0001",
            visibility="partial",
            confidence=0.55,
            occlusion_notes="patient half off-frame",
        ),
    ]
    behavior = {
        "visual_observations": [
            _make_behavior_obs(
                "video1_frame_0001", visibility="obscured", confidence=0.4
            )
        ]
    }
    merged, _stats = merge_frame_rows(comp, behavior, interval_sec=5.0)
    assert merged[0]["visibility"] == "partial"
    assert merged[0]["occlusion_notes"] == "patient half off-frame"
    assert merged[0]["confidence"] == pytest.approx(0.55)
    assert merged[0]["behavior_visibility"] == "obscured"
    assert merged[0]["behavior_confidence"] == pytest.approx(0.4)


def test_merge_frame_rows_old_checkpoint_without_new_fields_rehydrates_cleanly():
    """Pre-A7 checkpoints stored frames without visibility / confidence.
    Such rows must merge without raising and must yield empty / None
    defaults for the new fields so the report degrades gracefully."""
    legacy_comp = [
        {
            "frame_id": "video1_frame_0001",
            "timestamp_sec": 0.0,
            "test_type": "rom",
            "body_region": "cervical_spine",
            "patient_attire": "gown",
            "doctor_making_eye_contact": True,
            "patient_visible_distress": False,
            "equipment_visible": [],
            "notes": "",
        }
    ]
    merged, _stats = merge_frame_rows(legacy_comp, None, interval_sec=5.0)
    assert merged[0]["visibility"] == ""
    assert merged[0]["confidence"] is None
    assert merged[0]["behavior_visibility"] == ""
    assert merged[0]["behavior_confidence"] is None


# ----------------------------------------------------------------------
# build_standard_html: visibility coverage section + low-conf callout
# ----------------------------------------------------------------------


def _case_meta(generated="2026-05-26 10:00") -> dict:
    return {
        "patient": "Jane Doe",
        "dob": "1980-01-01",
        "examiner": "Dr. Test",
        "exam_date": "2026-01-01",
        "injury_date": "2025-06-01",
        "video_length": "5:00",
        "generated": generated,
        "run_id": "run123",
        "bundle_sha256": "abc",
        "interval_sec": 5.0,
    }


def _high_conf_payload():
    """5 frames; mostly full visibility; one partial; high confidence."""
    comp_frames = [
        _make_comp_frame(f"video1_frame_{i:04d}",
                         timestamp_sec=i * 5,
                         visibility="full" if i != 3 else "partial",
                         confidence=0.85)
        for i in range(1, 6)
    ]
    behavior_obs = [
        _make_behavior_obs(f["frame_id"], visibility=f["visibility"], confidence=0.8)
        for f in comp_frames
    ]
    return comp_frames, {"visual_observations": behavior_obs}


def _low_conf_payload():
    """3 frames; visibility OK; confidence low so the callout fires."""
    comp_frames = [
        _make_comp_frame(f"video1_frame_{i:04d}",
                         timestamp_sec=i * 5,
                         visibility="full",
                         confidence=0.3)
        for i in range(1, 4)
    ]
    behavior_obs = [
        _make_behavior_obs(f["frame_id"], visibility="full", confidence=0.3)
        for f in comp_frames
    ]
    return comp_frames, {"visual_observations": behavior_obs}


def test_visibility_section_renders_once_and_findings_show_pills():
    comp_frames, behavior = _high_conf_payload()
    merged, stats = merge_frame_rows(comp_frames, behavior, interval_sec=5.0)
    from backend.lambda_functions.cme_report_builder import _build_timeline

    timeline = _build_timeline(merged, interval_sec=5.0)

    html = build_standard_html(
        _case_meta(),
        merged,
        timeline,
        stats,
        claims={},
        claim_verdicts=[],
    )

    assert html.count("VISIBILITY COVERAGE") == 1
    top_findings_chunk = html.split("MAIN ISSUES IDENTIFIED", 1)[1].split("EXAMINATION TIMELINE", 1)[0]
    assert "Claim verification not run" in top_findings_chunk
    assert "Frames Analyzed" not in html.split("EXECUTIVE SUMMARY", 1)[0]


def test_low_confidence_callout_fires_below_threshold():
    comp_frames, behavior = _low_conf_payload()
    merged, stats = merge_frame_rows(comp_frames, behavior, interval_sec=5.0)
    from backend.lambda_functions.cme_report_builder import _build_timeline

    timeline = _build_timeline(merged, interval_sec=5.0)

    html = build_standard_html(
        _case_meta(),
        merged,
        timeline,
        stats,
        claims={},
        claim_verdicts=[],
    )
    assert "Low average model confidence" in html


def test_low_confidence_callout_silent_when_above_threshold():
    """Same shape as the low-conf case but with confidences >= 0.6 means
    the callout must NOT render."""
    comp_frames, behavior = _high_conf_payload()
    merged, stats = merge_frame_rows(comp_frames, behavior, interval_sec=5.0)
    from backend.lambda_functions.cme_report_builder import _build_timeline

    timeline = _build_timeline(merged, interval_sec=5.0)
    html = build_standard_html(
        _case_meta(),
        merged,
        timeline,
        stats,
        claims={},
        claim_verdicts=[],
    )
    assert "Low average model confidence" not in html


# ----------------------------------------------------------------------
# build_standard_html: per-claim caveat
# ----------------------------------------------------------------------


def test_partial_visibility_caveat_renders_in_claim_verdict_row():
    """A claim whose cited Evidence sits on a partial-visibility frame
    must show the `(visibility: partial at most cited frames)`
    parenthetical in the reasoning cell."""
    comp_frames = [
        _make_comp_frame(
            "video1_frame_0010",
            timestamp_sec=45,
            visibility="partial",
            confidence=0.7,
            test_type="rom",
            body_region="cervical_spine",
        ),
        _make_comp_frame(
            "video1_frame_0011",
            timestamp_sec=50,
            visibility="full",
            confidence=0.95,
            test_type="rom",
            body_region="cervical_spine",
        ),
    ]
    behavior = {"visual_observations": []}
    merged, stats = merge_frame_rows(comp_frames, behavior, interval_sec=5.0)
    from backend.lambda_functions.cme_report_builder import _build_timeline

    timeline = _build_timeline(merged, interval_sec=5.0)

    claim_verdicts = [
        {
            "claim_id": "rom",
            "claim_text": "Cervical ROM within normal limits.",
            "verdict": "partially_supported",
            "confidence": 0.6,
            "reasoning": "Some ROM testing observed.",
            "evidence": [
                {
                    "kind": "frame",
                    "frame_id": "video1_frame_0010",
                    "timestamp_sec": 45,
                    "notes": "partial view",
                }
            ],
            "model_id": "fake",
            "provider": "fake",
        }
    ]
    html = build_standard_html(
        _case_meta(),
        merged,
        timeline,
        stats,
        claims={},
        claim_verdicts=claim_verdicts,
    )
    assert "(visibility: partial" in html


def test_full_visibility_evidence_does_not_attach_caveat():
    """When every cited Evidence frame is `full`, the caveat must not
    appear in the reasoning cell."""
    comp_frames = [
        _make_comp_frame(
            "video1_frame_0010",
            timestamp_sec=45,
            visibility="full",
            confidence=0.9,
            test_type="rom",
        ),
    ]
    merged, stats = merge_frame_rows(comp_frames, {"visual_observations": []}, interval_sec=5.0)
    from backend.lambda_functions.cme_report_builder import _build_timeline

    timeline = _build_timeline(merged, interval_sec=5.0)
    claim_verdicts = [
        {
            "claim_id": "rom",
            "claim_text": "x",
            "verdict": "supported",
            "confidence": 0.9,
            "reasoning": "Frame f confirms ROM.",
            "evidence": [
                {"kind": "frame", "frame_id": "video1_frame_0010", "notes": "rom"},
            ],
            "model_id": "fake",
            "provider": "fake",
        }
    ]
    html = build_standard_html(
        _case_meta(),
        merged,
        timeline,
        stats,
        claims={},
        claim_verdicts=claim_verdicts,
    )
    assert "(visibility: partial" not in html
    assert "(visibility: obscured" not in html
