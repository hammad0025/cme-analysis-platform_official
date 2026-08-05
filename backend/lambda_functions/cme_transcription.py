"""
CME audio transcription (roadmap step A3, first half).

Contract
--------
Input: a path to a video file (mp4 / mov / mkv / ...) and an output
directory. Output: a `Transcript` dataclass with word-level timestamps,
mean per-word confidence, language, the backend that produced it, the
model id, and the per-segment text. The same data is also persisted to:

- ``<out_dir>/audio.wav``         -- mono 16-bit PCM 16 kHz audio (ASR-standard).
- ``<out_dir>/transcript.raw.json`` -- raw backend output as-is.
- ``<out_dir>/transcript.json``   -- normalized `Transcript` dataclass (asdict).
- ``<out_dir>/transcript.txt``    -- plain text, segments joined by newlines.

The plain `.txt` is written so the existing ``--transcript <file>`` code
path in `analyze_cme_full.py` keeps working transparently when callers
prefer the string interface; the JSON dump is for downstream consumers
that want word timing.

Hardware expectations and degradation
-------------------------------------
ASR backends are OPTIONAL. The module degrades gracefully when neither
is available:

- faster-whisper is a large CPU/GPU dependency (model weights ~3 GB for
  large-v3, cached under ``~/.cache/huggingface``). On Apple Silicon /
  CUDA / CPU all work; we let faster-whisper pick via ``device='auto'``
  and ``compute_type='auto'``.
- OpenAI Whisper API needs ``OPENAI_API_KEY`` plus the `openai` package
  (already in `backend/requirements.txt`).

When neither is importable / configured, `transcribe(...)` logs a clear
message and returns ``None``. The caller is expected to proceed with the
visual-only pipeline, which is exactly the prior behavior before this
module existed.

Diarization (out of scope)
--------------------------
Speaker diarization is explicitly NOT implemented in this iteration. The
dataclasses reserve an optional ``speaker`` field on `TranscriptWord` and
`TranscriptSegment` so a future iteration can wire in `pyannote.audio`
3.x or AWS Transcribe Medical without churning the schema. Until then,
``speaker`` is always ``None``.

SDK leak note
-------------
The Anthropic / OpenAI / Gemini text-generation SDK access in this
codebase is funneled through `vision_client.py`. This module is the ONE
documented exception: it imports the raw `openai` SDK to call
``audio.transcriptions.create``, which is a different endpoint shape
than chat and therefore does not belong on the `VisionClient` interface.
faster-whisper is also imported lazily here for the same reason -- ASR
is a different interaction surface than vision/text generation.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List, Optional


TRANSCRIPTION_PROMPT_VERSION = "1.0.0"

_LOGGER = logging.getLogger(__name__)

_BACKEND_PRIORITY = ("faster-whisper", "openai-whisper-api")


@dataclass
class TranscriptWord:
    """One word with start/end timestamps and (when available) confidence.

    `speaker` is reserved for a future diarization pass and is always
    `None` in this iteration.
    """

    text: str
    start_sec: float
    end_sec: float
    confidence: float = 0.0
    speaker: Optional[str] = None


@dataclass
class TranscriptSegment:
    """A contiguous ASR segment. Words may be empty for backends that do
    not return word-level granularity; segment-level text/start/end are
    always populated."""

    start_sec: float
    end_sec: float
    text: str
    words: List[TranscriptWord] = field(default_factory=list)
    speaker: Optional[str] = None


@dataclass
class Transcript:
    """Unified transcript dataclass shared across backends.

    `mean_word_confidence` is 0.0 when the backend does not return word
    probabilities (e.g., OpenAI Whisper API response shapes that omit
    per-word logprobs). Callers should not interpret a 0.0 confidence as
    "the words are unreliable" -- inspect `backend` to disambiguate.
    """

    language: str
    duration_sec: float
    backend: str
    model_id: str
    segments: List[TranscriptSegment] = field(default_factory=list)
    word_count: int = 0
    mean_word_confidence: float = 0.0
    raw_path: Optional[str] = None


def transcript_from_dict(payload: dict) -> Transcript:
    """Rehydrate a `Transcript` from its asdict() JSON form (e.g. a
    previously written transcript.json, or a converted AWS Transcribe
    output). Inverse of ``json.loads`` + ``asdict``."""
    segments: List[TranscriptSegment] = []
    for seg in payload.get("segments") or []:
        words = [
            TranscriptWord(
                text=str(w.get("text") or ""),
                start_sec=float(w.get("start_sec") or 0.0),
                end_sec=float(w.get("end_sec") or 0.0),
                confidence=float(w.get("confidence") or 0.0),
                speaker=w.get("speaker"),
            )
            for w in (seg.get("words") or [])
        ]
        segments.append(
            TranscriptSegment(
                start_sec=float(seg.get("start_sec") or 0.0),
                end_sec=float(seg.get("end_sec") or 0.0),
                text=str(seg.get("text") or ""),
                words=words,
                speaker=seg.get("speaker"),
            )
        )
    return Transcript(
        language=str(payload.get("language") or ""),
        duration_sec=float(payload.get("duration_sec") or 0.0),
        backend=str(payload.get("backend") or ""),
        model_id=str(payload.get("model_id") or ""),
        segments=segments,
        word_count=int(payload.get("word_count") or 0),
        mean_word_confidence=float(payload.get("mean_word_confidence") or 0.0),
        raw_path=payload.get("raw_path"),
    )


def detect_backend(prefer: str = "auto") -> Optional[str]:
    """Return the name of the first available ASR backend, or ``None``.

    Backend availability:

    - ``faster-whisper``: ``importlib.util.find_spec('faster_whisper')`` is not None.
    - ``openai-whisper-api``: ``OPENAI_API_KEY`` env var is set AND
      ``importlib.util.find_spec('openai')`` is not None.

    `prefer` semantics:

    - ``'auto'`` (default): iterate `_BACKEND_PRIORITY` and return the
      first available backend. faster-whisper wins when both are present
      since it does not incur per-call API cost.
    - explicit (`'faster-whisper'` / `'openai-whisper-api'`): only that
      backend is considered. Returns ``None`` (no error) if the named
      backend is not available; callers translate ``None`` into a clear
      skip message.
    - ``'none'``: returns ``None`` unconditionally. Lets the CLI flag
      surface ``--asr-backend none`` as an explicit opt-out.
    """
    p = (prefer or "auto").strip().lower()
    if p == "none":
        return None

    def _faster_whisper_available() -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def _openai_whisper_api_available() -> bool:
        if not os.environ.get("OPENAI_API_KEY"):
            return False
        return importlib.util.find_spec("openai") is not None

    if p == "auto":
        for candidate in _BACKEND_PRIORITY:
            if candidate == "faster-whisper" and _faster_whisper_available():
                return "faster-whisper"
            if candidate == "openai-whisper-api" and _openai_whisper_api_available():
                return "openai-whisper-api"
        return None

    if p == "faster-whisper":
        return "faster-whisper" if _faster_whisper_available() else None
    if p == "openai-whisper-api":
        return "openai-whisper-api" if _openai_whisper_api_available() else None

    return None


def extract_audio(video_path: Path, out_dir: Path) -> Path:
    """Extract mono 16-bit PCM 16 kHz WAV from ``video_path``.

    Mono / 16-bit / 16 kHz is the standard input shape for both Whisper
    backends and matches the ffmpeg invocation conventions used elsewhere
    in this repo. Output lands at ``out_dir / 'audio.wav'``.

    Returns the WAV path. Raises ``RuntimeError`` when ffmpeg fails -- the
    caller should treat that as a non-ASR failure (something is wrong with
    the input video or the ffmpeg install), not a "no backend available"
    skip path.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / "audio.wav"

    proc = subprocess.run(
        [
            "ffmpeg",
            "-i",
            str(video_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-vn",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
            "-y",
            "-loglevel",
            "error",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not wav_path.exists():
        raise RuntimeError(
            "ffmpeg audio extraction failed for "
            f"{video_path!s}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return wav_path


def _word_count_and_mean_conf(segments: List[TranscriptSegment]) -> tuple:
    total_words = 0
    conf_sum = 0.0
    conf_n = 0
    for seg in segments:
        for w in seg.words:
            total_words += 1
            if w.confidence > 0.0:
                conf_sum += w.confidence
                conf_n += 1
    mean_conf = (conf_sum / conf_n) if conf_n else 0.0
    return total_words, mean_conf


def _write_artifacts(
    out_dir: Path,
    transcript: Transcript,
    raw_payload: Any,
) -> None:
    """Persist `transcript.raw.json`, `transcript.json`, `transcript.txt`."""
    raw_path = out_dir / "transcript.raw.json"
    raw_path.write_text(
        json.dumps(raw_payload, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    transcript.raw_path = "transcript.raw.json"

    normalized_path = out_dir / "transcript.json"
    normalized_path.write_text(
        json.dumps(asdict(transcript), indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )

    txt_path = out_dir / "transcript.txt"
    txt_path.write_text(
        "\n".join((seg.text or "").strip() for seg in transcript.segments).strip()
        + "\n",
        encoding="utf-8",
    )


def _transcribe_faster_whisper(
    wav_path: Path,
    model: Optional[str] = None,
) -> tuple:
    """Run faster-whisper against the WAV at `wav_path`.

    Returns ``(Transcript, raw_payload)`` where ``raw_payload`` is a
    JSON-serializable list of segment dicts mirroring faster-whisper's
    iterator output (for the `transcript.raw.json` artifact).
    """
    from faster_whisper import WhisperModel  # lazy: optional dep

    model_id = model or "large-v3"
    model_obj = WhisperModel(model_id, device="auto", compute_type="auto")

    seg_iter, info = model_obj.transcribe(
        str(wav_path),
        word_timestamps=True,
        vad_filter=True,
    )

    segments: List[TranscriptSegment] = []
    raw_segments: List[dict] = []

    for seg in seg_iter:
        words: List[TranscriptWord] = []
        raw_words: List[dict] = []
        for w in (seg.words or []):
            try:
                prob = float(getattr(w, "probability", 0.0) or 0.0)
            except (TypeError, ValueError):
                prob = 0.0
            tw = TranscriptWord(
                text=str(getattr(w, "word", "") or ""),
                start_sec=float(getattr(w, "start", 0.0) or 0.0),
                end_sec=float(getattr(w, "end", 0.0) or 0.0),
                confidence=prob,
            )
            words.append(tw)
            raw_words.append(
                {
                    "word": tw.text,
                    "start": tw.start_sec,
                    "end": tw.end_sec,
                    "probability": tw.confidence,
                }
            )

        ts = TranscriptSegment(
            start_sec=float(getattr(seg, "start", 0.0) or 0.0),
            end_sec=float(getattr(seg, "end", 0.0) or 0.0),
            text=str(getattr(seg, "text", "") or "").strip(),
            words=words,
        )
        segments.append(ts)
        raw_segments.append(
            {
                "id": getattr(seg, "id", None),
                "start": ts.start_sec,
                "end": ts.end_sec,
                "text": ts.text,
                "avg_logprob": getattr(seg, "avg_logprob", None),
                "no_speech_prob": getattr(seg, "no_speech_prob", None),
                "words": raw_words,
            }
        )

    duration_sec = float(getattr(info, "duration", 0.0) or 0.0)
    language = str(getattr(info, "language", "") or "")

    total_words, mean_conf = _word_count_and_mean_conf(segments)
    transcript = Transcript(
        language=language,
        duration_sec=duration_sec,
        backend="faster-whisper",
        model_id=model_id,
        segments=segments,
        word_count=total_words,
        mean_word_confidence=mean_conf,
    )
    raw_payload = {
        "info": {
            "language": language,
            "language_probability": getattr(info, "language_probability", None),
            "duration": duration_sec,
        },
        "segments": raw_segments,
    }
    return transcript, raw_payload


def _transcribe_openai(
    wav_path: Path,
    model: Optional[str] = None,
) -> tuple:
    """Run OpenAI Whisper API against the WAV at `wav_path`.

    Returns ``(Transcript, raw_payload)`` where ``raw_payload`` is the
    raw JSON-decoded response (verbose_json format) for the
    `transcript.raw.json` artifact.

    Note: this is the ONE place in `backend/lambda_functions/` allowed to
    instantiate the raw `openai` SDK outside of `vision_client.py`. The
    ASR endpoint (``audio.transcriptions.create``) is a different shape
    than chat completions and does not belong on the `VisionClient`
    interface.
    """
    import openai  # lazy: optional dep

    model_id = model or "whisper-1"
    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    with open(wav_path, "rb") as fh:
        response = client.audio.transcriptions.create(
            model=model_id,
            file=fh,
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
        )

    if hasattr(response, "model_dump"):
        raw_payload = response.model_dump()
    elif isinstance(response, dict):
        raw_payload = response
    else:
        raw_payload = json.loads(json.dumps(response, default=lambda o: o.__dict__))

    duration_sec = float(raw_payload.get("duration") or 0.0)
    language = str(raw_payload.get("language") or "")

    raw_segments = list(raw_payload.get("segments") or [])
    raw_words = list(raw_payload.get("words") or [])

    has_word_probs = False
    words_by_seg_idx: List[List[TranscriptWord]] = [[] for _ in raw_segments]
    if raw_segments and raw_words:
        for w in raw_words:
            try:
                start = float(w.get("start") or 0.0)
                end = float(w.get("end") or 0.0)
            except (TypeError, ValueError):
                continue
            text = str(w.get("word") or "")
            prob = w.get("probability") or w.get("confidence")
            try:
                conf = float(prob) if prob is not None else 0.0
            except (TypeError, ValueError):
                conf = 0.0
            if conf > 0.0:
                has_word_probs = True
            tw = TranscriptWord(text=text, start_sec=start, end_sec=end, confidence=conf)
            placed = False
            for idx, seg in enumerate(raw_segments):
                try:
                    s_start = float(seg.get("start") or 0.0)
                    s_end = float(seg.get("end") or 0.0)
                except (TypeError, ValueError):
                    continue
                if s_start <= tw.start_sec <= s_end + 1e-3:
                    words_by_seg_idx[idx].append(tw)
                    placed = True
                    break
            if not placed and words_by_seg_idx:
                words_by_seg_idx[-1].append(tw)

    segments: List[TranscriptSegment] = []
    if raw_segments:
        for idx, seg in enumerate(raw_segments):
            try:
                s_start = float(seg.get("start") or 0.0)
                s_end = float(seg.get("end") or 0.0)
            except (TypeError, ValueError):
                s_start = s_end = 0.0
            ts = TranscriptSegment(
                start_sec=s_start,
                end_sec=s_end,
                text=str(seg.get("text") or "").strip(),
                words=words_by_seg_idx[idx] if idx < len(words_by_seg_idx) else [],
            )
            segments.append(ts)
    elif raw_words:
        # No segment-level breakdown but word-level present: collapse all
        # words into one synthetic segment so downstream consumers still
        # see something usable.
        words: List[TranscriptWord] = []
        for w in raw_words:
            try:
                start = float(w.get("start") or 0.0)
                end = float(w.get("end") or 0.0)
            except (TypeError, ValueError):
                continue
            text = str(w.get("word") or "")
            prob = w.get("probability") or w.get("confidence")
            try:
                conf = float(prob) if prob is not None else 0.0
            except (TypeError, ValueError):
                conf = 0.0
            if conf > 0.0:
                has_word_probs = True
            words.append(
                TranscriptWord(text=text, start_sec=start, end_sec=end, confidence=conf)
            )
        if words:
            seg_text = str(raw_payload.get("text") or "").strip()
            segments.append(
                TranscriptSegment(
                    start_sec=words[0].start_sec,
                    end_sec=words[-1].end_sec,
                    text=seg_text,
                    words=words,
                )
            )

    if not has_word_probs:
        _LOGGER.warning(
            "[transcription] openai-whisper-api response did not include "
            "word-level probabilities; mean_word_confidence will be 0.0."
        )

    total_words, mean_conf = _word_count_and_mean_conf(segments)
    transcript = Transcript(
        language=language,
        duration_sec=duration_sec,
        backend="openai-whisper-api",
        model_id=model_id,
        segments=segments,
        word_count=total_words,
        mean_word_confidence=mean_conf,
    )
    return transcript, raw_payload


def transcribe(
    video_path: Path,
    out_dir: Path,
    *,
    prefer: str = "auto",
    model: Optional[str] = None,
) -> Optional[Transcript]:
    """Top-level entrypoint.

    Selects a backend via `detect_backend`. When no backend is available,
    prints (NOT raises) the documented skip message and returns ``None``
    so the caller can fall through to the visual-only pipeline.

    On success, writes the four artifacts described in the module
    docstring under `out_dir` and returns the populated `Transcript`.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    backend = detect_backend(prefer)
    if backend is None:
        print(
            "[transcription] no ASR backend available; skipping. Install "
            "faster-whisper (`pip install faster-whisper`) or set "
            "OPENAI_API_KEY to enable."
        )
        return None

    wav_path = extract_audio(Path(video_path), out_dir)

    if backend == "faster-whisper":
        transcript, raw_payload = _transcribe_faster_whisper(wav_path, model)
    elif backend == "openai-whisper-api":
        transcript, raw_payload = _transcribe_openai(wav_path, model)
    else:
        # Shouldn't happen: detect_backend only returns members of
        # _BACKEND_PRIORITY or None. Treat as a programming error.
        raise RuntimeError(f"Unhandled ASR backend: {backend!r}")

    _write_artifacts(out_dir, transcript, raw_payload)
    return transcript
