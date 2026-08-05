#!/usr/bin/env python3
"""One-shot: push the Gadson transcript + refreshed report artifacts to the
live session cme_e855a70f1e96.

Deliberately a targeted subset of scripts/link_local_analysis_to_session.py:
the session is already linked and live (E2E tests may be running against it),
so this only ADDS the transcript keys and OVERWRITES the regenerated report
artifacts. No existing S3 objects are deleted or renamed, and the DynamoDB
update touches only transcript_uri, the new/refreshed artifact map entries,
and updated_at.
"""
import json
import sys
import time
from pathlib import Path

import boto3

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.link_local_analysis_to_session import content_type, presign, upload_file

SESSION_ID = "cme_e855a70f1e96"
BUCKET = "cme-analysis-recordings-388846700527"
TABLE = "cme-sessions"
REGION = "us-east-1"
RUN_DIR = REPO_ROOT / "cme_projects/Gadson_Alethea/analysis_run_2026_07"

REPORTS_PREFIX = f"cme-reports/{SESSION_ID}"
TRANSCRIPT_KEY = f"cme-transcripts/{SESSION_ID}/transcript_0.json"

# (local relative path, s3 key, artifact-map label or None)
UPLOADS = [
    ("audio/transcript.json", TRANSCRIPT_KEY, None),
    ("audio/transcript.json", f"{REPORTS_PREFIX}/transcript.json", "transcript_json"),
    ("audio/transcript.txt", f"{REPORTS_PREFIX}/transcript.txt", "transcript_txt"),
    ("STANDARD_CME_REPORT.html", f"{REPORTS_PREFIX}/standard_report.html", "standard_report_html"),
    ("STANDARD_CME_REPORT.html", f"{REPORTS_PREFIX}/report.html", "report_html"),
    ("STANDARD_CME_REPORT.pdf", f"{REPORTS_PREFIX}/standard_report.pdf", "standard_report_pdf"),
    ("MANIFEST.json", f"{REPORTS_PREFIX}/MANIFEST.json", "MANIFEST_json"),
]

s3 = boto3.client("s3", region_name=REGION)
table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)

new_artifact_keys: dict[str, str] = {}
for rel, key, label in UPLOADS:
    local = RUN_DIR / rel
    if not local.is_file():
        raise SystemExit(f"missing local artifact: {local}")
    upload_file(s3, BUCKET, key, local)
    if label:
        new_artifact_keys[label] = key

now = int(time.time())
transcript_uri = f"s3://{BUCKET}/{TRANSCRIPT_KEY}"

expr_parts = ["transcript_uri = :turi", "updated_at = :updated"]
expr_names: dict[str, str] = {}
expr_values: dict[str, object] = {":turi": transcript_uri, ":updated": now}

for i, (label, key) in enumerate(sorted(new_artifact_keys.items())):
    expr_names[f"#ak{i}"] = label
    expr_names[f"#au{i}"] = label
    expr_parts.append(f"analysis_artifacts.#ak{i} = :ak{i}")
    expr_parts.append(f"artifact_urls.#au{i} = :au{i}")
    expr_values[f":ak{i}"] = key
    expr_values[f":au{i}"] = presign(s3, BUCKET, key)

table.update_item(
    Key={"session_id": SESSION_ID},
    UpdateExpression="SET " + ", ".join(expr_parts),
    ExpressionAttributeNames=expr_names,
    ExpressionAttributeValues=expr_values,
)

print(f"\nDynamoDB session {SESSION_ID} updated (additive)")
print(json.dumps({
    "transcript_uri": transcript_uri,
    "artifact_keys_added_or_refreshed": new_artifact_keys,
    "updated_at": now,
}, indent=2))
