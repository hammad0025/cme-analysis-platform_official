#!/usr/bin/env python3
"""
Link a completed local CME analysis run to a live DynamoDB session (no re-analysis).

Uploads report artifacts to S3 and marks the session completed with artifact keys.
Optionally attaches video and transcript from another session or local file.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import time
import uuid
from pathlib import Path

import boto3
from decimal import Decimal

DEFAULT_BUCKET = "cme-analysis-recordings-388846700527"
DEFAULT_TABLE = "cme-sessions"
DEFAULT_REGION = "us-east-1"
DEFAULT_VIDEO_SOURCE_SESSION = "cme_8cc20baf0f10"
DEFAULT_LOCAL_VIDEO = Path(
    "/Users/hammadhaque/Downloads/CME - Defendant BI - Dr. Osborne  3.9.21 (video).mp4"
)

# Maps local filename -> S3 key under cme-reports/{session_id}/
UPLOAD_MAP = [
    ("STANDARD_CME_REPORT.html", "standard_report.html"),
    ("STANDARD_CME_REPORT.html", "report.html"),
    ("STANDARD_CME_REPORT.pdf", "standard_report.pdf"),
    ("comprehensive/comprehensive_analysis.json", "comprehensive_analysis.json"),
    ("test_ledger.json", "test_ledger.json"),
    ("named_test_index.json", "named_test_index.json"),
    ("three_way_ledger.json", "three_way_ledger.json"),
    ("comprehensive/claim_verdicts.json", "claim_verdicts.json"),
    ("../claims_atomic.json", "claims_atomic.json"),
    ("comprehensive/analysis_report.txt", "analysis_report.txt"),
    ("behavior_summary.json", "behavior_summary.json"),
    ("cost_actual.json", "cost_actual.json"),
    ("cme_report_Wendy_Scammon.html", "cme_report.html"),
    ("behavior/behavior_report.txt", "behavior_report.txt"),
]

# Extra files from sample-case bundle (derived summaries / dashboard)
SAMPLE_EXTRAS = [
    ("behavior_summary.json", "behavior_summary.json"),
    ("behavior_dashboard.html", "behavior_dashboard.html"),
    ("claim_verdicts.json", "claim_verdicts.json"),
    ("claims_atomic.json", "claims_atomic.json"),
    ("named_test_index.json", "named_test_index.json"),
    ("three_way_ledger.json", "three_way_ledger.json"),
    ("MANIFEST.json", "MANIFEST.json"),
]


def content_type(name: str) -> str:
    if name.endswith(".html"):
        return "text/html"
    if name.endswith(".pdf"):
        return "application/pdf"
    if name.endswith(".json"):
        return "application/json"
    if name.endswith(".mp4"):
        return "video/mp4"
    if name.endswith(".txt"):
        return "text/plain"
    return "application/octet-stream"


def upload_file(s3, bucket: str, key: str, path: Path) -> None:
    s3.upload_file(
        str(path),
        bucket,
        key,
        ExtraArgs={"ContentType": content_type(path.name)},
    )
    print(f"  uploaded s3://{bucket}/{key}")


def to_dynamo(value):
    """Convert floats to Decimal for DynamoDB."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_dynamo(v) for v in value]
    return value


def presign(s3, bucket: str, key: str, expires: int = 604800) -> str:
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )


def _find_source_video_key(s3, bucket: str, source_session: str) -> str | None:
    prefix = f"cme-recordings/{source_session}/"
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    for obj in resp.get("Contents") or []:
        key = obj["Key"]
        name = key.split("/")[-1]
        if name.startswith("."):
            continue
        if any(name.lower().endswith(ext) for ext in (".mp4", ".mov", ".m4v", ".mpeg", ".mpg", ".m")):
            return key
    return None


