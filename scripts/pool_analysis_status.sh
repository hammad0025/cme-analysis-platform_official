#!/usr/bin/env bash
# Quick status for pool Las Vegas half-second CME analysis run.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_DIR="$ROOT/cme_projects/pool_las_vegas_2023_09_21"
LOG="$PROJECT_DIR/analysis_run.log"
FRAMES_DIRS=(
  "$PROJECT_DIR/analysis_run_halfsec/frames"
  "$PROJECT_DIR/frames"
)

echo "=== Pool analysis status ==="
echo "Log: $LOG"
echo ""

if pgrep -fl "analyze_cme_full.py" >/dev/null 2>&1; then
  echo "Process: RUNNING"
  pgrep -fl "analyze_cme_full.py" | head -3 || true
else
  echo "Process: not found (may have finished or failed)"
fi
echo ""

frame_count=""
frame_dir=""
for d in "${FRAMES_DIRS[@]}"; do
  if [[ -d "$d" ]]; then
    n=$(find "$d" -maxdepth 1 -name '*.jpg' 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$n" -gt 0 ]]; then
      frame_count="$n"
      frame_dir="$d"
      break
    fi
  fi
done

if [[ -z "$frame_count" ]]; then
  for d in /tmp/cme_full_analysis_*/frames; do
    if [[ -d "$d" ]]; then
      n=$(find "$d" -maxdepth 1 -name '*.jpg' 2>/dev/null | wc -l | tr -d ' ')
      if [[ "$n" -gt 0 ]]; then
        frame_count="$n"
        frame_dir="$d"
        break
      fi
    fi
  done
fi

if [[ -n "$frame_count" ]]; then
  echo "Frames extracted: $frame_count (in $frame_dir)"
else
  echo "Frames extracted: 0 (none found yet)"
fi
echo ""

if [[ -f "$LOG" ]]; then
  echo "=== Last 20 lines of log ==="
  tail -n 20 "$LOG"
else
  echo "Log file not found yet."
fi
