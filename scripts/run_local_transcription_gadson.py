#!/usr/bin/env python3
"""One-shot: run local faster-whisper transcription for the Gadson case.

Writes the standard pipeline artifacts (audio.wav, transcript.raw.json,
transcript.json, transcript.txt) into the existing analysis run dir, exactly
as analyze_cme_full.py's PHASE 1b would have done had faster-whisper been
installed during the original run.
"""
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.lambda_functions.cme_transcription import transcribe

VIDEO = REPO_ROOT / "cme_projects/Gadson_Alethea/video.mp4"
OUT_DIR = REPO_ROOT / "cme_projects/Gadson_Alethea/analysis_run_2026_07/audio"

t0 = time.perf_counter()
transcript = transcribe(
    video_path=VIDEO,
    out_dir=OUT_DIR,
    prefer="faster-whisper",
    model="small",
)
elapsed = time.perf_counter() - t0

if transcript is None:
    print("FAILED: no transcript produced")
    sys.exit(1)

print(
    f"DONE backend={transcript.backend} model={transcript.model_id} "
    f"language={transcript.language} duration_sec={transcript.duration_sec:.1f} "
    f"segments={len(transcript.segments)} words={transcript.word_count} "
    f"mean_conf={transcript.mean_word_confidence:.3f} wall_sec={elapsed:.1f}"
)
