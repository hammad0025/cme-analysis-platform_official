"""Tests for the VERBAL EVIDENCE section rendered by cme_report_builder.

The section must:
- Render when a `transcript.json` dict is passed.
- Be omitted entirely when no transcript is passed (no empty stub).
- Surface up to 5 flagged problematic quotes pulled from
  `BehaviorAnalysisResult.verbal_observations`.
- Embed the full transcript inside a collapsible <details> block.
- Append the honest-uncertainty caveat to its header when the backend
  is `openai-whisper-api` and `mean_word_confidence == 0.0`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.lambda_functions.cme_report_builder import (  # noqa: E402
    build_standard_html,
    render_verbal_evidence_section,
    _has_transcript_evidence,
)


def _minimal_case_meta():
    return {
        "patient": "Test Patient",
        "dob": "",
        "examiner": "",
        "exam_date": "",
        "injury_date": "",
        "video_length": "0:00",
        "interval_sec": 5.0,
    }


def _empty_inputs():
    return [], {"total_frames": 0, "looking_pct": 0, "goniometer_frames": 0}, {
        "exam_window": {"start": "0:00", "end": "0:00", "duration_seconds": 0},
        "test_timeline": {},
        "body_part_timeline": {},
        "distress_events": [],
        "doctor_behavior_concerns": [],
    }


def _transcript_payload(backend="faster-whisper", mean_conf=0.85):
    return {
        "language": "en",
        "duration_sec": 30.0,
        "backend": backend,
        "model_id": "large-v3" if backend == "faster-whisper" else "whisper-1",
        "segments": [
            {"start_sec": 0.0, "end_sec": 12.0, "text": "Tell me about the accident."},
            {"start_sec": 12.5, "end_sec": 25.0, "text": "How does your neck feel today?"},
        ],
        "word_count": 11,
        "mean_word_confidence": mean_conf,
        "raw_path": "transcript.raw.json",
    }


def _behavior_payload_with_flagged_quote():
    return {
        "verbal_observations": [
            {
                "segment_id": "seg_0_0",
                "start_sec": 14.0,
                "end_sec": 16.0,
                "speaker": "doctor",
                "text": "Quit complaining about it.",
                "tone": "rude",
                "rude_comment": True,
                "problematic_quote": "Quit complaining about it.",
            },
            {
                "segment_id": "seg_0_1",
                "start_sec": None,
                "end_sec": None,
                "speaker": "doctor",
                "text": "It can't really be that bad.",
                "tone": "dismissive",
                "dismissing_symptom": True,
                "problematic_quote": "It can't really be that bad.",
            },
            {
                "segment_id": "seg_0_2",
                "start_sec": 30.0,
                "end_sec": 31.0,
                "speaker": "patient",
                "text": "I am in pain.",
                "tone": "distressed",
                "problematic_quote": "",
            },
        ]
    }


def test_verbal_evidence_section_renders_when_transcript_present():
    merged, stats, timeline = _empty_inputs()
    html = build_standard_html(
        _minimal_case_meta(),
        merged,
        timeline,
        stats,
        claims=None,
        claim_verdicts=[],
        transcript=_transcript_payload(),
        behavior_result=_behavior_payload_with_flagged_quote(),
    )
    assert "VERBAL EVIDENCE" in html
    assert "Transcribed via faster-whisper/large-v3" in html
    assert "Quit complaining about it." in html
    # second flagged quote (no timestamp) also shows up
    assert "It can&#x27;t really be that bad." in html or "It can't really be that bad." in html
    assert "[--:--]" in html
    # collapsible full-transcript block uses <details>
    assert "<details" in html and "Full transcript" in html


def test_verbal_evidence_section_absent_when_transcript_missing():
    merged, stats, timeline = _empty_inputs()
    html = build_standard_html(
        _minimal_case_meta(),
        merged,
        timeline,
        stats,
        claims=None,
        claim_verdicts=[],
        transcript=None,
        behavior_result=None,
    )
    assert "VERBAL EVIDENCE" not in html


def test_verbal_evidence_header_carries_honest_uncertainty_for_openai_without_word_probs():
    """openai-whisper-api with mean_word_confidence == 0.0 should append
    the documented caveat to the section header."""
    section = render_verbal_evidence_section(
        _transcript_payload(backend="openai-whisper-api", mean_conf=0.0),
        _behavior_payload_with_flagged_quote(),
    )
    assert "VERBAL EVIDENCE (transcript confidence not estimable for this backend)" in section


def test_verbal_evidence_header_no_caveat_for_faster_whisper_zero_confidence():
    """The caveat is keyed on `backend == openai-whisper-api`, not on the
    raw `mean_word_confidence == 0` value. faster-whisper produces real
    confidences so the caveat must not appear for that backend regardless."""
    section = render_verbal_evidence_section(
        _transcript_payload(backend="faster-whisper", mean_conf=0.0),
        None,
    )
    assert "transcript confidence not estimable" not in section


def test_has_transcript_evidence_helper_detects_transcript_span_kind():
    """The verdict-table reasoning caveat depends on this helper."""
    assert _has_transcript_evidence(
        [{"kind": "transcript_span", "quote": "hi"}, {"kind": "frame"}]
    )
    assert not _has_transcript_evidence([{"kind": "frame"}])
    assert not _has_transcript_evidence([])


def test_claim_verdict_table_appends_verbal_evidence_when_transcript_span_cited():
    """When a claim verdict cites transcript_span evidence, the reasoning
    cell should be suffixed with `(verbal evidence)`."""
    merged, stats, timeline = _empty_inputs()
    claim_verdicts = [
        {
            "claim_id": "c1",
            "claim_text": "Doctor said the patient was malingering.",
            "verdict": "supported",
            "confidence": 0.8,
            "reasoning": "Patient was dismissed verbally.",
            "evidence": [
                {"kind": "transcript_span", "quote": "Quit complaining about it."}
            ],
        }
    ]
    html = build_standard_html(
        _minimal_case_meta(),
        merged,
        timeline,
        stats,
        claims=None,
        claim_verdicts=claim_verdicts,
        transcript=_transcript_payload(),
        behavior_result=_behavior_payload_with_flagged_quote(),
    )
    assert "(verbal evidence)" in html
