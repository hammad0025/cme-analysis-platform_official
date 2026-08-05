#!/usr/bin/env python3
"""One-shot: repair the Deshefy live session (cme_89f184bd4e80) artifacts.

The original link run pulled three entries from the Osborne sample-case
directory via SAMPLE_EXTRAS, so the live session ended up with:
  - MANIFEST.json           -> Osborne sample manifest (wrong case)
  - behavior_dashboard.html -> Osborne sample dashboard (wrong case)
and it was missing the transcript_json / transcript_txt artifacts that the
Gadson reference session (cme_e855a70f1e96) exposes.

This script:
  1. Overwrites MANIFEST.json with the real Deshefy run manifest.
  2. Uploads audio/transcript.json + transcript.txt as transcript_json /
     transcript_txt artifacts (same layout as Gadson).
  3. Removes the behavior_dashboard_html artifact key and deletes the
     wrong-case S3 object.
Only those keys are touched; nothing else in the session record changes
except updated_at.
"""
import json
import sys
import time
from pathlib import Path

import boto3

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.link_local_analysis_to_session import presign, upload_file

SESSION_ID = "cme_89f184bd4e80"
BUCKET = "cme-analysis-recordings-388846700527"
TABLE = "cme-sessions"
REGION = "us-east-1"
RUN_DIR = REPO_ROOT / "cme_projects/Deshefy_Alan/analysis_run"

REPORTS_PREFIX = f"cme-reports/{SESSION_ID}"

# (local relative path, s3 key, artifact-map label)
UPLOADS = [
    ("MANIFEST.json", f"{REPORTS_PREFIX}/MANIFEST.json", "MANIFEST_json"),
    ("audio/transcript.json", f"{REPORTS_PREFIX}/transcript.json", "transcript_json"),
    ("audio/transcript.txt", f"{REPORTS_PREFIX}/transcript.txt", "transcript_txt"),
]

REMOVE_LABELS = ["behavior_dashboard_html"]
REMOVE_S3_KEYS = [f"{REPORTS_PREFIX}/behavior_dashboard.html"]

s3 = boto3.client("s3", region_name=REGION)
table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)

new_artifact_keys: dict[str, str] = {}
for rel, key, label in UPLOADS:
    local = RUN_DIR / rel
    if not local.is_file():
        raise SystemExit(f"missing local artifact: {local}")
    upload_file(s3, BUCKET, key, local)
    new_artifact_keys[label] = key

for key in REMOVE_S3_KEYS:
    s3.delete_object(Bucket=BUCKET, Key=key)
    print(f"  deleted s3://{BUCKET}/{key}")

now = int(time.time())
set_parts = ["updated_at = :updated"]
remove_parts: list[str] = []
expr_names: dict[str, str] = {}
expr_values: dict[str, object] = {":updated": now}

for i, (label, key) in enumerate(sorted(new_artifact_keys.items())):
    expr_names[f"#ak{i}"] = label
    set_parts.append(f"analysis_artifacts.#ak{i} = :ak{i}")
    set_parts.append(f"artifact_urls.#ak{i} = :au{i}")
    expr_values[f":ak{i}"] = key
    expr_values[f":au{i}"] = presign(s3, BUCKET, key)

for j, label in enumerate(REMOVE_LABELS):
    expr_names[f"#rm{j}"] = label
    remove_parts.append(f"analysis_artifacts.#rm{j}")
    remove_parts.append(f"artifact_urls.#rm{j}")

update_expr = "SET " + ", ".join(set_parts)
if remove_parts:
    update_expr += " REMOVE " + ", ".join(remove_parts)

table.update_item(
    Key={"session_id": SESSION_ID},
    UpdateExpression=update_expr,
    ExpressionAttributeNames=expr_names,
    ExpressionAttributeValues=expr_values,
)

print(f"\nDynamoDB session {SESSION_ID} updated")
print(json.dumps({
    "artifact_keys_added_or_refreshed": new_artifact_keys,
    "artifact_keys_removed": REMOVE_LABELS,
    "s3_objects_deleted": REMOVE_S3_KEYS,
    "updated_at": now,
}, indent=2))
