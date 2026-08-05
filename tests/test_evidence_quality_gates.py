"""Regression tests for centralized video evidence quality gates."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.lambda_functions.cme_evidence_quality import (  # noqa: E402
    BROLL_NOTE_PHRASES,
    NON_EXAM_TEST_TYPES,
    WORD_BOUNDARY_KEYWORDS,
    clean_evidence_note_for_display,
    cluster_evidence_timestamps,
    evidence_description_for_frame,
    evidence_notes_are_usable,
    expand_claim_keywords,
    filter_frames_for_claim,
    is_non_exam_frame,
    notes_indicate_broll,
    select_evidence_frames_for_claim,
    summarize_video_evidence,
)
from backend.lambda_functions.cme_claim_verifier import relevant_frames  # noqa: E402


def _frame(
    frame_id: str,
    *,
    timestamp_sec: float,
    test_type: str = "",
    body_region: str = "",
    notes: str = "",
    visibility: str = "full",
    confidence: float = 0.9,
    establishing_shot: bool = False,
) -> dict:
    return {
        "frame_id": frame_id,
        "timestamp_sec": timestamp_sec,
        "test_type": test_type,
        "body_region": body_region,
        "notes": notes,
        "visibility": visibility,
        "confidence": confidence,
        "establishing_shot": establishing_shot,
    }


def test_building_exterior_never_passes_physical_exam_claims():
    building = _frame(
        "bldg",
        timestamp_sec=8.0,
        test_type="none",
        body_region="none",
        notes="Exterior of medical building; no patient or medical examination visible.",
    )
    assert is_non_exam_frame(building)
    for claim_id, claim_text in (
        ("cervical_rom", "Cervical ROM within normal limits"),
        ("reflexes", "DTRs 2+ at biceps"),
        ("gait", "Gait normal on heels and toes"),
    ):
        matched = filter_frames_for_claim([building], claim_id, claim_text)
        assert matched == [], f"{claim_id} must not match building exterior"
        assert relevant_frames(claim_id, claim_text, [building]) == []


def test_real_neck_rom_passes_cervical_rom():
    rom = _frame(
        "neck",
        timestamp_sec=500.0,
        test_type="rom",
        body_region="neck",
        notes="Doctor performing cervical flexion and extension with goniometer.",
    )
    matched = filter_frames_for_claim([rom], "cervical_rom", "Cervical ROM with sidebending")
    assert [f["frame_id"] for f in matched] == ["neck"]


def test_motion_in_examination_does_not_false_positive():
    conv = _frame(
        "conv",
        timestamp_sec=30.0,
        test_type="conversation",
        body_region="none",
        notes="Patient in street clothes during medical examination; doctor not visible.",
    )
    rom = _frame(
        "rom",
        timestamp_sec=500.0,
        test_type="rom",
        body_region="neck",
        notes="Neck rotation measured during ROM testing.",
    )
    matched = filter_frames_for_claim(
        [conv, rom], "cervical_rom", "Cervical ROM within normal limits"
    )
    assert [f["frame_id"] for f in matched] == ["rom"]


def test_empty_after_filter_yields_not_shown_semantics():
    building = _frame(
        "bldg",
        timestamp_sec=1.0,
        test_type="rom",
        body_region="none",
        notes="Exterior establishing shot of clinic; no patient visible.",
    )
    matched = filter_frames_for_claim([building], "cervical_rom", "Cervical ROM normal")
    assert matched == []
    summary = summarize_video_evidence(matched)
    assert "not sampled" in summary.lower() or "not detected" in summary.lower()


def test_summarize_video_evidence_skips_broll():
    frames = [
        _frame(
            "broll",
            timestamp_sec=1.0,
            test_type="none",
            body_region="none",
            notes="Empty hallway; no examination activity.",
        ),
        _frame(
            "exam",
            timestamp_sec=100.0,
            test_type="reflex",
            body_region="arm",
            notes="Reflex hammer used at biceps.",
        ),
    ]
    summary = summarize_video_evidence(frames)
    assert "hallway" not in summary.lower()
    assert "reflex" in summary.lower() or "biceps" in summary.lower()


def test_exported_constants_for_regression():
    assert "exterior" in BROLL_NOTE_PHRASES
    assert "none" in NON_EXAM_TEST_TYPES
    assert "motion" in WORD_BOUNDARY_KEYWORDS


def test_notes_indicate_broll():
    assert notes_indicate_broll("Exterior of building, no patient")
    assert not notes_indicate_broll("Neck flexion with goniometer")


def test_hallway_gait_without_doctor_fails_gait_claim():
    hallway = _frame(
        "hall",
        timestamp_sec=200.0,
        test_type="gait",
        body_region="leg",
        notes="Patient walking in hallway. Doctor not visible in frame. Rear view only.",
    )
    assert filter_frames_for_claim([hallway], "gait", "Gait normal on heels and toes") == []


def test_motor_strength_rejects_attire_only_conversation_frame():
    """Mis-tagged strength at 1:30 with only gown/street-clothes notes must not match MMT."""
    mislabeled = _frame(
        "conv_strength",
        timestamp_sec=90.0,
        test_type="strength",
        body_region="arm",
        notes=(
            "Patient is wearing full street clothes during examination rather than medical gown, "
            "which could impact thoroughness of examination. Doctor appears focused on the testing."
        ),
    )
    real = _frame(
        "real_mmt",
        timestamp_sec=864.5,
        test_type="strength",
        body_region="arm",
        notes=(
            "Patient remains fully clothed in street clothes during examination which could "
            "compromise accuracy of strength testing and other assessments."
        ),
    )
    real["test_details"] = (
        "appears to be testing arm/shoulder strength with doctor's hands positioned on patient's arm"
    )
    mislabeled["test_details"] = (
        "doctor appears to be performing manual muscle testing or resistance testing with patient's arm/hand"
    )

    matched = filter_frames_for_claim(
        [mislabeled, real],
        "motor_strength",
        "Manual muscle testing (5/5 throughout): 5/5 strength throughout",
    )
    assert [f["frame_id"] for f in matched] == ["real_mmt"]

    selected = select_evidence_frames_for_claim(
        matched,
        "motor_strength",
        "Manual muscle testing (5/5 throughout): 5/5 strength throughout",
        max_frames=4,
    )
    assert [f["frame_id"] for f in selected] == ["real_mmt"]
    desc = evidence_description_for_frame(real, "motor_strength")
    assert desc and "strength" in desc.lower()
    assert not evidence_notes_are_usable(mislabeled["notes"], "motor_strength", frame=mislabeled)


def test_motor_strength_clusters_nearby_timestamps():
    frames = [
        _frame(
            f"f{i}",
            timestamp_sec=864.0 + i,
            test_type="strength",
            body_region="arm",
            notes=f"Strength testing of shoulder with resistance at sample {i}.",
        )
        for i in range(6)
    ]
    frames.append(
        _frame(
            "far",
            timestamp_sec=2000.0,
            test_type="strength",
            body_region="hand",
            notes="Grip strength testing with patient grasping doctor's hand.",
        )
    )
    for fa in frames:
        fa["test_details"] = fa["notes"]

    selected = select_evidence_frames_for_claim(
        filter_frames_for_claim(
            frames,
            "motor_strength",
            "Manual muscle testing (5/5 throughout): 5/5 strength throughout",
        ),
        "motor_strength",
        "Manual muscle testing (5/5 throughout): 5/5 strength throughout",
        max_frames=4,
    )
    assert len(selected) <= 4
    assert all(f["timestamp_sec"] < 900 for f in selected)
    assert selected[0]["frame_id"] == "f0"


def test_expand_claim_keywords_skips_throughout_stopword():
    keywords = expand_claim_keywords(
        "motor_strength",
        "Manual muscle testing (5/5 throughout): 5/5 strength throughout",
    )
    assert "throughout" not in keywords


def test_word_boundary_motion_not_in_examination_token():
    keywords = expand_claim_keywords("cervical_rom", "Cervical examination documented")
    # Keyword expansion should not treat substring 'motion' inside 'examination' as ROM hit.
    conv = _frame(
        "c",
        timestamp_sec=5.0,
        test_type="conversation",
        body_region="none",
        notes="Patient seated during medical examination only.",
    )
    assert filter_frames_for_claim([conv], "cervical_rom", "Cervical examination") == []


def test_cranial_claim_rejects_gait_hallway_frames():
    gait = _frame(
        "gait",
        timestamp_sec=746.0,
        test_type="gait",
        body_region="leg",
        notes=(
            "Doctor in blue scrubs walking behind patient during gait assessment. "
            "Patient wearing street clothes rather than medical gown."
        ),
    )
    cranial = _frame(
        "cranial",
        timestamp_sec=832.0,
        test_type="cranial",
        body_region="head",
        notes="Doctor performing head/cranial examination with hand placement on forehead.",
    )
    matched = filter_frames_for_claim(
        [gait, cranial], "cranial_nerves", "Cranial nerves III-XII grossly normal"
    )
    assert [f["frame_id"] for f in matched] == ["cranial"]


def test_long_tract_claim_rejects_pure_gait_frames():
    gait = _frame(
        "gait",
        timestamp_sec=746.0,
        test_type="gait",
        body_region="leg",
        notes="Doctor walking alongside patient in hallway during gait assessment.",
    )
    reflex = _frame(
        "bab",
        timestamp_sec=900.0,
        test_type="reflex",
        body_region="foot",
        notes="Doctor performing Babinski plantar reflex test on bare foot.",
    )
    matched = filter_frames_for_claim(
        [gait, reflex], "long_tract_signs", "No long tract signs"
    )
    assert [f["frame_id"] for f in matched] == ["bab"]


def test_attire_only_notes_rejected_for_display():
    note = (
        "Patient is wearing full street clothes during examination rather than medical gown, "
        "which could impact thoroughness of examination."
    )
    assert not evidence_notes_are_usable(note, "motor_strength")
    assert not evidence_notes_are_usable(note, "cranial_nerves")


def test_clean_evidence_note_no_mid_word_chop():
    note = (
        "Doctor is performing what appears to be a head/cranial examination. "
        "The positioning suggests active range testing."
    )
    cleaned = clean_evidence_note_for_display(note, max_sentences=2)
    assert cleaned.endswith(".")
    assert "active range testing" in cleaned
    assert not cleaned.endswith(" active r")


def test_cluster_evidence_timestamps_dedupes_by_second():
    frames = [
        _frame("a", timestamp_sec=746.0, test_type="gait", notes="Gait assessment."),
        _frame("b", timestamp_sec=746.5, test_type="gait", notes="Gait continues."),
        _frame("c", timestamp_sec=832.0, test_type="cranial", notes="Cranial exam."),
    ]
    stamps = cluster_evidence_timestamps(frames, max_stamps=4, gap_sec=45)
    assert stamps == [746, 832]
