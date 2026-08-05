"""Offline tests for backend.lambda_functions.cme_transcription.

No real ffmpeg invocation and no real ASR backend is exercised here.
The faster-whisper and openai-whisper-api paths are stubbed via
`monkeypatch` so the tests run on any machine, including CI runners
without GPU, without faster-whisper installed, and without an OpenAI
API key. Audio extraction is also monkeypatched so we never shell out
to ffmpeg.
"""

from __future__ import annotations

import importlib.util as _ilu
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.lambda_functions import cme_transcription  # noqa: E402
from backend.lambda_functions.cme_transcription import (  # noqa: E402
    TRANSCRIPTION_PROMPT_VERSION,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
    detect_backend,
    transcribe,
)


def _patch_find_spec(monkeypatch, *, faster_whisper: bool, openai: bool):
    """Helper: monkeypatch importlib.util.find_spec to control which
    backends look 'installed' from the module's perspective."""
    real_find_spec = _ilu.find_spec

    def fake_find_spec(name, *args, **kwargs):
        if name == "faster_whisper":
            return object() if faster_whisper else None
        if name == "openai":
            return object() if openai else None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(cme_transcription.importlib.util, "find_spec", fake_find_spec)


def test_detect_backend_auto_returns_none_when_neither_available(monkeypatch):
    """With neither faster-whisper installed nor OPENAI_API_KEY set, auto
    selection returns None so the caller can skip transcription."""
    _patch_find_spec(monkeypatch, faster_whisper=False, openai=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert detect_backend("auto") is None


def test_detect_backend_auto_prefers_faster_whisper_when_both_available(monkeypatch):
    """faster-whisper wins the auto contest because it has no per-call cost."""
    _patch_find_spec(monkeypatch, faster_whisper=True, openai=True)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert detect_backend("auto") == "faster-whisper"


def test_detect_backend_openai_explicit_returns_none_without_key(monkeypatch):
    """Explicitly asking for openai-whisper-api with no key returns None,
    not an exception. The CLI translates None into a clear skip."""
    _patch_find_spec(monkeypatch, faster_whisper=False, openai=True)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert detect_backend("openai-whisper-api") is None


def test_detect_backend_none_disables_unconditionally(monkeypatch):
    """`prefer='none'` always returns None even when backends are available."""
    _patch_find_spec(monkeypatch, faster_whisper=True, openai=True)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert detect_backend("none") is None


def test_transcribe_returns_none_when_no_backend_available(tmp_path, monkeypatch, capsys):
    """transcribe(...) returns None and prints the documented skip
    message when no backend is available. The caller is expected to
    proceed with the visual-only pipeline (a3-default flow)."""
    _patch_find_spec(monkeypatch, faster_whisper=False, openai=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # ffmpeg should NOT be invoked on the skip path; stub it to fail loudly
    # so we catch any accidental invocation.
    def _bomb(*a, **k):
        raise AssertionError("ffmpeg should not be invoked when backend is unavailable")

    monkeypatch.setattr(cme_transcription, "extract_audio", _bomb)

    out_dir = tmp_path / "audio"
    video_path = tmp_path / "fake.mp4"
    video_path.write_bytes(b"not really a video")

    result = transcribe(video_path, out_dir)
    assert result is None
    captured = capsys.readouterr()
    assert "no ASR backend available" in captured.out


def _fake_transcript() -> Transcript:
    """Build a small synthetic Transcript matching what _transcribe_*
    would produce, for the happy-path tests below."""
    segs = [
        TranscriptSegment(
            start_sec=0.0,
            end_sec=2.5,
            text="Hello world.",
            words=[
                TranscriptWord(text="Hello", start_sec=0.0, end_sec=1.0, confidence=0.9),
                TranscriptWord(text="world.", start_sec=1.1, end_sec=2.5, confidence=0.8),
            ],
        ),
        TranscriptSegment(
            start_sec=2.6,
            end_sec=5.0,
            text="Goodbye.",
            words=[
                TranscriptWord(text="Goodbye.", start_sec=2.6, end_sec=5.0, confidence=0.7),
            ],
        ),
    ]
    return Transcript(
        language="en",
        duration_sec=5.0,
        backend="faster-whisper",
        model_id="large-v3",
        segments=segs,
        word_count=3,
        mean_word_confidence=0.8,
    )


def _wire_happy_path(monkeypatch, tmp_path, *, backend: str):
    """Common scaffolding for happy-path tests.

    - Patch find_spec/env so detect_backend returns the requested backend.
    - Stub extract_audio to write a placeholder WAV (so the artifact write
      path is exercised without actually shelling out to ffmpeg).
    - Stub the backend implementation function to return a fixed
      Transcript + raw_payload pair.
    """
    if backend == "faster-whisper":
        _patch_find_spec(monkeypatch, faster_whisper=True, openai=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    else:
        _patch_find_spec(monkeypatch, faster_whisper=False, openai=True)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    out_dir = tmp_path / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    fake_wav = out_dir / "audio.wav"

    def fake_extract_audio(video_path: Path, out_dir_arg: Path) -> Path:
        out_dir_arg = Path(out_dir_arg)
        out_dir_arg.mkdir(parents=True, exist_ok=True)
        wav = out_dir_arg / "audio.wav"
        wav.write_bytes(b"RIFFfakeWAVE")
        return wav

    monkeypatch.setattr(cme_transcription, "extract_audio", fake_extract_audio)

    transcript = _fake_transcript()
    if backend == "openai-whisper-api":
        transcript.backend = "openai-whisper-api"
        transcript.model_id = "whisper-1"

    raw_payload = {"stub": True, "backend": backend}

    if backend == "faster-whisper":
        monkeypatch.setattr(
            cme_transcription,
            "_transcribe_faster_whisper",
            lambda wav_path, model: (transcript, raw_payload),
        )
    else:
        monkeypatch.setattr(
            cme_transcription,
            "_transcribe_openai",
            lambda wav_path, model: (transcript, raw_payload),
        )

    return out_dir, transcript, raw_payload, fake_wav


def test_transcribe_happy_path_faster_whisper(tmp_path, monkeypatch):
    """faster-whisper happy path: WAV created, all four artifacts written,
    Transcript round-trips through transcript.json correctly."""
    out_dir, transcript, raw_payload, _ = _wire_happy_path(
        monkeypatch, tmp_path, backend="faster-whisper"
    )
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")

    result = transcribe(video_path, out_dir)
    assert result is not None
    assert result.backend == "faster-whisper"
    assert result.model_id == "large-v3"
    assert result.word_count == 3
    assert abs(result.mean_word_confidence - 0.8) < 1e-9

    # WAV created by stubbed ffmpeg replacement
    assert (out_dir / "audio.wav").exists()

    # Raw backend payload written verbatim
    raw_text = (out_dir / "transcript.raw.json").read_text(encoding="utf-8")
    assert json.loads(raw_text) == raw_payload

    # Normalized Transcript dump round-trips
    normalized = json.loads(
        (out_dir / "transcript.json").read_text(encoding="utf-8")
    )
    assert normalized["backend"] == "faster-whisper"
    assert normalized["word_count"] == 3
    assert normalized["raw_path"] == "transcript.raw.json"
    assert len(normalized["segments"]) == 2

    # Plain-text artifact concatenates segment text by newlines
    txt = (out_dir / "transcript.txt").read_text(encoding="utf-8").strip()
    assert "Hello world." in txt
    assert "Goodbye." in txt


def test_transcribe_happy_path_openai(tmp_path, monkeypatch):
    """OpenAI Whisper API happy path mirrors faster-whisper artifacts."""
    out_dir, transcript, raw_payload, _ = _wire_happy_path(
        monkeypatch, tmp_path, backend="openai-whisper-api"
    )
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")

    result = transcribe(video_path, out_dir)
    assert result is not None
    assert result.backend == "openai-whisper-api"
    assert result.model_id == "whisper-1"

    assert (out_dir / "audio.wav").exists()
    assert (out_dir / "transcript.raw.json").exists()
    assert (out_dir / "transcript.json").exists()
    assert (out_dir / "transcript.txt").exists()

    normalized = json.loads(
        (out_dir / "transcript.json").read_text(encoding="utf-8")
    )
    assert normalized["backend"] == "openai-whisper-api"


def test_transcription_prompt_version_is_stamped():
    """Tests in PART D rely on this constant for MANIFEST stamping."""
    assert TRANSCRIPTION_PROMPT_VERSION == "1.0.0"
