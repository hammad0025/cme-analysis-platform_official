#!/usr/bin/env python3
"""Build named_test_index.json from existing comprehensive frame analyses."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.lambda_functions.cme_named_test_index import build_named_test_index

DEFAULT_FRAMES = (
    REPO_ROOT
    / "cme_projects/osborn_2021_03/analysis_run_halfsec/comprehensive/comprehensive_frame_analyses.json"
)
DEFAULT_OUT = REPO_ROOT / "cme_projects/osborn_2021_03/analysis_run_halfsec/named_test_index.json"
DEFAULT_SAMPLE = REPO_ROOT / "frontend/public/sample-case/named_test_index.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build named orthopedic test index from frame JSON.")
    parser.add_argument("--frames", type=Path, default=DEFAULT_FRAMES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sample-out", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--case-id", default="osborn_2021_03")
    args = parser.parse_args()

    frames = json.loads(args.frames.read_text(encoding="utf-8"))
    rel = str(args.frames.relative_to(REPO_ROOT)) if str(args.frames).startswith(str(REPO_ROOT)) else str(args.frames)
    index = build_named_test_index(frames, case_id=args.case_id, source_path=rel)

    for path in (args.out, args.sample_out):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {path} ({index['total_detections']} detections)")

    for key, count in sorted(index.get("detection_counts", {}).items()):
        print(f"  {key}: {count}")


if __name__ == "__main__":
    main()
