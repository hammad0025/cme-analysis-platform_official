"""Tests for backend.lambda_functions.cme_claim_verifier.

All tests run fully offline: the verifier is exercised against a fake
VisionClient whose `text_analyze` returns a canned response. No
real Anthropic / OpenAI / Gemini SDK is hit."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.lambda_functions.cme_claim_verifier import (  # noqa: E402
    CLAIM_VERIFIER_PROMPT_VERSION,
    ClaimVerdict,
    Evidence,
    _expand_claim_keywords,
    relevant_frames,
    relevant_observations,
    sanitize_claim_evidence,
    verify_all_claims,
    verify_claim,
)


class _StubResult:
    def __init__(self, text: str, model_id: str = "fake-model", provider: str = "fake"):
        self.text = text
        self.raw_text = text
        self.model_id = model_id
        self.provider = provider
        self.input_tokens = 100
        self.output_tokens = 50
        self.usd_cost_estimate = 0.001
        self.latency_ms = 10
        self.request_id = "stub-req"
        self.extra = {}


class FakeVisionClient:
    """Records calls for assertions and returns a canned text_analyze
    response. Implements only the surface the verifier actually uses."""

    provider = "fake"
    default_model_id = "fake-model"

    def __init__(self, response_text: str):
        self._response_text = response_text
        self.calls: list = []

    def text_analyze(self, prompt: str, *, model_id=None, max_tokens: int = 1500):
        self.calls.append({"prompt": prompt, "model_id": model_id, "max_tokens": max_tokens})
        return _StubResult(self._response_text)

    def analyze(self, *args, **kwargs):
        raise AssertionError("verify_claim must not call analyze()")


def _make_frame(
    frame_id: str,
    *,
    timestamp_sec: float,
    test_type: str = "",
    body_region: str = "",
    notes: str = "",
    raw_response: str = "",
    visibility: str = "full",
) -> dict:
    return {
        "frame_id": frame_id,
        "timestamp_sec": timestamp_sec,
        "test_type": test_type,
        "body_region": body_region,
        "notes": notes,
        "raw_response": raw_response,
        "visibility": visibility,
        "confidence": 0.9,
    }


def test_keyword_expansion_for_reflexes():
    keywords = _expand_claim_keywords("reflexes", "DTRs 2+ at biceps")
    joined = " ".join(keywords)
    assert "reflex" in joined
    assert "hammer" in joined
    assert "dtrs" in joined or "biceps" in joined


def test_keyword_expansion_for_gait():
    keywords = _expand_claim_keywords("gait", "Patient walked normally on heels and toes")
    joined = " ".join(keywords)
    assert "gait" in joined
    assert "walk" in joined
    assert "tandem" in joined


def test_keyword_expansion_for_rom():
    keywords = _expand_claim_keywords("rom", "Cervical flexion 50 deg by goniometer")
    joined = " ".join(keywords)
    assert "rom" in joined
    assert "goniometer" in joined
    assert "cervical" in joined


def test_relevant_frames_filters_by_keyword():
    frames = [
        _make_frame("f1", timestamp_sec=10, test_type="conversation", body_region="none"),
        _make_frame("f2", timestamp_sec=20, test_type="reflex", body_region="arm", notes="DTRs at biceps"),
        _make_frame("f3", timestamp_sec=30, test_type="rom", body_region="cervical_spine"),
    ]
    matched = relevant_frames("reflexes", "DTRs 2+ biceps", frames)
    assert [f["frame_id"] for f in matched] == ["f2"]

    rom_matched = relevant_frames("rom", "Cervical ROM 50 deg", frames)
    assert "f3" in {f["frame_id"] for f in rom_matched}


def test_relevant_frames_excludes_broll_and_ambient_conversation():
    frames = [
        _make_frame(
            "building",
            timestamp_sec=8,
            test_type="none",
            body_region="none",
            visibility="obscured",
            notes="Exterior of medical building; no patient or medical examination visible.",
        ),
        _make_frame(
            "waiting",
            timestamp_sec=25,
            test_type="none",
            body_region="none",
            notes="Patient seated in examination room waiting area wearing street clothes.",
        ),
        _make_frame(
            "exam",
            timestamp_sec=400,
            test_type="rom",
            body_region="neck",
            notes="Doctor performing cervical flexion and extension with goniometer.",
        ),
    ]
    matched = relevant_frames(
        "cervical_rom",
        "Cervical ranges of motion normal with mild sidebending limitation",
        frames,
    )
    assert [f["frame_id"] for f in matched] == ["exam"]


def test_relevant_frames_motor_strength_excludes_attire_only_mislabel():
    frames = [
        _make_frame(
            "mislabeled",
            timestamp_sec=90.0,
            test_type="strength",
            body_region="arm",
            notes=(
                "Patient in street clothes during examination rather than medical gown. "
                "Doctor appears focused on the testing."
            ),
        ),
        _make_frame(
            "real",
            timestamp_sec=864.5,
            test_type="strength",
            body_region="arm",
            notes="Strength testing of the arm with resistance; doctor's hands on patient's arm.",
        ),
    ]
    frames[1]["test_details"] = frames[1]["notes"]
    matched = relevant_frames(
        "motor_strength",
        "Manual muscle testing (5/5 throughout): 5/5 strength throughout",
        frames,
        max_frames=4,
    )
    assert [f["frame_id"] for f in matched] == ["real"]


def test_relevant_frames_does_not_match_motion_inside_examination():
    frames = [
        _make_frame(
            "conv",
            timestamp_sec=30,
            test_type="conversation",
            body_region="none",
            notes="Patient in street clothes during medical examination; doctor not visible.",
        ),
        _make_frame(
            "rom",
            timestamp_sec=500,
            test_type="rom",
            body_region="neck",
            notes="Neck rotation measured during ROM testing.",
        ),
    ]
    matched = relevant_frames("cervical_rom", "Cervical ROM within normal limits", frames)
    assert [f["frame_id"] for f in matched] == ["rom"]


def test_verify_claim_parses_canned_response_and_stamps_metadata(tmp_path: Path):
    canned = json.dumps(
        {
            "verdict": "not_shown",
            "confidence": 0.65,
            "reasoning": "No reflex hammer in the matched frames; testing was never sampled on camera.",
            "evidence": [
                {
                    "kind": "absence",
                    "notes": "No frames flagged as reflex test in this run.",
                }
            ],
        }
    )
    client = FakeVisionClient(canned)
    frames = [_make_frame("f1", timestamp_sec=10, test_type="conversation")]

    verdict = verify_claim(
        "reflexes",
        "DTRs 2+ bilaterally at biceps, triceps, patella, achilles",
        frame_analyses=frames,
        behavior_observations=[],
        verbal_observations=[],
        vision_client=client,
        output_dir=tmp_path,
    )

    assert isinstance(verdict, ClaimVerdict)
    assert verdict.claim_id == "reflexes"
    assert verdict.verdict == "not_shown"
    assert 0.6 <= verdict.confidence <= 0.7
    assert verdict.evidence and verdict.evidence[0].kind == "absence"
    assert verdict.model_id == "fake-model"
    assert verdict.provider == "fake"
    assert verdict.prompt_version == CLAIM_VERIFIER_PROMPT_VERSION

    # Raw text was persisted for the provenance bundle.
    raw_path = tmp_path / "claim_verdicts_raw" / "reflexes.txt"
    assert raw_path.exists()
    assert "not_shown" in raw_path.read_text(encoding="utf-8")


def test_verify_claim_unparseable_response_yields_insufficient(tmp_path: Path):
    client = FakeVisionClient("this is not JSON; maybe the model bailed out mid-sentence")
    verdict = verify_claim(
        "rom",
        "Cervical ROM within normal limits",
        frame_analyses=[],
        behavior_observations=[],
        verbal_observations=[],
        vision_client=client,
        output_dir=tmp_path,
    )

    assert verdict.verdict == "insufficient_evidence"
    assert verdict.confidence == 0.0
    assert verdict.reasoning == "model output unparseable"
    assert verdict.evidence == []

    raw_path = tmp_path / "claim_verdicts_raw" / "rom.txt"
    assert raw_path.exists()
    assert "not JSON" in raw_path.read_text(encoding="utf-8")


def test_verify_claim_strips_broll_evidence_from_llm_response(tmp_path: Path):
    """LLM may cite real frame_ids that failed quality gates; sanitize must drop them."""
    canned = json.dumps(
        {
            "verdict": "insufficient_evidence",
            "confidence": 0.4,
            "reasoning": "Only early B-roll and waiting-room frames matched keywords.",
            "evidence": [
                {
                    "kind": "frame",
                    "frame_id": "building",
                    "timestamp_sec": 8.0,
                    "notes": "Exterior of medical building; no patient or medical examination visible.",
                },
                {
                    "kind": "frame",
                    "frame_id": "waiting",
                    "timestamp_sec": 25.0,
                    "notes": "Patient seated in examination room waiting area wearing street clothes.",
                },
                {
                    "kind": "frame",
                    "frame_id": "exam",
                    "timestamp_sec": 400.0,
                    "notes": "Doctor performing cervical flexion and extension with goniometer.",
                },
            ],
        }
    )
    client = FakeVisionClient(canned)
    frames = [
        _make_frame(
            "building",
            timestamp_sec=8,
            test_type="none",
            body_region="none",
            visibility="obscured",
            notes="Exterior of medical building; no patient or medical examination visible.",
        ),
        _make_frame(
            "waiting",
            timestamp_sec=25,
            test_type="none",
            body_region="none",
            notes="Patient seated in examination room waiting area wearing street clothes.",
        ),
        _make_frame(
            "exam",
            timestamp_sec=400,
            test_type="rom",
            body_region="neck",
            notes="Doctor performing cervical flexion and extension with goniometer.",
        ),
    ]
    verdict = verify_claim(
        "cervical_rom",
        "Cervical ranges of motion normal with mild sidebending limitation",
        frame_analyses=frames,
        behavior_observations=[],
        verbal_observations=[],
        vision_client=client,
        output_dir=tmp_path,
    )
    assert [e.frame_id for e in verdict.evidence] == ["exam"]
    assert all(e.timestamp_sec != 8.0 for e in verdict.evidence)


def test_sanitize_claim_evidence_drops_establishing_shot_without_llm():
    evidence = [
        Evidence(
            kind="frame",
            frame_id="video1_frame_0017",
            timestamp_sec=8.0,
            notes="Exterior of medical building; no patient visible.",
        )
    ]
    frames = [
        _make_frame(
            "video1_frame_0017",
            timestamp_sec=8,
            test_type="none",
            body_region="none",
            notes="Exterior of medical building; no patient or medical examination visible.",
        )
    ]
    cleaned = sanitize_claim_evidence(
        evidence,
        claim_id="cervical_rom",
        claim_text="Cervical ROM within normal limits",
        frame_analyses=frames,
    )
    assert cleaned == []


def test_verify_claim_evidence_picks_up_raw_response_ref(tmp_path: Path):
    """If a cited frame_id has a `raw_response` pointer on the frame
    analysis dict, Evidence.raw_response_ref must be populated so a
    reviewer can audit the source."""
    canned = json.dumps(
        {
            "verdict": "supported",
            "confidence": 0.9,
            "reasoning": "Observed strength testing at frame f2.",
            "evidence": [
                {
                    "kind": "frame",
                    "frame_id": "f2",
                    "timestamp_sec": 20.0,
                    "notes": (
                        "Doctor performing manual muscle testing with resistance "
                        "on the biceps; patient pushes against examiner's hand (5/5)."
                    ),
                }
            ],
        }
    )
    client = FakeVisionClient(canned)
    frames = [
        _make_frame(
            "f2",
            timestamp_sec=20.0,
            test_type="strength",
            body_region="arm",
            notes=(
                "Doctor performing manual muscle testing with resistance "
                "on the biceps; patient pushes against examiner's hand (5/5)."
            ),
            raw_response="raw/f2.txt",
        )
    ]
    verdict = verify_claim(
        "strength",
        "Motor 5/5 throughout",
        frame_analyses=frames,
        behavior_observations=[],
        verbal_observations=[],
        vision_client=client,
        output_dir=tmp_path,
    )
    assert verdict.verdict == "supported"
    assert verdict.evidence[0].frame_id == "f2"
    assert verdict.evidence[0].raw_response_ref == "raw/f2.txt"


def test_verify_all_claims_writes_json_and_roundtrips(tmp_path: Path):
    """verify_all_claims must persist claim_verdicts.json that round-trips
    back into dataclasses without loss."""
    canned = json.dumps(
        {
            "verdict": "supported",
            "confidence": 0.8,
            "reasoning": "Frame f2 shows strength testing.",
            "evidence": [{"kind": "frame", "frame_id": "f2", "notes": "5/5"}],
        }
    )
    client = FakeVisionClient(canned)
    claims = {
        "strength": "Motor 5/5 throughout",
        "rom": "Cervical ROM full",
    }
    frames = [
        _make_frame("f1", timestamp_sec=5, test_type="conversation"),
        _make_frame("f2", timestamp_sec=20, test_type="strength", body_region="arm"),
        _make_frame("f3", timestamp_sec=30, test_type="rom", body_region="cervical_spine"),
    ]
    verdicts = verify_all_claims(
        claims=claims,
        frame_analyses=frames,
        behavior_observations=[],
        verbal_observations=[],
        vision_client=client,
        output_dir=tmp_path,
        max_workers=2,
    )

    assert {v.claim_id for v in verdicts} == {"strength", "rom"}
    assert verdicts == sorted(verdicts, key=lambda v: v.claim_id)
    assert len(client.calls) == 2

    out_path = tmp_path / "claim_verdicts.json"
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 2

    # Round-trip: rebuild ClaimVerdict from dict and confirm asdict matches.
    for raw in data:
        ev_list = [Evidence(**e) for e in raw.get("evidence", [])]
        rebuilt = ClaimVerdict(
            claim_id=raw["claim_id"],
            claim_text=raw["claim_text"],
            claim_payload=raw.get("claim_payload"),
            verdict=raw["verdict"],
            confidence=raw["confidence"],
            reasoning=raw["reasoning"],
            evidence=ev_list,
            model_id=raw["model_id"],
            provider=raw["provider"],
            prompt_version=raw["prompt_version"],
        )
        # asdict(rebuilt) should be deeply equal to the on-disk payload.
        assert asdict(rebuilt) == raw


def test_verify_claim_invalid_verdict_label_falls_back_to_insufficient(tmp_path: Path):
    """An otherwise-valid JSON with a hallucinated verdict label must be
    rejected and fall through to insufficient_evidence; this is the
    legally safe default."""
    canned = json.dumps({"verdict": "very probably true", "confidence": 0.9, "reasoning": "x"})
    client = FakeVisionClient(canned)
    verdict = verify_claim(
        "cranial_nerves",
        "CN II-XII grossly normal",
        frame_analyses=[],
        behavior_observations=[],
        verbal_observations=[],
        vision_client=client,
        output_dir=tmp_path,
    )
    assert verdict.verdict == "insufficient_evidence"


def test_relevant_observations_matches_text_and_notes_fields():
    obs = [
        {"speaker": "doctor", "text": "Let me check your reflexes", "notes": "calm"},
        {"speaker": "patient", "text": "My shoulder hurts", "notes": "wincing"},
        {"speaker": "doctor", "text": "Look up here", "notes": "cranial nerve check"},
    ]
    matched = relevant_observations("reflexes", "DTRs 2+", obs)
    assert any("reflex" in (m.get("text") or "").lower() for m in matched)

    cn = relevant_observations("cranial_nerves", "CN II-XII grossly normal", obs)
    # Either text match ("look up here" is too vague) or notes match should hit.
    assert any("cranial" in (m.get("notes") or "").lower() for m in cn)


def test_verify_all_claims_empty_returns_empty_and_writes_empty_file(tmp_path: Path):
    client = FakeVisionClient("{}")
    verdicts = verify_all_claims(
        claims={},
        frame_analyses=[],
        behavior_observations=[],
        verbal_observations=[],
        vision_client=client,
        output_dir=tmp_path,
        max_workers=2,
    )
    assert verdicts == []
    assert (tmp_path / "claim_verdicts.json").exists()
    assert json.loads((tmp_path / "claim_verdicts.json").read_text()) == []
    assert client.calls == []


def test_prompt_includes_explicit_not_shown_guidance(monkeypatch, tmp_path: Path):
    """Static prompt audit: verify the prompt body that reaches the
    model contains the legally-distinct 'not_shown vs contradicted'
    guidance. This protects against accidental prompt regression."""
    client = FakeVisionClient(
        json.dumps({"verdict": "not_shown", "confidence": 0.5, "reasoning": "x", "evidence": []})
    )
    verify_claim(
        "reflexes",
        "DTRs 2+",
        frame_analyses=[],
        behavior_observations=[],
        verbal_observations=[],
        vision_client=client,
        output_dir=tmp_path,
    )
    assert client.calls, "verify_claim must call text_analyze"
    prompt = client.calls[0]["prompt"]
    assert "not_shown" in prompt
    assert "contradicted" in prompt
    assert "Silence is NEVER contradiction" in prompt


def test_metadata_claim_ids_excluded_from_verifier_and_report():
    from backend.lambda_functions.cme_analysis_utils import (
        filter_medical_claims,
        filter_medical_claim_verdicts,
        is_metadata_claim_id,
    )
    from backend.lambda_functions.cme_report_builder import (
        _render_deposition_crosswalk_top_findings,
        render_claim_verdicts_table,
    )

    assert is_metadata_claim_id("plaintiff")
    assert is_metadata_claim_id("exam_date")
    assert not is_metadata_claim_id("brace_removal")

    claims = {
        "plaintiff": "Alan Deshefy",
        "exam_date": "February 11, 2026",
        "examiner": "Juan Agudelo, MD",
        "brace_removal": "Both braces removed for examination.",
    }
    filtered = filter_medical_claims(claims)
    assert set(filtered) == {"brace_removal"}

    verdicts = [
        {"claim_id": "exam_date", "claim_text": "February 11, 2026", "verdict": "not_shown"},
        {
            "claim_id": "brace_removal",
            "claim_text": "Both braces removed for examination.",
            "verdict": "partially_supported",
            "test_name": "Brace removal",
            "report_quote": "Both braces removed for examination.",
        },
    ]
    medical = filter_medical_claim_verdicts(verdicts)
    assert len(medical) == 1
    assert medical[0]["claim_id"] == "brace_removal"

    table_html, _ = render_claim_verdicts_table(medical)
    top_findings = _render_deposition_crosswalk_top_findings(medical)
    assert "exam_date" not in table_html
    assert "plaintiff" not in table_html
    assert "February 11, 2026" not in top_findings
    assert len(medical) == 1
