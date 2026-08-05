"""
Extract named orthopedic/neurologic tests from half-second frame analyses.

Uses Hunter methodology + exam knowledge base detection keywords and
cme_evidence_quality gates — no vision API calls.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .cme_evidence_quality import (
    _fa_field,
    _frame_combined_exam_text,
    _matches,
    frame_passes_quality_gates,
    notes_indicate_broll,
)
from .cme_exam_knowledge_base import EXAMINATION_KNOWLEDGE_BASE, get_exam_by_name
from .cme_hunter_methodology import TEST_PERFORMANCE_INDICATORS

MAX_GAP_SEC = 12.0
MIN_EVENT_FRAMES = 2

CERVICAL_PLANES = (
    "flexion",
    "extension",
    "left_lateral_flexion",
    "right_lateral_flexion",
    "left_rotation",
    "right_rotation",
)

PLANE_LABELS = {
    "flexion": "Flexion",
    "extension": "Extension",
    "left_lateral_flexion": "Left lateral flexion",
    "right_lateral_flexion": "Right lateral flexion",
    "left_rotation": "Left rotation",
    "right_rotation": "Right rotation",
}

PLANE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("flexion", ("chin to chest", "head forward", "bending head/neck forward", "bend neck forward", "flexion")),
    ("extension", ("looking up", "head tilted back", "look up", "extension", "tilt back")),
    (
        "left_lateral_flexion",
        ("tilt left", "ear to shoulder left", "side bend left", "lateral flexion left", "sidebending left"),
    ),
    (
        "right_lateral_flexion",
        ("tilt right", "ear to shoulder right", "side bend right", "lateral flexion right", "sidebending right"),
    ),
    ("left_rotation", ("turn left", "rotate left", "look left", "look over left", "rotation left")),
    ("right_rotation", ("turn right", "rotate right", "look right", "look over right", "rotation right")),
]

NAMED_TEST_SPECS: dict[str, dict[str, Any]] = {
    "hoffmann_sign": {
        "display_name": "Hoffmann sign",
        "kb_key": "hoffmanns_sign",
        "hunter_key": None,
        "body_region": "hand",
        "claim_ids": ("long_tract_signs",),
    },
    "babinski_sign": {
        "display_name": "Babinski sign",
        "kb_key": "babinski_sign",
        "hunter_key": None,
        "body_region": "foot",
        "claim_ids": ("long_tract_signs",),
    },
    "romberg_test": {
        "display_name": "Romberg test",
        "kb_key": "romberg_test",
        "hunter_key": "romberg_test",
        "body_region": "full_body",
        "claim_ids": ("romberg",),
    },
    "cervical_rom": {
        "display_name": "Cervical range of motion",
        "kb_key": "cervical_rom",
        "hunter_key": "cervical_rom",
        "body_region": "neck",
        "claim_ids": ("cervical_rom", "rom"),
    },
}


def _frame_text(fa: Any) -> str:
    return _frame_combined_exam_text(fa).lower()


def _frame_passes(fa: Any, claim_id: str = "") -> bool:
    if notes_indicate_broll(_fa_field(fa, "notes")):
        return False
    return frame_passes_quality_gates(fa, claim_id or "exam", "")


def _infer_cervical_plane(text: str) -> str | None:
    for plane, patterns in PLANE_PATTERNS:
        if _matches(text, patterns):
            return plane
    if "neck" in text and "range of motion" in text:
        return "flexion"  # generic cervical ROM when plane unspecified
    return None


def _kb_keywords(kb_key: str) -> list[str]:
    exam = get_exam_by_name(kb_key)
    keys: list[str] = []
    planes = exam.get("six_planes_detection") or {}
    for spec in planes.values():
        keys.extend(spec.get("detection_keywords") or [])
    for indicator in exam.get("visual_indicators") or []:
        keys.append(str(indicator).replace("_", " "))
    methodology = exam.get("methodology") or {}
    for step in methodology.get("steps") or []:
        keys.append(str(step).lower())
    return keys


def _matches_hoffmann(fa: Any) -> tuple[bool, str, str]:
    text = _frame_text(fa)
    tt = _fa_field(fa, "test_type").lower()
    br = _fa_field(fa, "body_region").lower()
    if _matches(text, ("hoffmann", "hoffman", "middle finger", "flick", "thumb flex")):
        return True, "explicit", "Keyword match for Hoffmann sign"
    if tt in ("hoffmann", "hoffmanns") or "hoffmann" in tt:
        return True, "explicit", f"Frame test_type={tt}"
    if tt in ("strength", "reflex", "reflexes") and br in ("hand", "arm"):
        if _matches(text, ("middle finger", "flick", "pathological", "hoffmann")):
            return True, "inferred", "Finger flick consistent with Hoffmann sign"
    return False, "", ""


def _matches_babinski(fa: Any) -> tuple[bool, str, str]:
    text = _frame_text(fa)
    tt = _fa_field(fa, "test_type").lower()
    br = _fa_field(fa, "body_region").lower()
    if _matches(text, ("babinski", "plantar response", "plantar reflex", "upgoing", "great toe", "sole strok")):
        return True, "explicit", "Keyword match for Babinski / plantar response"
    if tt in ("babinski",) or "babinski" in tt:
        return True, "explicit", f"Frame test_type={tt}"
    if tt in ("reflex", "reflexes") and br in ("foot", "leg"):
        if _matches(text, ("plantar", "babinski", "sole", "toe")):
            return True, "inferred", "Plantar/reflex testing on lower extremity"
    return False, "", ""


def _matches_romberg(fa: Any) -> tuple[bool, str, str]:
    text = _frame_text(fa)
    tt = _fa_field(fa, "test_type").lower()
    if tt in ("romberg", "rhomberg"):
        return True, "explicit", f"Frame test_type={tt}"
    if _matches(text, ("romberg", "rhomberg", "feet together", "eyes closed", "balance test")):
        return True, "explicit", "Keyword match for Romberg test"
    if tt == "gait" and _matches(text, ("feet together", "eyes closed", "standing still", "balance")):
        return True, "inferred", "Stationary balance observation during gait assessment"
    if tt == "gait" and _matches(text, ("standing", "hallway")) and "walking" not in text:
        return True, "weak", "Patient standing during gait segment — Romberg technique not confirmed"
    return False, "", ""


def _matches_cervical_rom(fa: Any) -> tuple[bool, str, str, str | None]:
    text = _frame_text(fa)
    tt = _fa_field(fa, "test_type").lower()
    br = _fa_field(fa, "body_region").lower()
    plane = _infer_cervical_plane(text)
    if tt == "cervical_rom" or "cervical_rom" in tt:
        return True, "explicit", "Frame tagged cervical ROM", plane
    if tt == "rom" and br in ("neck", "cervical", "cervical_spine"):
        return True, "explicit", "Neck ROM frame", plane or "flexion"
    if tt == "rom" and _matches(text, ("cervical", "neck")):
        return True, "inferred", "ROM activity involving neck/cervical spine", plane or "flexion"
    if plane and ("neck" in text or "cervical" in text):
        return True, "inferred", f"Cervical movement cue: {PLANE_LABELS.get(plane, plane)}", plane
    return False, "", "", None


MATCHERS: dict[str, Callable[[Any], tuple]] = {
    "hoffmann_sign": _matches_hoffmann,
    "babinski_sign": _matches_babinski,
    "romberg_test": _matches_romberg,
}


def _cluster_frames(
    frames: list[Any],
    *,
    test_types: set[str],
    body_regions: set[str],
    named_key: str,
    display_name: str,
    body_region: str,
    confidence: str,
    note: str,
    claim_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Group category-level frames into named-test events (Hunter inference path)."""
    candidates = []
    for fa in frames:
        if not _frame_passes(fa):
            continue
        tt = _fa_field(fa, "test_type").lower()
        br = _fa_field(fa, "body_region").lower()
        if tt not in test_types:
            continue
        if body_regions and br not in body_regions and br not in ("none", "unknown"):
            continue
        ts = float(_fa_field(fa, "timestamp_sec") or 0)
        candidates.append(
            {
                "test_name": display_name,
                "named_test_key": named_key,
                "body_region": body_region,
                "plane": None,
                "plane_label": None,
                "timestamp_sec": round(ts, 1),
                "frame_id": _fa_field(fa, "frame_id"),
                "detection_confidence": confidence,
                "detection_note": note,
                "technique_issues": [str(i) for i in (fa.get("technique_issues") if isinstance(fa, dict) else getattr(fa, "technique_issues", None) or [])],
                "technique_notes": [(_fa_field(fa, "test_details") or _fa_field(fa, "notes"))[:240]],
                "visibility": _fa_field(fa, "visibility") or "unknown",
                "technique_verdict": "inconclusive",
                "claim_ids": list(claim_ids),
                "kb_reference": get_exam_by_name(NAMED_TEST_SPECS[named_key]["kb_key"]).get("reference"),
            }
        )
    return _collapse_events(candidates)