def attach_video(
    s3,
    bucket: str,
    session_id: str,
    *,
    source_session: str | None,
    local_path: Path | None,
    dry_run: bool,
) -> dict | None:
    """Copy or upload video; return recording metadata dict."""
    if local_path and local_path.is_file():
        dest_filename = local_path.name.replace(" ", "_")
    else:
        dest_filename = "CME_-_Defendant_BI_-_Dr._Osborne__3.9.21_(video).mp4"
    dest_key = f"cme-recordings/{session_id}/{uuid.uuid4().hex[:8]}_{dest_filename}"
    file_size = None

    if local_path and local_path.is_file():
        file_size = local_path.stat().st_size
        if dry_run:
            print(f"  [dry-run] would upload {local_path} -> s3://{bucket}/{dest_key}")
        else:
            upload_file(s3, bucket, dest_key, local_path)
    elif source_session:
        src_key = _find_source_video_key(s3, bucket, source_session)
        if not src_key:
            print(f"  no video found under cme-recordings/{source_session}/")
            return None
        head = s3.head_object(Bucket=bucket, Key=src_key)
        file_size = head.get("ContentLength")
        if dry_run:
            print(f"  [dry-run] would copy s3://{bucket}/{src_key} -> s3://{bucket}/{dest_key}")
        else:
            s3.copy_object(
                Bucket=bucket,
                Key=dest_key,
                CopySource={"Bucket": bucket, "Key": src_key},
                ContentType="video/mp4",
                MetadataDirective="REPLACE",
            )
            print(f"  copied s3://{bucket}/{src_key} -> s3://{bucket}/{dest_key}")
    else:
        print("  skip video: no --video-local-path or --video-source-session")
        return None

    now = int(time.time())
    return {
        "uri": f"s3://{bucket}/{dest_key}",
        "s3_key": dest_key,
        "filename": dest_filename,
        "content_type": "video/mp4",
        "file_size": file_size,
        "uploaded_at": now,
        "recording_slot": 1,
        "display_label": "Video 1",
    }


