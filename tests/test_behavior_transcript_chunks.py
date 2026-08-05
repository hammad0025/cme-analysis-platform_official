"""Tests for the chunking + timestamping behavior introduced by A3.

Two paths are exercised:

1. Structured `Transcript` -> chunks are built from real segment
   boundaries and the resulting `VerbalBehaviorObservation`s carry
   the real `start_sec` / `end_sec` from the underlying words.
2. Legacy string transcript -> chunks are sized by word count and the
   resulting observations carry `start_sec=None` / `end_sec=None`
   (we explicitly do NOT fake the timestamps anymore).

The VisionClient.text_analyze call is monkeypatched with a canned JSON
response so no provider SDK is exercised.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.lambda_functions.cme_behavior_analyzer import (  # noqa: E402
    CMEBehaviorAnalyzer,
    VerbalBehaviorObservation,
)
from backend.lambda_functions.cme_transcription import (  # noqa: E402
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)


class _StubAnalyzeResult:
    """Mimics enough of `vision_client.AnalyzeResult` to satisfy the
    behavior analyzer's text_analyze consumer (cost + raw text)."""

    def __init__(self, text: str):
        self.text = text
        self.raw_text = text
        self.input_tokens = 10
        self.output_tokens = 5
        self.usd_cost_estimate = 0.0001
        self.provider = "stub"
        self.model_id = "stub-model"


class _StubVisionClient:
    """Records the last prompt seen and returns a fixed JSON payload."""

    provider = "stub"
    default_model_id = "stub-model"

    def __init__(self, canned_json: str):
        self._canned = canned_json
        self.calls: list = []

    def analyze(self, *a, **k):  # pragma: no cover - not used here
        raise NotImplementedError

    def text_analyze(self, prompt: str, *, model_id=None, max_tokens=1500):
        self.calls.append(prompt)
        return _StubAnalyzeResult(self._canned)


def _build_synthetic_transcript() -> Transcript:
    """3 segments / ~20 words / 0-25 seconds total.

    Segment timings chosen so that the 30-second-span and 400-word
    chunk-flush thresholds in `_build_transcript_chunks` are NOT
    triggered; all three segments should land in a single chunk with
    start_sec=0.0, end_sec=25.0 derived from the first/last words.
    """
    seg1_words = [
        TranscriptWord(text=w, start_sec=i * 0.5, end_sec=i * 0.5 + 0.4, confidence=0.9)
        for i, w in enumerate(
            ["Hello", "doctor.", "How", "are", "you", "today?", "I", "am"]
        )
    ]
    seg2_words = [
        TranscriptWord(text=w, start_sec=8.0 + i * 0.5, end_sec=8.0 + i * 0.5 + 0.4, confidence=0.85)
        for i, w in enumerate(["Doing", "fine.", "Tell", "me", "about", "the", "pain."])
    ]
    seg3_words = [
        TranscriptWord(text=w, start_sec=20.0 + i * 0.5, end_sec=20.0 + i * 0.5 + 0.4, confidence=0.8)
        for i, w in enumerate(["It", "hurts", "in", "my", "neck."])
    ]
    segments = [
        TranscriptSegment(
            start_sec=seg1_words[0].start_sec,
            end_sec=seg1_words[-1].end_sec,
            text="Hello doctor. How are you today? I am",
            words=seg1_words,
        ),
        TranscriptSegment(
            start_sec=seg2_words[0].start_sec,
            end_sec=seg2_words[-1].end_sec,
            text="Doing fine. Tell me about the pain.",
            words=seg2_words,
        ),
        TranscriptSegment(
            start_sec=seg3_words[0].start_sec,
            end_sec=seg3_words[-1].end_sec,
            text="It hurts in my neck.",
            words=seg3_words,
        ),
    ]
    return Transcript(
        language="en",
        duration_sec=25.0,
        backend="faster-whisper",
        model_id="large-v3",
        segments=segments,
        word_count=sum(len(s.words) for s in segments),
        mean_word_confidence=0.85,
    )


_CANNED_VERBAL_JSON = json.dumps(
    {
        "exchanges": [
            {
                "speaker": "doctor",
                "text": "How are you today?",
                "tone": "neutral",
                "negative_behaviors": {},
                "positive_behaviors": {"empathetic": True},
                "is_problematic": False,
            },
            {
                "speaker": "patient",
                "text": "It hurts in my neck.",
                "tone": "distressed",
                "negative_behaviors": {},
                "positive_behaviors": {},
                "is_problematic": False,
            },
        ],
        "problematic_quotes": [],
    }
)


