#!/usr/bin/env python3
"""
Aggregate half-second frame analyses into a searchable orthopedic test ledger.

Uses existing local analysis only — no vision API calls.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FRAMES = (
    REPO_ROOT
    / "cme_projects/osborn_2021_03/analysis_run_halfsec/comprehensive/comprehensive_frame_analyses.json"
)
DEFAULT_CLAIMS = REPO_ROOT / "cme_projects/osborn_2021_03/claims.json"
DEFAULT_BEHAVIOR = (
    REPO_ROOT
    / "cme_projects/osborn_2021_03/analysis_run_halfsec/behavior/behavior_summary.json"
)
DEFAULT_SAMPLE_OUT = REPO_ROOT / "frontend/public/sample-case/test_ledger.json"
DEFAULT_FIXTURE_OUT = REPO_ROOT / "tests/fixtures/test_ledger_osborne.json"

# Gap between frames (seconds) before starting a new event for same test+region.
MAX_GAP_SEC = 12.0

# Drop single-frame blips (half-second sampling noise).
MIN_EVENT_FRAMES = 2

SKIP_TEST_TYPES = {"none", "conversation", ""}

STANDARD_TEST_NAMES: dict[str, str] = {
    "hoffmann": "Hoffmann sign",
    "hoffmanns": "Hoffmann's test",
    "babinski": "Babinski sign",
    "romberg": "Romberg test",
    "rhomberg": "Romberg test",
    "rom": "Range of motion",
    "gait": "Gait assessment",
    "strength": "Manual muscle testing",
    "sensory": "Sensory examination",
    "reflex": "Deep tendon reflexes",
    "reflexes": "Deep tendon reflexes",
    "cranial_nerve": "Cranial nerve examination",
    "cranial_nerves": "Cranial nerve examination",
    "palpation": "Palpation",
    "unknown": "Unspecified examination",
}

BODY_REGION_LABELS: dict[str, str] = {
    "neck": "Cervical spine",
    "shoulder": "Shoulder",
    "arm": "Upper extremity",
    "hand": "Hand / wrist",
    "back": "Thoracic / back",
    "leg": "Lower extremity",
    "foot": "Foot / ankle",
    "face": "Face",
    "head": "Head",
    "full_body": "Full body",
    "none": "General",
    "unknown": "Unspecified",
}

ORTHO_CATEGORIES = {
    "hoffmann",
    "hoffmanns",
    "babinski",
    "romberg",
    "rhomberg",
    "rom",
    "gait",
    "strength",
    "sensory",
    "reflex",
    "reflexes",
    "cranial_nerve",
    "cranial_nerves",
}

CLAIMS_KEY_MAP: dict[str, str] = {
    "cranial_nerves": "cranial_nerve",
    "strength": "strength",
    "rom": "rom",
    "romberg": "romberg",
    "rhomberg": "romberg",
    "sensory": "sensory",
    "reflexes": "reflex",
    "gait": "gait",
    "hoffmann": "hoffmann",
    "babinski": "babinski",
}

# Video types the report addresses as discrete categories (from claims.json).
REPORT_CLAIM_TYPES = {
    "cranial_nerve",
    "strength",
    "rom",
    "romberg",
    "sensory",
    "reflex",
    "gait",
    "hoffmann",
    "babinski",
}

# General exam activity on video — not individually claimed in the defense report.
NON_CLAIM_VIDEO_TYPES = {"palpation", "unknown"}

MODIFIED_ISSUES = {
    "testing_through_clothing",
    "patient_not_in_gown",
    "testing_in_street_shoes",
    "no_gown",
}


def merge_segment_into(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Merge two observed segments of the same test type + body region."""
    target["start_sec"] = min(target["start_sec"], source["start_sec"])
    target["end_sec"] = max(target["end_sec"], source["end_sec"])
    target["duration_sec"] = round(max(target["end_sec"] - target["start_sec"], 0.5), 1)
    target["frame_ids"].extend(source.get("frame_ids") or [])
    target["frame_count"] = len(target["frame_ids"])
    target["technique_issues"] = sorted(
        set(target.get("technique_issues") or []) | set(source.get("technique_issues") or [])
    )
    notes = list(target.get("technique_notes") or [])
    for note in source.get("technique_notes") or []:
        if note and note not in notes:
            notes.append(note)
    target["technique_notes"] = notes[:5]
    target["visibilities"] = (target.get("visibilities") or []) + [source.get("visibility") or "unknown"]


