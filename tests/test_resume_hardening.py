"""Tests for the failure-stub-aware resume in the behavior pass and the
per-claim checkpoint in the claim verifier.

Both tests run fully offline: no API calls; the verifier-side test uses
a recording FakeVisionClient and the behavior-side test exercises the
pure-Python helpers in cme_behavior_analyzer (no model is invoked)."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.lambda_functions.cme_behavior_analyzer import (  # noqa: E402
    _observation_from_checkpoint,
    _observation_has_model_output,
)
from backend.lambda_functions.cme_claim_verifier import (  # noqa: E402
    ClaimVerdict,
    _append_claim_checkpoint,
    _claim_checkpoint_has_real_verdict,
    _load_claim_checkpoint,
    verify_all_claims,
)


class _StubResult:
    def __init__(self, text: str):
        self.text = text
        self.raw_text = text
        self.model_id = "fake-model"
        self.provider = "fake"
        self.input_tokens = 80
        self.output_tokens = 40
        self.usd_cost_estimate = 0.001
        self.latency_ms = 5
        self.request_id = "stub-req"
        self.extra = {}


class FakeVisionClient:
    """Records prompts and returns a canned text_analyze response per claim."""

    provider = "fake"
    default_model_id = "fake-model"

    def __init__(self, responses_by_claim_id: dict):
        self._responses = responses_by_claim_id
        self.calls = []

    def text_analyze(self, prompt: str, *, model_id=None, max_tokens: int = 1500):
        # Pull claim_id out of the rendered prompt for the test harness.
        claim_id = ""
        for line in prompt.splitlines():
            if line.startswith("claim_id:"):
                claim_id = line.split(":", 1)[1].strip()
                break
        self.calls.append({"claim_id": claim_id, "prompt": prompt})
        body = self._responses.get(claim_id) or self._responses.get("default") or "{}"
        return _StubResult(body)

    def analyze(self, *args, **kwargs):
        raise AssertionError("verifier must not call analyze()")


# ----------------------------------------------------------------------
# B5: behavior pass - failure-stub-aware resume
# ----------------------------------------------------------------------


def test_behavior_failure_stub_detected_for_default_observation():
    """A behavior checkpoint stub with empty raw_response, empty notes,
    and zero confidence must be flagged as a failure stub (needs re-run)
    by the comprehensive-pattern helper."""
    failure_stub = {
        "frame_id": "video1_frame_0001",
        "timestamp_sec": 0.0,
        "raw_response": "",
        "notes": "",
        "confidence": 0.0,
    }
    assert _observation_has_model_output(failure_stub) is False


def test_behavior_real_observation_passes_failure_stub_check():
    """Any one of raw_response / notes / confidence > 0 is sufficient
    proof that the model actually produced output for this frame."""
    real_obs_via_raw = {
        "frame_id": "video1_frame_0010",
        "raw_response": "raw/video1_frame_0010.txt",
        "notes": "",
        "confidence": 0.0,
    }
    real_obs_via_notes = {
        "frame_id": "video1_frame_0011",
        "raw_response": "",
        "notes": "doctor looking at notes",
        "confidence": 0.0,
    }
    real_obs_via_confidence = {
        "frame_id": "video1_frame_0012",
        "raw_response": "",
        "notes": "",
        "confidence": 0.8,
    }
    assert _observation_has_model_output(real_obs_via_raw) is True
    assert _observation_has_model_output(real_obs_via_notes) is True
    assert _observation_has_model_output(real_obs_via_confidence) is True


def test_behavior_resume_appends_failure_stubs_and_skips_real_observations(tmp_path):
    """Simulate the behavior-pass resume loop: with `resume=True`, the
    failure-stub frame must end up in pending_tasks; the real one must
    rehydrate from the checkpoint and be skipped.

    This mirrors the loop in analyze_cme_behavior at the per-frame
    branching site -- exercising the same helpers it uses."""
    # Build two synthetic frame paths under tmp_path so the path-based
    # parts of _observation_from_checkpoint resolve cleanly.
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    failure_frame = frames_dir / "video1_frame_0001.jpg"
    real_frame = frames_dir / "video1_frame_0002.jpg"
    failure_frame.write_bytes(b"x")
    real_frame.write_bytes(b"x")

    loaded = {
        failure_frame.stem: {
            "frame_id": failure_frame.stem,
            "timestamp_sec": 0.0,
            "raw_response": "",
            "notes": "",
            "confidence": 0.0,
        },
        real_frame.stem: {
            "frame_id": real_frame.stem,
            "timestamp_sec": 5.0,
            "raw_response": "raw/video1_frame_0002.txt",
            "notes": "doctor leaning in, engaged",
            "confidence": 0.82,
        },
    }

    pending = []
    rehydrated = []
    resume = True
    for frame in [failure_frame, real_frame]:
        parts = frame.stem.split("_")
        timestamp = (int(parts[-1]) - 1) * 5.0
        if frame.stem in loaded:
            stub = loaded[frame.stem]
            if resume and not _observation_has_model_output(stub):
                pending.append(frame)
            else:
                rehydrated.append(
                    _observation_from_checkpoint(stub, frame, timestamp)
                )

    assert pending == [failure_frame]
    assert len(rehydrated) == 1
    assert rehydrated[0].frame_id == real_frame.stem
    assert rehydrated[0].confidence == pytest.approx(0.82)


# ----------------------------------------------------------------------
# B5: claim verifier per-claim resume
# ----------------------------------------------------------------------


def test_claim_checkpoint_treats_insufficient_evidence_as_failure_stub():
    ok_row = {"claim_id": "reflexes", "verdict": "not_shown"}
    failure_row = {"claim_id": "rom", "verdict": "insufficient_evidence"}
    bad_row = {"claim_id": "x", "verdict": ""}

    assert _claim_checkpoint_has_real_verdict(ok_row) is True
    assert _claim_checkpoint_has_real_verdict(failure_row) is False
    assert _claim_checkpoint_has_real_verdict(bad_row) is False


def test_load_claim_checkpoint_keeps_latest_per_claim_id(tmp_path):
    path = tmp_path / "claim_verdicts_checkpoint.jsonl"
    payloads = [
        {"claim_id": "a", "verdict_record": {"claim_id": "a", "verdict": "insufficient_evidence"}},
        {"claim_id": "a", "verdict_record": {"claim_id": "a", "verdict": "not_shown"}},
        {"claim_id": "b", "verdict_record": {"claim_id": "b", "verdict": "supported"}},
    ]
    with open(path, "w", encoding="utf-8") as f:
        for p in payloads:
            f.write(json.dumps(p) + "\n")

    loaded = _load_claim_checkpoint(path)
    assert set(loaded.keys()) == {"a", "b"}
    # Latest row wins.
    assert loaded["a"]["verdict"] == "not_shown"
    assert loaded["b"]["verdict"] == "supported"


def test_verify_all_claims_resume_retries_insufficient_and_skips_real_verdicts(tmp_path):
    """Two prior claim verdicts in the per-claim checkpoint: one
    `not_shown` (success), one `insufficient_evidence` (failure stub).
    With resume=True, the verifier must:
      - reuse the `not_shown` row without calling text_analyze
      - retry the `insufficient_evidence` row by calling text_analyze
    """
    checkpoint = tmp_path / "claim_verdicts_checkpoint.jsonl"
    prior_rows = [
        {
            "claim_id": "reflexes",
            "verdict_record": asdict(
                ClaimVerdict(
                    claim_id="reflexes",
                    claim_text="DTRs 2+",
                    verdict="not_shown",
                    confidence=0.5,
                    reasoning="No reflex frames matched.",
                    evidence=[],
                    model_id="fake-model",
                    provider="fake",
                )
            ),
        },
        {
            "claim_id": "rom",
            "verdict_record": asdict(
                ClaimVerdict(
                    claim_id="rom",
                    claim_text="Cervical ROM full",
                    verdict="insufficient_evidence",
                    confidence=0.0,
                    reasoning="model output unparseable",
                    evidence=[],
                    model_id="fake-model",
                    provider="fake",
                )
            ),
        },
    ]
    with open(checkpoint, "w", encoding="utf-8") as f:
        for p in prior_rows:
            f.write(json.dumps(p, default=str) + "\n")

    # On retry, the model produces a real verdict for rom.
    rom_response = json.dumps(
        {
            "verdict": "supported",
            "confidence": 0.85,
            "reasoning": "Frame f2 shows cervical ROM testing.",
            "evidence": [{"kind": "frame", "frame_id": "f2", "notes": "rom"}],
        }
    )
    client = FakeVisionClient({"rom": rom_response})

    claims = {"reflexes": "DTRs 2+", "rom": "Cervical ROM full"}
    verdicts = verify_all_claims(
        claims=claims,
        frame_analyses=[
            {
                "frame_id": "f2",
                "timestamp_sec": 30,
                "test_type": "rom",
                "body_region": "cervical_spine",
                "notes": "",
                "raw_response": "",
                "visibility": "full",
                "confidence": 0.9,
            }
        ],
        behavior_observations=[],
        verbal_observations=[],
        vision_client=client,
        output_dir=tmp_path,
        max_workers=1,
        resume=True,
    )

    by_id = {v.claim_id: v for v in verdicts}
    assert by_id["reflexes"].verdict == "not_shown"
    assert by_id["rom"].verdict == "supported"

    # Only the failure stub triggered a model call.
    called_ids = {c["claim_id"] for c in client.calls}
    assert called_ids == {"rom"}


def test_verify_all_claims_default_resume_false_unlinks_checkpoint(tmp_path):
    """Default behavior (`resume=False`) must truncate any pre-existing
    per-claim checkpoint so a fresh run starts clean. This preserves the
    default-mode contract."""
    checkpoint = tmp_path / "claim_verdicts_checkpoint.jsonl"
    checkpoint.write_text(
        json.dumps({"claim_id": "reflexes", "verdict_record": {"verdict": "not_shown"}}) + "\n",
        encoding="utf-8",
    )

    client = FakeVisionClient(
        {
            "default": json.dumps(
                {
                    "verdict": "not_shown",
                    "confidence": 0.5,
                    "reasoning": "x",
                    "evidence": [],
                }
            )
        }
    )
    verdicts = verify_all_claims(
        claims={"reflexes": "DTRs 2+"},
        frame_analyses=[],
        behavior_observations=[],
        verbal_observations=[],
        vision_client=client,
        output_dir=tmp_path,
        max_workers=1,
        resume=False,
    )
    assert len(verdicts) == 1
    assert len(client.calls) == 1
    # The checkpoint is rebuilt with exactly one fresh row.
    assert checkpoint.exists()
    reloaded = _load_claim_checkpoint(checkpoint)
    assert set(reloaded.keys()) == {"reflexes"}