def _make_analyzer(canned_json: str = _CANNED_VERBAL_JSON) -> CMEBehaviorAnalyzer:
    stub = _StubVisionClient(canned_json)
    analyzer = CMEBehaviorAnalyzer(vision_client=stub)
    analyzer._stub = stub  # for assertions
    return analyzer


def test_structured_transcript_chunks_use_real_segment_boundaries():
    """With a real `Transcript`, the chunker should emit a single chunk
    spanning the whole transcript (under the 400-word / 30-sec caps),
    and the resulting observations should carry segment-boundary times
    -- NOT the legacy `i * 0.5` synthetic timestamps."""
    transcript = _build_synthetic_transcript()
    analyzer = _make_analyzer()

    chunks = analyzer._build_transcript_chunks(transcript, None)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["start_sec"] == pytest.approx(transcript.segments[0].words[0].start_sec)
    assert chunk["end_sec"] == pytest.approx(transcript.segments[-1].words[-1].end_sec)

    obs = analyzer.analyze_transcript_behavior(transcript_obj=transcript)
    assert obs, "expected at least one VerbalBehaviorObservation"
    for o in obs:
        assert isinstance(o, VerbalBehaviorObservation)
        assert o.start_sec == pytest.approx(chunk["start_sec"])
        assert o.end_sec == pytest.approx(chunk["end_sec"])
        # Sanity: the old synthetic `i * 0.5` per-chunk pattern would put
        # this at 0.0 + j, which would NOT equal the real first-word time
        # except by coincidence when the first segment also begins at 0.
        # The relevant invariant we care about is that timestamps come
        # from the underlying words, which is checked above.


def test_legacy_string_transcript_has_null_timestamps():
    """When only a plain string transcript is supplied, observations
    must carry `start_sec=None` / `end_sec=None` so downstream consumers
    can distinguish 'no timing info available' from a real `0.0`."""
    analyzer = _make_analyzer()
    string_transcript = "Hello doctor. " * 50  # ~100 words; one chunk
    obs = analyzer.analyze_transcript_behavior(string_transcript)
    assert obs, "expected at least one VerbalBehaviorObservation"
    for o in obs:
        assert o.start_sec is None
        assert o.end_sec is None


def test_legacy_string_transcript_does_not_raise_attribute_errors():
    """Round-trip: asdict() on observations with `start_sec=None` should
    not raise (regression guard for the Optional[float] migration)."""
    from dataclasses import asdict

    analyzer = _make_analyzer()
    obs = analyzer.analyze_transcript_behavior("Hello there how are you")
    for o in obs:
        d = asdict(o)
        assert d["start_sec"] is None
        assert d["end_sec"] is None


def test_long_transcript_flushes_on_thirty_second_boundary():
    """A transcript spanning >30 seconds in one segment should NOT
    coalesce into a single chunk; the chunker should flush at the span
    cap so we keep prompt-sized requests."""
    words = [
        TranscriptWord(text=f"w{i}", start_sec=float(i), end_sec=float(i) + 0.5, confidence=0.9)
        for i in range(60)
    ]
    seg = TranscriptSegment(
        start_sec=0.0,
        end_sec=words[-1].end_sec,
        text=" ".join(w.text for w in words),
        words=words,
    )
    # Two segments each spanning ~60 seconds.
    seg2_words = [
        TranscriptWord(text=f"x{i}", start_sec=float(70 + i), end_sec=float(70 + i) + 0.5, confidence=0.9)
        for i in range(20)
    ]
    seg2 = TranscriptSegment(
        start_sec=seg2_words[0].start_sec,
        end_sec=seg2_words[-1].end_sec,
        text=" ".join(w.text for w in seg2_words),
        words=seg2_words,
    )
    transcript = Transcript(
        language="en",
        duration_sec=100.0,
        backend="faster-whisper",
        model_id="large-v3",
        segments=[seg, seg2],
        word_count=80,
        mean_word_confidence=0.9,
    )
    analyzer = _make_analyzer()
    chunks = analyzer._build_transcript_chunks(transcript, None)
    # Both segments individually exceed the 30s span cap, so each
    # segment lands in its own chunk -> 2 chunks total.
    assert len(chunks) >= 2
