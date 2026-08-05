"""Tests for the transcript-pass port to VisionClient.text_analyze.

`analyze_transcript_segment` (cme_comprehensive_analyzer) and
`analyze_transcript_behavior` (cme_behavior_analyzer) must now route
through the configured VisionClient. These tests monkeypatch a fake
client into each analyzer and assert:
  - text_analyze was called with a prompt containing the transcript
  - cost accumulated into the result object via add_analyze_result_cost
No network calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class _StubResult:
    def __init__(self, text: str, input_tokens: int = 120, output_tokens: int = 60):
        self.text = text
        self.raw_text = text
        self.model_id = "fake-model"
        self.provider = "fake"
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        # Use a known cost so the test asserts a concrete value when usage
        # is present.
        self.usd_cost_estimate = 0.0025
        self.latency_ms = 5
        self.request_id = "stub-req"
        self.extra = {}


class FakeVisionClient:
    """Records text_analyze calls and returns a canned response. Only the
    surface the transcript passes use is implemented."""

    provider = "fake"
    default_model_id = "fake-model"

    def __init__(self, response_text: str):
        self._response_text = response_text
        self.calls = []

    def text_analyze(self, prompt: str, *, model_id=None, max_tokens: int = 1500):
        self.calls.append({"prompt": prompt, "model_id": model_id, "max_tokens": max_tokens})
        return _StubResult(self._response_text)

    def analyze(self, *args, **kwargs):
        raise AssertionError(
            "transcript passes must use text_analyze, never analyze (image-bearing)"
        )


_AUDIO_RESPONSE = json.dumps(
    {
        "segments": [
            {
                "speaker": "doctor",
                "text": "Lift your arm",
                "tone": "rushed",
                "sentiment_score": -0.2,
                "issues": {"rushing_patient": True},
                "problematic_quote": "",
                "notes": "",
            }
        ],
        "helpful_for_plaintiff": [],
    }
)

_VERBAL_RESPONSE = json.dumps(
    {
        "exchanges": [
            {
                "speaker": "doctor",
                "text": "Lift your arm",
                "tone": "rushed",
                "negative_behaviors": {"rushing_patient": True},
                "positive_behaviors": {},
                "is_problematic": True,
                "problem_explanation": "doctor cut patient off",
            }
        ],
        "problematic_quotes": [],
    }
)


def test_analyze_transcript_segment_routes_through_vision_client():
    """analyze_transcript_segment must call vision_client.text_analyze,
    not the raw Anthropic SDK."""
    from backend.lambda_functions.cme_comprehensive_analyzer import (
        CMEComprehensiveAnalyzer,
    )

    fake = FakeVisionClient(_AUDIO_RESPONSE)
    analyzer = CMEComprehensiveAnalyzer(vision_client=fake)

    transcript = "Doctor: lift your arm. Patient: it hurts."
    pre_cost = analyzer.result.total_cost_usd
    segments = analyzer.analyze_transcript_segment(transcript)

    assert fake.calls, "expected at least one text_analyze call"
    # The transcript content must appear in the rendered prompt.
    rendered = fake.calls[0]["prompt"]
    assert "lift your arm" in rendered.lower()
    assert "it hurts" in rendered.lower()

    # Cost was accumulated via add_analyze_result_cost (usage-driven path
    # because our stub carries input_tokens/output_tokens). The exact
    # value depends on the Sonnet pricing constants; assert it strictly
    # increased.
    assert analyzer.result.total_cost_usd > pre_cost
    assert analyzer.result.total_input_tokens >= 120
    assert analyzer.result.total_output_tokens >= 60

    # The segment was parsed back.
    assert segments and segments[0].speaker == "doctor"
    assert segments[0].rushing_patient is True


def test_analyze_transcript_behavior_routes_through_vision_client():
    """analyze_transcript_behavior must call vision_client.text_analyze."""
    from backend.lambda_functions.cme_behavior_analyzer import CMEBehaviorAnalyzer

    fake = FakeVisionClient(_VERBAL_RESPONSE)
    analyzer = CMEBehaviorAnalyzer(vision_client=fake)

    transcript = "Doctor: lift your arm. Patient: it hurts."
    pre_cost = analyzer.result.total_cost_usd
    observations = analyzer.analyze_transcript_behavior(transcript)

    assert fake.calls, "expected at least one text_analyze call"
    rendered = fake.calls[0]["prompt"]
    assert "lift your arm" in rendered.lower()
    assert "it hurts" in rendered.lower()

    assert analyzer.result.total_cost_usd > pre_cost
    assert analyzer.result.total_input_tokens >= 120
    assert analyzer.result.total_output_tokens >= 60

    assert observations and observations[0].speaker == "doctor"
    assert observations[0].rushing_patient is True


def test_transcript_passes_never_call_analyze_method():
    """Belt-and-suspenders: the transcript passes are text-only and must
    never invoke .analyze() (which carries an image part)."""
    from backend.lambda_functions.cme_behavior_analyzer import CMEBehaviorAnalyzer
    from backend.lambda_functions.cme_comprehensive_analyzer import (
        CMEComprehensiveAnalyzer,
    )

    fake = FakeVisionClient(_VERBAL_RESPONSE)

    beh = CMEBehaviorAnalyzer(vision_client=fake)
    beh.analyze_transcript_behavior("Doctor: hi. Patient: hi.")

    fake2 = FakeVisionClient(_AUDIO_RESPONSE)
    comp = CMEComprehensiveAnalyzer(vision_client=fake2)
    comp.analyze_transcript_segment("Doctor: hi. Patient: hi.")

    # The FakeVisionClient.analyze raises AssertionError if hit; both
    # calls above completed without raising, so analyze was never called.
    assert fake.calls
    assert fake2.calls
