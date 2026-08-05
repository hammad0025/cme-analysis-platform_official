#!/usr/bin/env python3
"""One-shot: refresh the Gadson analysis run after adding the ASR transcript.

Mirrors what analyze_cme_full.py does after the transcription phase, without
re-running any paid vision/LLM passes:

1. Update MANIFEST.json: transcription block, artifact list/digests, and the
   recomputed bundle hash (transcript artifacts are part of the hash surface;
   audio/audio.wav stays excluded).
2. Regenerate STANDARD_CME_REPORT.html/.pdf via write_standard_reports so the
   VERBAL EVIDENCE section renders, keeping the previous run's session
   deep-link settings.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.lambda_functions.cme_provenance import compute_bundle_hash
from backend.lambda_functions.cme_report_builder import write_standard_reports
from backend.lambda_functions.cme_transcription import TRANSCRIPTION_PROMPT_VERSION

RUN_DIR = REPO_ROOT / "cme_projects/Gadson_Alethea/analysis_run_2026_07"
CLAIMS_PATH = REPO_ROOT / "cme_projects/Gadson_Alethea/claims.json"

SESSION_ID = "cme_e855a70f1e96"
APP_BASE_URL = "https://cme-analysis-platform-official.vercel.app"
INTERVAL_SEC = 5.0

transcript_path = RUN_DIR / "audio" / "transcript.json"
transcript = json.loads(transcript_path.read_text(encoding="utf-8"))

manifest_path = RUN_DIR / "MANIFEST.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

# Same exclusion sets analyze_cme_full.py used for this run.
presentation_exclusions = set(manifest.get("bundle_hash_excludes") or [])
extra_excludes = set(manifest.get("bundle_hash_extra_excludes") or []) | {"audio/audio.wav"}

bundle_hash, file_pairs = compute_bundle_hash(
    RUN_DIR,
    exclude_names=presentation_exclusions,
    exclude_relpaths=extra_excludes,
)

manifest["transcription"] = {
    "backend": transcript["backend"],
    "model_id": transcript["model_id"],
    "prompt_version": TRANSCRIPTION_PROMPT_VERSION,
    "word_count": transcript["word_count"],
    "mean_confidence": transcript["mean_word_confidence"],
    "duration_sec": transcript["duration_sec"],
    "language": transcript["language"],
}
manifest.setdefault("prompt_versions", {})["transcription"] = TRANSCRIPTION_PROMPT_VERSION
manifest["artifacts"] = [rel for rel, _ in file_pairs]
manifest["artifact_digests"] = {rel: digest for rel, digest in file_pairs}
manifest["bundle_sha256"] = bundle_hash
manifest["bundle_hash_extra_excludes"] = sorted(extra_excludes)
manifest["transcript_added_at"] = datetime.now(timezone.utc).isoformat()

manifest_path.write_text(
    json.dumps(manifest, indent=2, default=str, ensure_ascii=False),
    encoding="utf-8",
)
print(f"MANIFEST updated: bundle_sha256={bundle_hash}")
print(f"  artifacts={len(file_pairs)}")

case_meta = {
    "patient": "Gadson, Alethea",
    "dob": "",
    "examiner": "Dr. Steven Bailey",
    "exam_date": "09/06/2024",
    "injury_date": "",
    "video_length": "39:02",
    "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "run_id": "gadson_2026_07",
    "bundle_sha256": bundle_hash,
    "session_id": SESSION_ID,
    "app_base_url": APP_BASE_URL,
}

std_html, std_pdf = write_standard_reports(
    RUN_DIR, case_meta, CLAIMS_PATH if CLAIMS_PATH.is_file() else None, INTERVAL_SEC
)
print(f"Standard report HTML: {std_html}")
print(f"Standard report PDF: {std_pdf}")