def _infer_missing_named_tests(frames: list[Any], explicit_keys: set[str]) -> list[dict[str, Any]]:
    """Hunter-style inference when vision labels category blobs only."""
    inferred: list[dict[str, Any]] = []
    if "hoffmann_sign" not in explicit_keys:
        inferred.extend(
            _cluster_frames(
                frames,
                test_types={"strength", "sensory"},
                body_regions={"hand", "arm"},
                named_key="hoffmann_sign",
                display_name="Hoffmann sign",
                body_region="hand",
                confidence="inferred",
                note="UE hand/arm testing cluster — vision did not label Hoffmann; deposition should confirm flick technique",
                claim_ids=NAMED_TEST_SPECS["hoffmann_sign"]["claim_ids"],
            )
        )
    if "babinski_sign" not in explicit_keys:
        inferred.extend(
            _cluster_frames(
                frames,
                test_types={"sensory", "reflex", "reflexes", "strength"},
                body_regions={"foot", "leg"},
                named_key="babinski_sign",
                display_name="Babinski sign",
                body_region="foot",
                confidence="inferred",
                note="LE foot/leg testing cluster — plantar response not explicitly labeled on video",
                claim_ids=NAMED_TEST_SPECS["babinski_sign"]["claim_ids"],
            )
        )
    if "romberg_test" not in explicit_keys:
        inferred.extend(
            _cluster_frames(
                frames,
                test_types={"gait", "romberg", "rhomberg"},
                body_regions=set(),
                named_key="romberg_test",
                display_name="Romberg test",
                body_region="full_body",
                confidence="weak",
                note="Hallway gait/balance segment — classic Romberg (feet together, eyes closed) not confirmed on video",
                claim_ids=NAMED_TEST_SPECS["romberg_test"]["claim_ids"],
            )
        )
    return inferred


