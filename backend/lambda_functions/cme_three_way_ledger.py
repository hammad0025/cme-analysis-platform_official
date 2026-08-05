"""
Three-way reconciliation: report claims ↔ named video tests (Hunter rules).

Outputs deposition-ready rows including performed_not_reported when video
shows a named test but the written report is silent on it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cme_named_test_index import NAMED_TEST_SPECS, PLANE_LABELS, extract_named_tests

# Named tests explicitly covered by atomic claim IDs (report mentions them).
CLAIM_COVERS_NAMED: dict[str, set[str]] = {
    "cervical_rom": {"cervical_rom"},
    "rom": {"cervical_rom"},
    "long_tract_signs": {"hoffmann_sign", "babinski_sign"},
    "romberg": {"romberg_test"},
    "gait": {"romberg_test"},  # tandem gait claim may overlap balance testing
}

DEPOSITION_PROMPTS: dict[str, str] = {
    "hoffmann_sign": "Doctor, Hoffmann sign testing appears on the deposition video — identify the timestamp and describe your technique.",
    "babinski_sign": "Doctor, plantar/Babinski testing appears on the deposition video — identify the timestamp and describe your technique.",
    "romberg_test": "Doctor, Romberg or balance testing appears on the deposition video but your report wording may not match what was performed — identify the timestamp.",
    "cervical_rom": "Doctor, cervical range of motion appears on video — identify each plane you measured and whether inclinometer/goniometer was used.",
}


def _load_atomic_claims(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    claims = data.get("claims") if isinstance(data, dict) else data
    if not isinstance(claims, list):
        return {}
    return {str(c["claim_id"]): c for c in claims if isinstance(c, dict) and c.get("claim_id")}


def _claim_covers_named(claim_ids_in_report: set[str], named_key: str) -> bool:
    for cid in claim_ids_in_report:
        covered = CLAIM_COVERS_NAMED.get(cid, set())
        if named_key in covered:
            return True
    return False


def _aggregate_by_named_test(tests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse multiple frame hits into one row per (named_test_key, plane)."""
    merged: dict[tuple[str, str | None], dict[str, Any]] = {}
    for t in tests:
        key = (t["named_test_key"], t.get("plane"))
        if key not in merged:
            merged[key] = {**t, "frame_ids": [t.get("frame_id")], "timestamps_sec": [t["timestamp_sec"]]}
        else:
            row = merged[key]
            row["timestamps_sec"].append(t["timestamp_sec"])
            if t.get("frame_id"):
                row["frame_ids"].append(t["frame_id"])
            row["timestamp_sec"] = min(row["timestamps_sec"])
            row["end_sec"] = max(row["timestamps_sec"])
            issues = set(row.get("technique_issues") or []) | set(t.get("technique_issues") or [])
            row["technique_issues"] = sorted(issues)
            notes = list(row.get("technique_notes") or [])
            for n in t.get("technique_notes") or []:
                if n and n not in notes:
                    notes.append(n)
            row["technique_notes"] = notes[:5]
            # Weakest confidence wins for conservative technique verdict
            order = {"weak": 0, "inferred": 1, "explicit": 2}
            if order.get(t.get("detection_confidence", ""), 1) < order.get(
                row.get("detection_confidence", ""), 1
            ):
                row["detection_confidence"] = t["detection_confidence"]
                row["detection_note"] = t["detection_note"]
    for row in merged.values():
        stamps = sorted(set(row.pop("timestamps_sec", [])))
        row["timestamp_sec"] = stamps[0] if stamps else row.get("timestamp_sec")
        row["end_sec"] = stamps[-1] if len(stamps) > 1 else row.get("timestamp_sec")
        row["frame_count"] = len(row.get("frame_ids") or [])
    return sorted(merged.values(), key=lambda r: (r["named_test_key"], r.get("plane") or "", r["timestamp_sec"]))


def _three_way_status(*, claimed: bool, observed: bool, technique_verdict: str) -> str:
    if claimed and observed:
        if technique_verdict in ("improper", "modified"):
            return "performed_incorrectly"
        return "claimed_and_observed"
    if claimed and not observed:
        return "claimed_not_shown"
    if not claimed and observed:
        return "performed_not_reported"
    return "neither"