def attach_transcript(
    s3,
    bucket: str,
    session_id: str,
    *,
    source_session: str,
    dry_run: bool,
) -> str | None:
    """Copy transcript from source session; return transcript s3 URI."""
    src_key = f"cme-transcripts/{source_session}/transcript_0.json"
    dest_key = f"cme-transcripts/{session_id}/transcript_0.json"
    try:
        s3.head_object(Bucket=bucket, Key=src_key)
    except Exception:
        print(f"  transcript not found at s3://{bucket}/{src_key}")
        return None

    if dry_run:
        print(f"  [dry-run] would copy transcript -> s3://{bucket}/{dest_key}")
    else:
        s3.copy_object(
            Bucket=bucket,
            Key=dest_key,
            CopySource={"Bucket": bucket, "Key": src_key},
            ContentType="application/json",
            MetadataDirective="REPLACE",
        )
        print(f"  copied transcript -> s3://{bucket}/{dest_key}")

    return f"s3://{bucket}/{dest_key}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Link local analysis output to a CME session")
    parser.add_argument("--session-id", required=True)
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=Path("cme_projects/osborn_2021_03/analysis_run_halfsec"),
    )
    parser.add_argument(
        "--sample-dir",
        type=Path,
        default=Path("frontend/public/sample-case"),
    )
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--table", default=DEFAULT_TABLE)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--include-video", action="store_true", help="Attach CME recording video")
    parser.add_argument("--include-transcript", action="store_true", help="Copy transcript from source session")
    parser.add_argument(
        "--video-source-session",
        default=DEFAULT_VIDEO_SOURCE_SESSION,
        help="Session id to copy video from when local file missing",
    )
    parser.add_argument(
        "--transcript-source-session",
        default=DEFAULT_VIDEO_SOURCE_SESSION,
        help="Session id to copy transcript from",
    )
    parser.add_argument(
        "--video-local-path",
        type=Path,
        default=DEFAULT_LOCAL_VIDEO,
        help="Local mp4 path (preferred over S3 copy when file exists)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    analysis_dir = args.analysis_dir.resolve()
    sample_dir = args.sample_dir.resolve()
    if not analysis_dir.is_dir():
        raise SystemExit(f"Analysis dir not found: {analysis_dir}")

    prefix = f"cme-reports/{args.session_id}"
    s3 = boto3.client("s3", region_name=args.region)
    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)

    # Load summary JSON for DynamoDB metadata
    comp_path = analysis_dir / "comprehensive" / "comprehensive_analysis.json"
    comprehensive = json.loads(comp_path.read_text()) if comp_path.exists() else {}
    cost_path = analysis_dir / "cost_actual.json"
    cost = json.loads(cost_path.read_text()) if cost_path.exists() else {}

    artifact_keys: dict[str, str] = {}
    uploaded_s3_names: set[str] = set()

    print(f"Linking {analysis_dir.name} -> session {args.session_id}")
    print(f"S3 prefix: s3://{args.bucket}/{prefix}/")

    for rel_local, s3_name in UPLOAD_MAP:
        local = analysis_dir / rel_local
        if not local.is_file():
            print(f"  skip missing {local}")
            continue
        key = f"{prefix}/{s3_name}"
        artifact_keys[s3_name.replace(".", "_")] = key
        uploaded_s3_names.add(s3_name)
        if not args.dry_run:
            upload_file(s3, args.bucket, key, local)

    for sample_name, s3_name in SAMPLE_EXTRAS:
        if s3_name in uploaded_s3_names:
            print(f"  skip sample {sample_name} (analysis dir already uploaded {s3_name})")
            continue
        local = sample_dir / sample_name
        if not local.is_file():
            print(f"  skip missing sample {local}")
            continue
        key = f"{prefix}/{s3_name}"
        artifact_keys[s3_name.replace(".", "_")] = key
        if not args.dry_run:
            upload_file(s3, args.bucket, key, local)

    recording = None
    if args.include_video:
        local_video = args.video_local_path.resolve() if args.video_local_path else None
        recording = attach_video(
            s3,
            args.bucket,
            args.session_id,
            source_session=args.video_source_session,
            local_path=local_video if local_video and local_video.is_file() else None,
            dry_run=args.dry_run,
        )

    transcript_uri = None
    if args.include_transcript:
        transcript_uri = attach_transcript(
            s3,
            args.bucket,
            args.session_id,
            source_session=args.transcript_source_session,
            dry_run=args.dry_run,
        )

    artifact_urls = {}
    if not args.dry_run:
        for label, key in artifact_keys.items():
            artifact_urls[label] = presign(s3, args.bucket, key)

    now = int(time.time())
    plaintiff = comprehensive.get("plaintiff_name") or "Wendy Scammon"
    examiner = comprehensive.get("examiner_name") or "Dr. Brett Osborn DO"
    linked_from = str(analysis_dir.relative_to(analysis_dir.parents[1]))
    analysis_summary = {
        "plaintiff_name": plaintiff,
        "examiner_name": examiner,
        "exam_date": comprehensive.get("exam_date") or "2021-03-09",
        "frame_count": comprehensive.get("total_frames_analyzed") or cost.get("frame_count"),
        "cost_usd": cost.get("actual_total_usd"),
        "examination_quality_score": comprehensive.get("examination_quality_score"),
        "professionalism_score": comprehensive.get("professionalism_score"),
        "linked_from": linked_from,
        "linked_at": now,
    }

    update_item: dict = {
        "status": "completed",
        "processing_stage": "report_generated",
        "updated_at": now,
        "completed_at": now,
        "analysis_artifacts": artifact_keys,
        "analysis_summary": analysis_summary,
        "metadata": {
            "linked_local_run": linked_from,
            "is_backfilled": True,
            "patient_report_name": plaintiff,
            "examiner_report_name": examiner,
        },
    }
    if artifact_urls:
        update_item["artifact_urls"] = artifact_urls
    if recording:
        update_item["recordings"] = [recording]
        update_item["video_uri"] = recording["uri"]
    if transcript_uri:
        update_item["transcript_uri"] = transcript_uri
        update_item["metadata"]["transcript_source_session"] = args.transcript_source_session

    if args.dry_run:
        print("Dry run — DynamoDB update would set:")
        print(json.dumps(update_item, indent=2, default=str))
        return

    expr_parts = [
        "#status = :status",
        "processing_stage = :stage",
        "updated_at = :updated",
        "completed_at = :completed_at",
        "analysis_artifacts = :artifacts",
        "artifact_urls = :urls",
        "analysis_summary = :summary",
        "metadata = :meta",
    ]
    expr_values = {
        ":status": "completed",
        ":stage": "report_generated",
        ":updated": now,
        ":completed_at": now,
        ":artifacts": artifact_keys,
        ":urls": artifact_urls,
        ":summary": to_dynamo(analysis_summary),
        ":meta": to_dynamo(update_item["metadata"]),
    }
    if recording:
        expr_parts.extend(["recordings = :recordings", "video_uri = :video_uri"])
        expr_values[":recordings"] = [to_dynamo(recording)]
        expr_values[":video_uri"] = recording["uri"]
    if transcript_uri:
        expr_parts.append("transcript_uri = :transcript_uri")
        expr_values[":transcript_uri"] = transcript_uri

    table.update_item(
        Key={"session_id": args.session_id},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues=expr_values,
    )
    print(f"\nDynamoDB session {args.session_id} updated -> completed")
    print(json.dumps({
        "artifact_keys": artifact_keys,
        "analysis_summary": analysis_summary,
        "video_uri": update_item.get("video_uri"),
        "transcript_uri": transcript_uri,
        "recordings": update_item.get("recordings"),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
