#!/usr/bin/env python3
"""Convert an AWS Transcribe JSON (transcript_0.json) into the normalized
Transcript artifacts used by the local pipeline (audio/transcript.json,
transcript.txt, transcript.raw.json).

Lets analyze_cme_full.py --transcript-json reuse an existing cloud transcript
instead of re-running ASR locally.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.lambda_functions.cme_transcription import (
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)


def convert(aws_payload: dict, *, language: str = "en") -> Transcript:
    results = aws_payload.get("results") or {}
    items = results.get("items") or []
    items_by_id = {}
    for it in items:
        iid = it.get("id")
        if iid is not None:
            items_by_id[iid] = it

    segments: list[TranscriptSegment] = []
    duration = 0.0
    for seg in results.get("audio_segments") or []:
        words: list[TranscriptWord] = []
        for iid in seg.get("items") or []:
            it = items_by_id.get(iid)
            if not it or it.get("type") != "pronunciation":
                continue
            alt = (it.get("alternatives") or [{}])[0]
            try:
                start = float(it.get("start_time") or 0.0)
                end = float(it.get("end_time") or 0.0)
                conf = float(alt.get("confidence") or 0.0)
            except (TypeError, ValueError):
                continue
            words.append(
                TranscriptWord(
                    text=str(alt.get("content") or ""),
                    start_sec=start,
                    end_sec=end,
                    confidence=conf,
                    speaker=it.get("speaker_label") or seg.get("speaker_label"),
                )
            )
        try:
            s_start = float(seg.get("start_time") or (words[0].start_sec if words else 0.0))
            s_end = float(seg.get("end_time") or (words[-1].end_sec if words else 0.0))
        except (TypeError, ValueError):
            s_start = words[0].start_sec if words else 0.0
            s_end = words[-1].end_sec if words else 0.0
        duration = max(duration, s_end)
        segments.append(
            TranscriptSegment(
                start_sec=s_start,
                end_sec=s_end,
                text=str(seg.get("transcript") or "").strip(),
                words=words,
                speaker=seg.get("speaker_label"),
            )
        )

    total_words = sum(len(s.words) for s in segments)
    confs = [w.confidence for s in segments for w in s.words if w.confidence > 0.0]
    mean_conf = sum(confs) / len(confs) if confs else 0.0

    return Transcript(
        language=language,
        duration_sec=duration,
        backend="aws-transcribe-medical",
        model_id=str(aws_payload.get("jobName") or "aws-transcribe"),
        segments=segments,
        word_count=total_words,
        mean_word_confidence=mean_conf,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="AWS Transcribe JSON -> normalized Transcript artifacts")
    parser.add_argument("aws_json", type=Path, help="AWS Transcribe output JSON (transcript_0.json)")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory for transcript.json/.txt/.raw.json")
    args = parser.parse_args()

    aws_payload = json.loads(args.aws_json.read_text(encoding="utf-8"))
    transcript = convert(aws_payload)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_path = out_dir / "transcript.raw.json"
    raw_path.write_text(
        json.dumps(aws_payload, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
    )
    transcript.raw_path = "transcript.raw.json"

    (out_dir / "transcript.json").write_text(
        json.dumps(asdict(transcript), indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "transcript.txt").write_text(
        "\n".join((s.text or "").strip() for s in transcript.segments).strip() + "\n",
        encoding="utf-8",
    )

    print(
        f"Converted: backend={transcript.backend} words={transcript.word_count} "
        f"segments={len(transcript.segments)} duration={transcript.duration_sec:.1f}s "
        f"mean_conf={transcript.mean_word_confidence:.3f}"
    )
    print(f"Wrote {out_dir}/transcript.json, transcript.txt, transcript.raw.json")


if __name__ == "__main__":
    main()
