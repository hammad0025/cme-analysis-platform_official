# Audio Transcription (roadmap A3, first half)

This document describes the auto-transcription pass added by roadmap
item A3. The pipeline now produces a word-level transcript so the
verbal-behavior pass can run end-to-end without a manually-supplied
transcript file.

The transcription pass is OPTIONAL by design. The default
`python analyze_cme_full.py video.mp4` flow still works with only
`OPENAI_API_KEY` set: when no ASR backend is available, the
transcription step prints a clear skip message and the pipeline
proceeds with the visual-only passes, exactly as it did pre-A3.

## Backends

Two backends are supported. Both are optional and are imported lazily
at runtime so the package install does not require either:

### 1. `faster-whisper` (preferred, local)

- Install: `pip install faster-whisper`
- Default model: `large-v3` (override via `--model` on the CLI; not yet
  wired through `analyze_cme_full.py`, but available via the
  `cme_transcription.transcribe(..., model=...)` API).
- Hardware: faster-whisper auto-selects CUDA / Metal / CPU. We pass
  `device="auto"` and `compute_type="auto"` so installs work on all
  three. Large model weights are cached under the standard Hugging Face
  cache (`~/.cache/huggingface`) and downloaded on first use; expect
  ~3 GB for `large-v3`.
- Cost: zero per-call (model runs locally). The trade-off is the
  large dependency footprint and the model-download warm-up cost on
  first run.

### 2. `openai-whisper-api` (cloud fallback)

- Install: the `openai` package is already in `backend/requirements.txt`.
- Requires: `OPENAI_API_KEY` env var.
- Default model: `whisper-1`.
- Cost: order-of-magnitude $0.006 per minute of audio at this writing;
  consult the OpenAI pricing page for current numbers.
- Note: response shapes vary; older responses omit per-word
  probabilities. When that happens, `mean_word_confidence` is recorded
  as `0.0` and the standard report appends a `(transcript confidence
  not estimable for this backend)` parenthetical to the VERBAL EVIDENCE
  section header. This is intentional: silently displaying `0% mean
  confidence` would be misleading.

## Selection logic

`backend/lambda_functions/cme_transcription.py::detect_backend(prefer)`
implements the selection. `prefer="auto"` (default) iterates in this
order and returns the first available backend:

1. `faster-whisper` (if `import faster_whisper` succeeds).
2. `openai-whisper-api` (if `OPENAI_API_KEY` is set AND
   `import openai` succeeds).
3. `None`.

Explicit values (`faster-whisper`, `openai-whisper-api`) force the
named backend; the function returns `None` (no exception) if the
named backend is not available. The CLI then surfaces that as the
documented skip path.

## Disabling transcription

```
python analyze_cme_full.py video.mp4 --auto-transcribe false
# OR
python analyze_cme_full.py video.mp4 --asr-backend none
```

Either flag short-circuits the transcription pass without touching the
audio stream of the video. When a user-supplied `--transcript foo.txt`
is also provided, auto-transcription is automatically disabled (the
explicit file wins).

## Artifacts written

When transcription succeeds, the following files land under
`<output>/audio/`:

| File                         | Description                                                                 |
| ---------------------------- | --------------------------------------------------------------------------- |
| `audio.wav`                  | Mono 16-bit PCM 16 kHz audio extracted via `ffmpeg`. ASR-standard format.   |
| `transcript.raw.json`        | Raw backend output, verbatim (faster-whisper iterator dump / OpenAI verbose_json). |
| `transcript.json`            | Normalized `Transcript` dataclass dump (the canonical artifact).            |
| `transcript.txt`             | Plain text; segments joined by newlines. Lets the legacy `--transcript <file>` code path keep working. |

## Provenance and bundle hash

`MANIFEST.json` now embeds a top-level `transcription` block with the
backend name, model id, prompt version, word count, mean confidence,
duration in seconds, and detected language.

The bundle hash includes the text-level transcript artifacts
(`audio/transcript.json`, `audio/transcript.raw.json`, `audio/transcript.txt`)
in its deterministic Merkle-ish digest so a reviewer can re-derive the
same hash from the artifacts on disk.

`audio/audio.wav` is intentionally EXCLUDED from the bundle hash. The
rationale: it is a large binary derivative of the source video
(approximately bit-identical given the same `ffmpeg` invocation) and is
not part of the analytical text surface. Excluding it keeps the
bundle hash cheap to recompute and focused on the artifacts that
reviewers actually audit. The exclusion is recorded explicitly in
`MANIFEST.json` under `bundle_hash_extra_excludes`.

## Diarization (deferred)

Speaker diarization (who-said-what) is NOT implemented in this
iteration. The `Transcript`, `TranscriptSegment`, and `TranscriptWord`
dataclasses reserve an optional `speaker` field so a future iteration
can populate it without churning the schema or invalidating cached
artifacts.

Two viable approaches were considered for the follow-up iteration:

- `pyannote.audio` 3.x: open-source, runs locally; requires a Hugging
  Face token to download the model weights and has a non-trivial
  install footprint. Best fit if we want to keep diarization local.
- AWS Transcribe Medical: managed service; supports diarization +
  medical vocabulary out of the box and ties into the existing AWS
  deployment surface. Per-minute cost is the trade-off.

Picking between the two is the right scope for a dedicated follow-up
iteration rather than bolting onto this PR.