def build_three_way_ledger(
    frames: list[Any],
    *,
    atomic_claims_path: Path | None = None,
    case_id: str = "osborn_2021_03",
) -> dict[str, Any]:
    atomic_by_id = _load_atomic_claims(atomic_claims_path)
    claim_ids_in_report = set(atomic_by_id.keys())

    raw_tests = extract_named_tests(frames)
    aggregated = _aggregate_by_named_test(raw_tests)

    rows: list[dict[str, Any]] = []
    for t in aggregated:
        named_key = t["named_test_key"]
        claimed = _claim_covers_named(claim_ids_in_report, named_key)
        observed = True
        status = _three_way_status(
            claimed=claimed,
            observed=observed,
            technique_verdict=t.get("technique_verdict") or "inconclusive",
        )

        matching_claim_id = None
        for cid, covered in CLAIM_COVERS_NAMED.items():
            if named_key in covered and cid in claim_ids_in_report:
                matching_claim_id = cid
                break

        atomic = atomic_by_id.get(matching_claim_id or "", {})
        plane_suffix = ""
        if t.get("plane"):
            plane_suffix = f" ({PLANE_LABELS.get(t['plane'], t['plane'])})"

        deposition_prompt = DEPOSITION_PROMPTS.get(named_key, "")
        if status == "performed_not_reported":
            deposition_prompt = (
                f"Doctor, {t['test_name']}{plane_suffix} appears on the deposition video "
                f"at {t['timestamp_sec']}s but is not documented in your written report — explain."
            )
        elif atomic.get("deposition_prompt") and status in ("claimed_and_observed", "performed_incorrectly"):
            deposition_prompt = atomic["deposition_prompt"]
            if t.get("plane"):
                deposition_prompt += f" Specifically identify {PLANE_LABELS.get(t['plane'], t['plane'])} on video."

        rows.append(
            {
                "test_name": t["test_name"] + plane_suffix,
                "named_test_key": named_key,
                "body_region": t.get("body_region"),
                "plane": t.get("plane"),
                "plane_label": t.get("plane_label"),
                "timestamp_sec": t.get("timestamp_sec"),
                "end_sec": t.get("end_sec"),
                "frame_ids": t.get("frame_ids") or [],
                "frame_count": t.get("frame_count", 0),
                "detection_confidence": t.get("detection_confidence"),
                "detection_note": t.get("detection_note"),
                "technique_issues": t.get("technique_issues") or [],
                "technique_notes": t.get("technique_notes") or [],
                "technique_verdict": t.get("technique_verdict"),
                "visibility": t.get("visibility"),
                "claimed_in_report": claimed,
                "observed_on_video": observed,
                "three_way_status": status,
                "matching_claim_id": matching_claim_id,
                "report_quote": atomic.get("report_quote"),
                "report_page": atomic.get("report_page"),
                "deposition_prompt": deposition_prompt,
            }
        )

    # Claim-only rows: report mentions test category but no named detection on video
    detected_keys = {r["named_test_key"] for r in rows}
    for cid, atomic in atomic_by_id.items():
        for named_key in CLAIM_COVERS_NAMED.get(cid, set()):
            if named_key in detected_keys:
                continue
            spec = NAMED_TEST_SPECS.get(named_key, {})
            rows.append(
                {
                    "test_name": spec.get("display_name", named_key.replace("_", " ").title()),
                    "named_test_key": named_key,
                    "body_region": spec.get("body_region"),
                    "plane": None,
                    "plane_label": None,
                    "timestamp_sec": None,
                    "end_sec": None,
                    "frame_ids": [],
                    "frame_count": 0,
                    "detection_confidence": None,
                    "detection_note": "No named test detection on video",
                    "technique_issues": [],
                    "technique_notes": [],
                    "technique_verdict": "not_shown",
                    "visibility": "not_shown",
                    "claimed_in_report": True,
                    "observed_on_video": False,
                    "three_way_status": "claimed_not_shown",
                    "matching_claim_id": cid,
                    "report_quote": atomic.get("report_quote"),
                    "report_page": atomic.get("report_page"),
                    "deposition_prompt": atomic.get("deposition_prompt"),
                }
            )

    rows.sort(
        key=lambda r: (
            0 if r["three_way_status"] == "performed_not_reported" else 1,
            0 if r["three_way_status"] == "claimed_not_shown" else 1,
            r.get("timestamp_sec") is None,
            r.get("timestamp_sec") or 0,
            r["test_name"],
        )
    )

    status_counts: dict[str, int] = {}
    for r in rows:
        s = r["three_way_status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "schema_version": "1.0.0",
        "case_id": case_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_rows": len(rows),
        "performed_not_reported_count": status_counts.get("performed_not_reported", 0),
        "claimed_not_shown_count": status_counts.get("claimed_not_shown", 0),
        "claimed_and_observed_count": status_counts.get("claimed_and_observed", 0),
        "performed_incorrectly_count": status_counts.get("performed_incorrectly", 0),
        "status_counts": status_counts,
        "rows": rows,
    }