def _hunter_technique_notes(test_key: str, technique_issues: list[str]) -> list[str]:
    hunter_key = NAMED_TEST_SPECS[test_key].get("hunter_key")
    if not hunter_key:
        return []
    spec = TEST_PERFORMANCE_INDICATORS.get(hunter_key) or {}
    notes: list[str] = []
    proper = spec.get("proper_technique")
    if proper:
        notes.append(f"Proper technique (Hunter): {proper}")
    for err in spec.get("common_errors") or []:
        if any(err.lower().replace(" ", "_") in i for i in technique_issues):
            notes.append(f"Technique issue: {err}")
    return notes[:3]


def _technique_verdict(
    *,
    observed: bool,
    technique_issues: list[str],
    visibility: str,
    detection_confidence: str,
) -> str:
    if not observed:
        return "not_shown"
    if detection_confidence == "weak":
        return "inconclusive"
    vis = (visibility or "").lower()
    if vis in ("obscured", "partial", "poor"):
        return "inconclusive"
    modified = {"testing_through_clothing", "patient_not_in_gown", "testing_in_street_shoes", "no_gown"}
    if technique_issues:
        if any(i in modified for i in technique_issues):
            return "modified"
        return "improper"
    return "proper"


def _collapse_events(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group half-second frame hits into short events (min 2 frames)."""
    if not raw_rows:
        return []
    sorted_rows = sorted(raw_rows, key=lambda r: r["timestamp_sec"])
    events: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def finalize(row: dict[str, Any]) -> dict[str, Any] | None:
        min_frames = 1 if row.get("detection_confidence") == "explicit" else MIN_EVENT_FRAMES
        if (row.get("frame_count") or 0) >= min_frames:
            return row
        return None

    for row in sorted_rows:
        key = (row["named_test_key"], row.get("plane"))
        if (
            current
            and (current["named_test_key"], current.get("plane")) == key
            and row["timestamp_sec"] - current["end_sec"] <= MAX_GAP_SEC
        ):
            current["end_sec"] = row["timestamp_sec"]
            current["frame_ids"].append(row.get("frame_id"))
            current["frame_count"] = len(current["frame_ids"])
            current["technique_issues"] = sorted(
                set(current.get("technique_issues") or []) | set(row.get("technique_issues") or [])
            )
            notes = list(current.get("technique_notes") or [])
            for n in row.get("technique_notes") or []:
                if n and n not in notes:
                    notes.append(n)
            current["technique_notes"] = notes[:5]
        else:
            if current:
                done = finalize(current)
                if done:
                    events.append(done)
            current = {
                **row,
                "end_sec": row["timestamp_sec"],
                "frame_ids": [row.get("frame_id")] if row.get("frame_id") else [],
                "frame_count": 1,
            }
    if current:
        done = finalize(current)
        if done:
            events.append(done)
    return events


def extract_named_tests(frames: list[Any]) -> list[dict[str, Any]]:
    """Return one row per detected named test (including cervical ROM planes)."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str]] = set()

    for fa in frames:
        if not _frame_passes(fa):
            continue
        ts = float(_fa_field(fa, "timestamp_sec") or 0)
        frame_id = _fa_field(fa, "frame_id")
        visibility = _fa_field(fa, "visibility") or "unknown"
        issues = [str(i) for i in (fa.get("technique_issues") if isinstance(fa, dict) else getattr(fa, "technique_issues", None) or [])]
        details = _fa_field(fa, "test_details") or _fa_field(fa, "notes")

        # Cervical ROM — one row per plane when inferrable
        ok, conf, note, plane = _matches_cervical_rom(fa)
        if ok:
            dedupe_key = ("cervical_rom", plane, frame_id)
            if dedupe_key not in seen:
                seen.add(dedupe_key)
                spec = NAMED_TEST_SPECS["cervical_rom"]
                kb = get_exam_by_name(spec["kb_key"])
                rows.append(
                    {
                        "test_name": spec["display_name"],
                        "named_test_key": "cervical_rom",
                        "body_region": "neck",
                        "plane": plane,
                        "plane_label": PLANE_LABELS.get(plane or "", plane or "Unspecified plane"),
                        "timestamp_sec": round(ts, 1),
                        "frame_id": frame_id,
                        "detection_confidence": conf,
                        "detection_note": note,
                        "technique_issues": issues,
                        "technique_notes": _hunter_technique_notes("cervical_rom", issues)
                        + ([details[:240]] if details else []),
                        "visibility": visibility,
                        "technique_verdict": _technique_verdict(
                            observed=True,
                            technique_issues=issues,
                            visibility=visibility,
                            detection_confidence=conf,
                        ),
                        "claim_ids": list(spec["claim_ids"]),
                        "kb_reference": kb.get("reference"),
                    }
                )

        for test_key, matcher in MATCHERS.items():
            result = matcher(fa)
            ok = result[0]
            if not ok:
                continue
            conf, note = result[1], result[2]
            dedupe_key = (test_key, None, frame_id)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            spec = NAMED_TEST_SPECS[test_key]
            kb = get_exam_by_name(spec["kb_key"])
            rows.append(
                {
                    "test_name": spec["display_name"],
                    "named_test_key": test_key,
                    "body_region": spec["body_region"],
                    "plane": None,
                    "plane_label": None,
                    "timestamp_sec": round(ts, 1),
                    "frame_id": frame_id,
                    "detection_confidence": conf,
                    "detection_note": note,
                    "technique_issues": issues,
                    "technique_notes": _hunter_technique_notes(test_key, issues)
                    + ([details[:240]] if details else []),
                    "visibility": visibility,
                    "technique_verdict": _technique_verdict(
                        observed=True,
                        technique_issues=issues,
                        visibility=visibility,
                        detection_confidence=conf,
                    ),
                    "claim_ids": list(spec["claim_ids"]),
                    "kb_reference": kb.get("reference"),
                }
            )

    rows.sort(key=lambda r: (r["named_test_key"], r.get("plane") or "", r["timestamp_sec"]))
    collapsed = _collapse_events(rows)
    explicit_keys = {r["named_test_key"] for r in collapsed}
    inferred = _infer_missing_named_tests(frames, explicit_keys)
    merged = collapsed + [r for r in inferred if r["named_test_key"] not in explicit_keys]
    merged.sort(key=lambda r: (r["named_test_key"], r.get("plane") or "", r["timestamp_sec"]))
    return merged


def build_named_test_index(
    frames: list[Any],
    *,
    case_id: str = "osborn_2021_03",
    source_path: str = "",
) -> dict[str, Any]:
    tests = extract_named_tests(frames)
    by_key: dict[str, int] = {}
    for t in tests:
        key = t["named_test_key"]
        if t.get("plane"):
            key = f"{key}:{t['plane']}"
        by_key[key] = by_key.get(key, 0) + 1

    return {
        "schema_version": "1.0.0",
        "case_id": case_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_frames_path": source_path,
        "total_detections": len(tests),
        "detection_counts": by_key,
        "tests": tests,
    }