def collapse_by_type_and_region(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (test_type, body_region) — avoids hundreds of duplicate reconciliation rows."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for seg in sorted(segments, key=lambda e: e["start_sec"]):
        key = (seg["test_type"], seg["body_region"])
        if key not in merged:
            copy = dict(seg)
            copy["visibilities"] = [seg.get("visibility") or "unknown"]
            merged[key] = copy
        else:
            merge_segment_into(merged[key], seg)
    collapsed: list[dict[str, Any]] = []
    for raw in merged.values():
        visibility = dominant_visibility(raw.pop("visibilities", []))
        raw["visibility"] = visibility
        raw["technique_verdict"] = compute_technique_verdict(
            observed_on_video=True,
            technique_issues=raw.get("technique_issues") or [],
            visibility=visibility,
        )
        collapsed.append(raw)
    collapsed.sort(key=lambda e: e["start_sec"])
    return collapsed


def aggregate_technique_verdict(clips: list[dict[str, Any]]) -> str:
    if not clips:
        return "not_shown"
    order = {"improper": 4, "modified": 3, "inconclusive": 2, "proper": 1, "not_shown": 0}
    return max((c.get("technique_verdict") or "not_shown" for c in clips), key=lambda v: order.get(v, 0))


def build_report_crosswalk(
    claims: dict[str, str], clips_by_type: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """One honest row per report claim — reconciliation at category level, not per frame."""
    rows: list[dict[str, Any]] = []
    for claim_type, claim_text in claims.items():
        clips = clips_by_type.get(claim_type, [])
        observed = len(clips) > 0
        status = three_way_status(claimed=True, observed=observed)
        start = min(c["start_sec"] for c in clips) if clips else None
        end = max(c["end_sec"] for c in clips) if clips else None
        rows.append(
            {
                "row_kind": "report_summary",
                "test_type": claim_type,
                "test_name": STANDARD_TEST_NAMES.get(
                    claim_type, claim_type.replace("_", " ").title()
                ),
                "body_region": "full_body" if claim_type in ("gait", "romberg") else "unknown",
                "body_region_label": "Report category",
                "variant": infer_variant(claim_type, claim_text),
                "category": "orthopedic_neurologic",
                "start_sec": round(start, 1) if start is not None else None,
                "end_sec": round(end, 1) if end is not None else None,
                "duration_sec": round(max((end or 0) - (start or 0), 0), 1) if observed else 0,
                "frame_ids": [],
                "frame_count": sum(c.get("frame_count", 0) for c in clips),
                "video_file": clips[0].get("video_file") if clips else None,
                "technique_issues": sorted({i for c in clips for i in (c.get("technique_issues") or [])}),
                "technique_notes": [claim_text[:240]],
                "visibility": dominant_visibility([c.get("visibility") or "unknown" for c in clips])
                if clips
                else "not_shown",
                "observed_on_video": observed,
                "claimed_in_report": True,
                "report_claim_text": claim_text,
                "three_way_status": status,
                "technique_verdict": aggregate_technique_verdict(clips),
                "video_clip_count": len(clips),
                "video_clips": [
                    {
                        "start_sec": c["start_sec"],
                        "end_sec": c["end_sec"],
                        "body_region": c["body_region"],
                        "body_region_label": c.get("body_region_label"),
                        "technique_verdict": c.get("technique_verdict"),
                    }
                    for c in clips[:12]
                ],
            }
        )
    rows.sort(
        key=lambda e: (
            0 if e["three_way_status"] == "claimed_not_observed" else 1,
            e["test_name"],
        )
    )
    return rows


def build_video_clip_rows(segments: list[dict[str, Any]], claims: dict[str, str]) -> list[dict[str, Any]]:
    """
    Collapsed video observations for click-to-seek drill-down.
    Do NOT mark these as report claims — palpation is general exam touch, not 'undocumented test'.
    """
    rows: list[dict[str, Any]] = []
    for seg in collapse_by_type_and_region(segments):
        test_type = seg["test_type"]
        in_report = test_type in claims
        rows.append(
            {
                **seg,
                "row_kind": "video_clip",
                "claimed_in_report": False,
                "report_claim_text": claims.get(test_type) if in_report else None,
                "three_way_status": "neither",
                "category": "orthopedic_neurologic"
                if test_type in ORTHO_CATEGORIES
                else "general_examination",
            }
        )
    return rows


def normalize_test_type(raw: str | None) -> str | None:
    if not raw:
        return None
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if key in SKIP_TEST_TYPES:
        return None
    aliases = {
        "range_of_motion": "rom",
        "manual_muscle": "strength",
        "mmt": "strength",
        "dtr": "reflex",
        "cranial": "cranial_nerve",
    }
    return aliases.get(key, key)


def standard_name(test_type: str, body_region: str) -> str:
    base = STANDARD_TEST_NAMES.get(test_type, test_type.replace("_", " ").title())
    region = BODY_REGION_LABELS.get(body_region, body_region.replace("_", " ").title())
    if body_region in ("none", "unknown", "full_body") or test_type in ("gait", "romberg", "rhomberg"):
        return base
    return f"{base} — {region}"


def infer_variant(test_type: str, test_details: str) -> str | None:
    text = (test_details or "").lower()
    if test_type in ("romberg", "rhomberg"):
        if "tandem" in text:
            return "tandem Romberg"
        if "sharp" in text or "negative" in text:
            return "standard Romberg"
        return "Romberg variant"
    if test_type == "gait" and "tandem" in text:
        return "tandem gait"
    if test_type == "rom":
        for word in ("flexion", "extension", "rotation", "sidebend", "side bend", "abduction"):
            if word in text:
                return word.replace(" ", "-")
    if test_type == "sensory":
        for word in ("pinprick", "pin prick", "light touch", "vibration", "proprioception", "joint position"):
            if word in text:
                return word.replace(" ", "-")
    if test_type in ("hoffmann", "babinski"):
        return test_type
    return None


def dominant_visibility(visibilities: list[str]) -> str:
    if not visibilities:
        return "unknown"
    counts = Counter(v.lower() for v in visibilities if v)
    if not counts:
        return "unknown"
    return counts.most_common(1)[0][0]


def compute_technique_verdict(
    *,
    observed_on_video: bool,
    technique_issues: list[str],
    visibility: str,
) -> str:
    if not observed_on_video:
        return "not_shown"
    vis = (visibility or "").lower()
    if vis in ("obscured", "partial", "poor"):
        return "inconclusive"
    if not technique_issues:
        return "proper"
    if any(issue in MODIFIED_ISSUES for issue in technique_issues):
        return "modified"
    return "improper"


def three_way_status(*, claimed: bool, observed: bool) -> str:
    if claimed and observed:
        return "claimed_and_observed"
    if claimed and not observed:
        return "claimed_not_observed"
    if not claimed and observed:
        return "observed_not_reported"
    return "neither"


def group_frames(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    sorted_frames = sorted(frames, key=lambda f: float(f.get("timestamp_sec") or 0))

    for frame in sorted_frames:
        test_type = normalize_test_type(frame.get("test_type"))
        if not test_type:
            continue

        body_region = (frame.get("body_region") or "unknown").strip().lower()
        ts = float(frame.get("timestamp_sec") or 0)
        frame_id = frame.get("frame_id") or ""
        issues = [str(i) for i in (frame.get("technique_issues") or [])]
        visibility = frame.get("visibility") or "unknown"
        details = frame.get("test_details") or frame.get("notes") or ""

        if (
            current
            and current["test_type"] == test_type
            and current["body_region"] == body_region
            and ts - current["end_sec"] <= MAX_GAP_SEC
        ):
            current["end_sec"] = ts
            current["frame_ids"].append(frame_id)
            current["technique_issues"].extend(issues)
            current["visibilities"].append(visibility)
            if details and details not in current["technique_notes"]:
                current["technique_notes"].append(details[:240])
        else:
            if current:
                events.append(finalize_event(current))
            current = {
                "test_type": test_type,
                "body_region": body_region,
                "start_sec": ts,
                "end_sec": ts,
                "frame_ids": [frame_id] if frame_id else [],
                "technique_issues": list(issues),
                "visibilities": [visibility],
                "technique_notes": [details[:240]] if details else [],
                "video_file": frame.get("video_file") or "video1",
            }

    if current:
        events.append(finalize_event(current))

    return filter_short_events(events)


def filter_short_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove observed segments with fewer than MIN_EVENT_FRAMES sampled frames."""
    kept: list[dict[str, Any]] = []
    for event in events:
        if event.get("frame_count", 0) >= MIN_EVENT_FRAMES:
            kept.append(event)
    return kept


def finalize_event(raw: dict[str, Any]) -> dict[str, Any]:
    test_type = raw["test_type"]
    body_region = raw["body_region"]
    unique_issues = sorted(set(raw["technique_issues"]))
    visibility = dominant_visibility(raw["visibilities"])
    variant = infer_variant(test_type, " ".join(raw["technique_notes"]))
    return {
        "test_type": test_type,
        "test_name": standard_name(test_type, body_region),
        "body_region": body_region,
        "body_region_label": BODY_REGION_LABELS.get(body_region, body_region),
        "variant": variant,
        "category": "orthopedic_neurologic" if test_type in ORTHO_CATEGORIES else "general_examination",
        "start_sec": round(raw["start_sec"], 1),
        "end_sec": round(raw["end_sec"], 1),
        "duration_sec": round(max(raw["end_sec"] - raw["start_sec"], 0.5), 1),
        "frame_ids": raw["frame_ids"],
        "frame_count": len(raw["frame_ids"]),
        "video_file": raw.get("video_file") or "video1",
        "technique_issues": unique_issues,
        "technique_notes": raw["technique_notes"][:3],
        "visibility": visibility,
        "observed_on_video": True,
        "claimed_in_report": False,
        "report_claim_text": None,
        "three_way_status": "neither",
        "row_kind": "video_clip",
        "technique_verdict": compute_technique_verdict(
            observed_on_video=True,
            technique_issues=unique_issues,
            visibility=visibility,
        ),
    }


def load_claims(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    claims: dict[str, str] = {}
    for key, value in data.items():
        if key in ("report_context", "initial_ime_reference", "exam_time"):
            continue
        if isinstance(value, str) and value.strip():
            mapped = CLAIMS_KEY_MAP.get(key.lower(), normalize_test_type(key))
            if mapped:
                claims[mapped] = value.strip()
    return claims


def assemble_ledger_events(segments: list[dict[str, Any]], claims: dict[str, str]) -> list[dict[str, Any]]:
    """Report summary rows first, then optional collapsed video clips for drill-down."""
    clip_rows = build_video_clip_rows(segments, claims)
    clips_by_type: dict[str, list[dict[str, Any]]] = {}
    for clip in clip_rows:
        clips_by_type.setdefault(clip["test_type"], []).append(clip)

    report_rows = build_report_crosswalk(claims, clips_by_type)
    return report_rows + clip_rows


def build_ledger(
    frames_path: Path,
    claims_path: Path | None = None,
    behavior_path: Path | None = None,
    case_id: str = "osborn_2021_03",
) -> dict[str, Any]:
    frames = json.loads(frames_path.read_text(encoding="utf-8"))
    if not isinstance(frames, list):
        raise ValueError(f"Expected list of frames in {frames_path}")

    segments = group_frames(frames)
    claims = load_claims(claims_path) if claims_path else {}
    events = assemble_ledger_events(segments, claims)

    report_rows = [e for e in events if e.get("row_kind") == "report_summary"]
    clip_rows = [e for e in events if e.get("row_kind") == "video_clip"]

    behavior_meta = {}
    if behavior_path and behavior_path.is_file():
        behavior = json.loads(behavior_path.read_text(encoding="utf-8"))
        behavior_meta = {
            "behavior_issue_count": len(behavior.get("behavior_issues") or []),
            "eye_contact_score": behavior.get("eye_contact_score"),
        }

    type_counts = Counter(e["test_type"] for e in events if e.get("observed_on_video"))
    verdict_counts = Counter(e["technique_verdict"] for e in events)

    return {
        "schema_version": "1.1.0",
        "case_id": case_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_frames_path": str(frames_path.relative_to(REPO_ROOT))
        if str(frames_path).startswith(str(REPO_ROOT))
        else str(frames_path),
        "frame_interval_sec": 0.5,
        "total_events": len(events),
        "report_summary_count": len(report_rows),
        "video_clip_count": len(clip_rows),
        "observed_event_count": sum(1 for e in events if e.get("observed_on_video")),
        "claimed_only_count": sum(
            1 for e in report_rows if e.get("three_way_status") == "claimed_not_observed"
        ),
        "observed_not_reported_count": sum(
            1 for e in events if e.get("three_way_status") == "observed_not_reported"
        ),
        "test_type_counts": dict(type_counts),
        "verdict_counts": dict(verdict_counts),
        "behavior_summary": behavior_meta,
        "events": events,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {path} ({payload['total_events']} events)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build orthopedic test ledger from frame analyses.")
    parser.add_argument("--frames", type=Path, default=DEFAULT_FRAMES)
    parser.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    parser.add_argument("--behavior", type=Path, default=DEFAULT_BEHAVIOR)
    parser.add_argument("--case-id", default="osborn_2021_03")
    parser.add_argument("--sample-out", type=Path, default=DEFAULT_SAMPLE_OUT)
    parser.add_argument("--fixture-out", type=Path, default=DEFAULT_FIXTURE_OUT)
    parser.add_argument("--session-out", type=Path, default=None, help="Optional path for session bundle copy")
    args = parser.parse_args()

    ledger = build_ledger(
        frames_path=args.frames,
        claims_path=args.claims,
        behavior_path=args.behavior,
        case_id=args.case_id,
    )

    write_json(args.sample_out, ledger)
    write_json(args.fixture_out, ledger)

    if args.session_out:
        write_json(args.session_out, ledger)

    print(
        f"Summary: {ledger['total_events']} events "
        f"({ledger['observed_event_count']} observed, "
        f"{ledger['claimed_only_count']} claim-only, "
        f"{ledger['observed_not_reported_count']} done-but-not-reported)"
    )


if __name__ == "__main__":
    main()
