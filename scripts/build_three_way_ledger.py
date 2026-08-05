#!/usr/bin/env python3
"""Build three_way_ledger.json — report vs named video tests."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.lambda_functions.cme_three_way_ledger import build_three_way_ledger

DEFAULT_FRAMES = (
    REPO_ROOT
    / "cme_projects/osborn_2021_03/analysis_run_halfsec/comprehensive/comprehensive_frame_analyses.json"
)
DEFAULT_ATOMIC = REPO_ROOT / "cme_projects/osborn_2021_03/claims_atomic.json"
DEFAULT_OUT = REPO_ROOT / "cme_projects/osborn_2021_03/analysis_run_halfsec/three_way_ledger.json"
DEFAULT_SAMPLE = REPO_ROOT / "frontend/public/sample-case/three_way_ledger.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build three-way test reconciliation ledger.")
    parser.add_argument("--frames", type=Path, default=DEFAULT_FRAMES)
    parser.add_argument("--atomic-claims", type=Path, default=DEFAULT_ATOMIC)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sample-out", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--case-id", default="osborn_2021_03")
    args = parser.parse_args()

    frames = json.loads(args.frames.read_text(encoding="utf-8"))
    ledger = build_three_way_ledger(
        frames,
        atomic_claims_path=args.atomic_claims,
        case_id=args.case_id,
    )

    for path in (args.out, args.sample_out):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {path} ({ledger['total_rows']} rows)")

    print(
        f"Summary: performed_not_reported={ledger['performed_not_reported_count']}, "
        f"claimed_not_shown={ledger['claimed_not_shown_count']}, "
        f"claimed_and_observed={ledger['claimed_and_observed_count']}, "
        f"performed_incorrectly={ledger['performed_incorrectly_count']}"
    )


if __name__ == "__main__":
    main()
