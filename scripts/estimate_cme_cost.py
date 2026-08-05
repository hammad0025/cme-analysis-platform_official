#!/usr/bin/env python3
"""Estimate API cost for analyze_cme_full.py before running."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.lambda_functions.cme_analysis_utils import (
    PRESET_INTERVALS,
    estimate_full_analysis_cost_usd,
    median_cost_per_vision_call_usd,
)


def main():
    p = argparse.ArgumentParser(description="Estimate dual-pass vision cost from video duration")
    p.add_argument("videos", nargs="+", help="Video paths")
    p.add_argument("-i", "--interval", type=float, default=None)
    p.add_argument("--preset", choices=list(PRESET_INTERVALS.keys()), default=None)
    p.add_argument("-t", "--transcript-words", type=int, default=0, help="Word count if analyzing transcript")
    args = p.parse_args()

    if args.interval is not None:
        interval = args.interval
    elif args.preset:
        interval = PRESET_INTERVALS[args.preset]
    else:
        interval = 5.0

    est = estimate_full_analysis_cost_usd(
        args.videos,
        interval,
        dual_vision_pass=True,
        transcript_word_count=args.transcript_words,
    )
    print(f"Duration: {est['total_duration_sec']:.1f}s ({est['total_duration_sec']/60:.1f} min)")
    print(f"Interval: {interval}s")
    print(f"Estimated frames: {est['estimated_frames']}")
    print(f"Vision API calls (2 passes): {est['vision_api_calls']}")
    print(f"Est. vision USD: ${est['estimated_vision_cost_usd']:.2f}")
    print(f"Est. transcript USD: ${est['estimated_transcript_cost_usd']:.2f}")
    print(f"Est. total USD: ${est['estimated_total_usd']:.2f}")
    med = median_cost_per_vision_call_usd()
    if med is not None:
        alt = est["vision_api_calls"] * med + est["estimated_transcript_cost_usd"]
        print(f"History-based vision rate (~${med:.4f}/call): total ~${alt:.2f}")


if __name__ == "__main__":
    main()
