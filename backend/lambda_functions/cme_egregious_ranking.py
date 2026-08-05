"""Aggressive issue ranking for Main Issues Identified (trial-lawyer focus).

Also home of the cross-examination materiality gate: the single inclusion
test for report findings is "does this contradict or undercut a specific
claim the doctor made in his written report, provable by timestamped
video/audio evidence?". Administrative noise (name spellings, transcription
artifacts) and demeanor-only complaints are hard-banned here so they can
never reach a generated report regardless of what upstream models emit.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .cme_analysis_utils import is_metadata_claim_id
from .cme_evidence_quality import is_physical_exam_claim

ISSUE_TYPE_LABELS: Dict[str, str] = {
    "contradiction": "CONTRADICTION",
    "rom_gap": "ROM GAP",
    "not_shown": "NOT SHOWN ON VIDEO",
    "performed_not_reported": "DONE BUT NOT IN REPORT",
    "technique_gap": "TECHNIQUE GAP",
}

LOW_PRIORITY_CLAIM_IDS = frozenset(
    {
        "general_appearance",
        "mental_status",
    }
)

_DEGREE_RE = re.compile(r"\d+\s*(?:°|degrees?)", re.I)
_GONIOMETER_GAP_RE = re.compile(
    r"no\s+goniometer|without\s+(?:visible\s+)?goniometer|not\s+visible.*goniometer|street\s+clothes|wheelchair",
    re.I,
)

# Administrative / transcription noise that must NEVER surface as a finding.
# The user-facing rule: nothing about names, spellings, transcription
# artifacts, scheduling, paperwork, or recording quality is a finding.
_BANNED_NOISE_RE = re.compile(
    r"\b(?:"
    r"name\s+(?:was\s+)?(?:recorded|spelled|misspelled|mispronounced|stated)"
    r"|misspell\w*|spelling|mispronunc\w*|pronunciation"
    r"|transcription\s+(?:error|artifact|issue|quality)"
    r"|transcript\s+(?:error|artifact)"
    r"|audio\s+quality|recording\s+quality|inaudible"
    r"|recorded\s+improperly"
    r"|paperwork|scheduling|check[- ]?in|consent\s+form"
    r"|introduc(?:ed|tion|ing)\s+(?:himself|herself|themselves)"
    r"|small\s+talk|greeting"
    r")\b",
    re.I,
)

# Demeanor / tone vocabulary. A finding whose ONLY substance is bedside
# manner is banned unless it also carries exam substance (a specific test,
# measurement, duration, or clothing/technique issue).
_DEMEANOR_ONLY_RE = re.compile(
    r"\b(?:rude|dismissive|condescending|impatient|unprofessional|cold|curt|"
    r"not\s+nice|bedside\s+manner|tone|demeanor|attitude|empath\w*|rapport)\b",
    re.I,
)
_EXAM_SUBSTANCE_RE = re.compile(
    r"\b(?:test(?:s|ing)?|rom|range\s+of\s+motion|goniometer|inclinometer|strength|"
    r"reflex\w*|sensor\w*|sensation|gait|romberg|babinski|hoffmann|palpat\w*|"
    r"cranial|coordination|straight[- ]leg|spurling|neer|lachman|mcmurray|"
    r"duration|minute?s|measure\w*|clothing|clothes|gown|exam(?:ination)?\s+window|"
    r"maneuver|plane(?:s)?\s+of\s+motion|instrument)\b",
    re.I,
)

_DEMEANOR_CLAIM_IDS = frozenset(
    {
        "demeanor",
        "tone",
        "bedside_manner",
        "professionalism",
        "empathy",
        "attitude",
        "rapport",
        "behavior",
    }
)


def _claim_id(row: Dict[str, Any]) -> str:
    return str(row.get("claim_id") or "").strip().lower()


def _verdict(row: Dict[str, Any]) -> str:
    return str(row.get("verdict") or "insufficient_evidence").strip().lower()


def _confidence(row: Dict[str, Any]) -> float:
    try:
        return float(row.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _combined_text(row: Dict[str, Any]) -> str:
    ce = row.get("cross_examination") or {}
    parts = [
        row.get("report_quote"),
        row.get("claim_text"),
        row.get("video_shows"),
        row.get("reasoning"),
        ce.get("video_finding"),
        ce.get("leading_question"),
    ]
    for ev in row.get("evidence") or []:
        if isinstance(ev, dict):
            parts.append(ev.get("notes"))
            parts.append(ev.get("quote"))
    return " ".join(str(p) for p in parts if p)


def is_rom_claim(row: Dict[str, Any]) -> bool:
    cid = _claim_id(row)
    if cid.startswith("rom_") or "_rom" in cid:
        return True
    text = _combined_text(row).lower()
    return "range of motion" in text or "flexion contracture" in text


def has_degree_measurements(row: Dict[str, Any]) -> bool:
    return bool(_DEGREE_RE.search(_combined_text(row)))


def lacks_goniometer_on_video(row: Dict[str, Any]) -> bool:
    return bool(_GONIOMETER_GAP_RE.search(_combined_text(row)))


def classify_issue_type(row: Dict[str, Any]) -> str:
    verdict = _verdict(row)
    if verdict == "performed_not_reported":
        return "performed_not_reported"
    if verdict == "contradicted":
        return "contradiction"
    if is_rom_claim(row) and verdict == "partially_supported":
        return "rom_gap"
    if verdict == "not_shown":
        return "not_shown"
    if verdict == "partially_supported":
        return "technique_gap"
    return "technique_gap"


def issue_type_label(row: Dict[str, Any]) -> str:
    return ISSUE_TYPE_LABELS.get(classify_issue_type(row), "TECHNIQUE GAP")


def is_low_priority(row: Dict[str, Any]) -> bool:
    if is_metadata_claim_id(_claim_id(row)):
        return True
    cid = _claim_id(row)
    verdict = _verdict(row)
    if cid in LOW_PRIORITY_CLAIM_IDS:
        if verdict != "contradicted":
            return True
    if verdict == "supported":
        return True
    return False


def is_banned_noise(row: Dict[str, Any]) -> bool:
    """True when the finding is administrative/transcription noise or a
    demeanor-only complaint — content that is banned from reports."""
    text = _combined_text(row)
    if _BANNED_NOISE_RE.search(text):
        return True
    cid = _claim_id(row)
    if cid in _DEMEANOR_CLAIM_IDS or any(cid.startswith(f"{d}_") for d in _DEMEANOR_CLAIM_IDS):
        return True
    if _DEMEANOR_ONLY_RE.search(text) and not _EXAM_SUBSTANCE_RE.search(text):
        return True
    return False


def _has_report_claim(row: Dict[str, Any]) -> bool:
    return bool(str(row.get("report_quote") or row.get("claim_text") or "").strip())


def _has_timestamped_evidence(row: Dict[str, Any]) -> bool:
    for ev in row.get("evidence") or []:
        if isinstance(ev, dict) and isinstance(ev.get("timestamp_sec"), (int, float)):
            return True
    ce = row.get("cross_examination") or {}
    for t in ce.get("timestamps") or []:
        if isinstance(t, dict) and isinstance(t.get("sec"), (int, float)):
            return True
    return False


_IMPEACHING_VERDICTS = frozenset(
    {"contradicted", "not_shown", "partially_supported", "performed_not_reported"}
)


def passes_materiality_gate(row: Dict[str, Any]) -> bool:
    """The single inclusion test for report findings.

    A finding qualifies only when it (a) targets a specific claim in the
    doctor's written report, (b) carries an impeaching verdict backed by
    video/audio review, and (c) is not administrative/transcription noise
    or a demeanor-only complaint. `not_shown` findings are exempt from the
    timestamp requirement because their evidentiary value is the absence
    across the whole reviewed video (the exam window is cited instead)."""
    if is_low_priority(row) or is_banned_noise(row):
        return False
    if not _has_report_claim(row):
        return False
    verdict = _verdict(row)
    if verdict not in _IMPEACHING_VERDICTS:
        return False
    if verdict != "not_shown" and not _has_timestamped_evidence(row):
        return False
    return True


def compute_egregious_score(row: Dict[str, Any]) -> float:
    if is_low_priority(row) or is_banned_noise(row):
        return 0.0

    verdict = _verdict(row)
    conf = _confidence(row)
    cid = _claim_id(row)

    if verdict == "contradicted":
        bonus = 12.0 if "strength" in cid else 8.0
        return 100.0 + conf * 10.0 + bonus

    # Test claimed in the report but never performed on video: a top-tier
    # impeachment point (report says it happened; the video says it didn't).
    if verdict == "not_shown" and is_physical_exam_claim(cid, str(row.get("claim_text") or "")):
        return 80.0 + conf * 10.0

    if verdict == "performed_not_reported":
        return 76.0 + conf * 8.0

    if is_rom_claim(row) and verdict == "partially_supported" and has_degree_measurements(row):
        score = 68.0 + conf * 8.0
        if lacks_goniometer_on_video(row):
            score += 8.0
        return score

    if verdict == "partially_supported" and conf >= 0.55:
        return 55.0 + conf * 15.0

    if verdict == "not_shown" and any(
        k in cid for k in ("inspection", "palpation", "strength", "sensation", "vascular", "feet")
    ):
        return 35.0 + conf * 5.0

    return 0.0


def issue_punch_line(row: Dict[str, Any]) -> str:
    ce = row.get("cross_examination") or {}
    report = str(row.get("report_quote") or row.get("claim_text") or "").strip()
    if len(report) > 120:
        report = report[:117].rstrip() + "…"
    video = str(
        ce.get("video_finding")
        or row.get("video_shows")
        or row.get("reasoning")
        or "Not documented on video."
    ).strip()
    if len(video) > 140:
        video = video[:137].rstrip() + "…"
    return f'Report: "{report}" — Video: {video}'


def why_it_matters(row: Dict[str, Any]) -> str:
    issue = classify_issue_type(row)
    test = str(row.get("test_name") or _claim_id(row).replace("_", " ")).strip()
    if issue == "contradiction":
        return (
            f"A contradicted {test} finding undermines the defense doctor's credibility "
            "and gives plaintiff counsel a concrete impeachment point at deposition."
        )
    if issue == "performed_not_reported":
        return (
            f"{test} was performed on camera but omitted from the written report — "
            "the record is incomplete and favorable findings may have been left out."
        )
    if issue == "rom_gap":
        return (
            "Degree-specific ROM in the report cannot be verified on video without proper "
            "goniometer technique — a core Hunter methodology attack at trial."
        )
    if issue == "not_shown":
        return (
            f"The report documents {test}, but the deposition video does not show it — "
            "counsel can force the doctor to identify the moment or admit it was not done on camera."
        )
    return (
        f"The video only partially supports the documented {test}; deposition should pin down "
        "exact technique, planes tested, and instruments used."
    )


def three_way_row_to_verdict(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a three_way_ledger performed_not_reported row to a verdict-shaped dict."""
    ts = float(row.get("timestamp_sec") or 0.0)
    test_name = str(row.get("test_name") or row.get("named_test_key") or "Unnamed test")
    claim_id = f"three_way_{row.get('named_test_key') or test_name.lower().replace(' ', '_')}"
    deposition_prompt = str(
        row.get("deposition_prompt")
        or f"Doctor, {test_name} appears on the deposition video at {ts:.0f}s but is not documented in your written report — explain."
    )
    technique_notes = " ".join(str(n) for n in (row.get("technique_notes") or [])[:2])
    return {
        "claim_id": claim_id,
        "test_name": test_name,
        "claim_text": deposition_prompt,
        "report_quote": row.get("report_quote") or "",
        "report_page": row.get("report_page"),
        "verdict": "performed_not_reported",
        "confidence": 0.75,
        "reasoning": technique_notes or row.get("detection_note") or "",
        "video_shows": technique_notes or f"{test_name} observed on video at {ts:.0f}s.",
        "deposition_prompt": deposition_prompt,
        "evidence": [
            {
                "kind": "frame",
                "frame_id": (row.get("frame_ids") or [None])[0],
                "timestamp_sec": ts,
                "notes": technique_notes or f"{test_name} performed on video.",
            }
        ],
        "three_way_status": row.get("three_way_status"),
        "source": "three_way_ledger",
    }


def merge_three_way_issues(
    verdicts: List[Dict[str, Any]],
    three_way_ledger: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out = list(verdicts or [])
    existing_ids = {_claim_id(v) for v in out}
    for row in (three_way_ledger or {}).get("rows") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("three_way_status") or "") != "performed_not_reported":
            continue
        converted = three_way_row_to_verdict(row)
        if _claim_id(converted) in existing_ids:
            continue
        out.append(converted)
        existing_ids.add(_claim_id(converted))
    return out


def annotate_egregious_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(row)
    enriched["issue_type"] = classify_issue_type(enriched)
    enriched["issue_type_label"] = issue_type_label(enriched)
    enriched["egregious_score"] = round(compute_egregious_score(enriched), 2)
    enriched["issue_punch_line"] = issue_punch_line(enriched)
    enriched["why_it_matters"] = why_it_matters(enriched)
    enriched["is_main_issue"] = enriched["egregious_score"] >= 50.0
    return enriched


def rank_main_issues(
    verdicts: List[Dict[str, Any]],
    *,
    three_way_ledger: Optional[Dict[str, Any]] = None,
    max_issues: int = 7,
    min_score: float = 50.0,
) -> List[Dict[str, Any]]:
    merged = merge_three_way_issues(verdicts, three_way_ledger)
    candidates = [
        annotate_egregious_fields(v)
        for v in merged
        if not is_metadata_claim_id(_claim_id(v))
    ]
    ranked = sorted(
        [c for c in candidates if c.get("egregious_score", 0) >= min_score],
        key=lambda r: (-float(r.get("egregious_score") or 0), _claim_id(r)),
    )
    return ranked[:max_issues]


def sort_all_findings(
    verdicts: List[Dict[str, Any]],
    *,
    three_way_ledger: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    merged = merge_three_way_issues(verdicts, three_way_ledger)
    annotated = [
        annotate_egregious_fields(v)
        for v in merged
        if not is_metadata_claim_id(_claim_id(v))
    ]
    return sorted(
        annotated,
        key=lambda r: (-float(r.get("egregious_score") or 0), _claim_id(r)),
    )


# ----------------------------------------------------------------------
# Numbered CROSS EXAMINATION findings (litigation-ready report format)
# ----------------------------------------------------------------------


def _fmt_mmss(sec: float) -> str:
    total = max(0, int(sec))
    return f"{total // 60}:{total % 60:02d}"


def _short(text: str, limit: int = 220) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


def _finding_timestamps(row: Dict[str, Any], *, max_stamps: int = 3) -> List[Dict[str, Any]]:
    """Unique sorted timestamps from cross_examination block or evidence."""
    secs: List[float] = []
    ce = row.get("cross_examination") or {}
    for t in ce.get("timestamps") or []:
        if isinstance(t, dict) and isinstance(t.get("sec"), (int, float)):
            secs.append(float(t["sec"]))
    if not secs:
        for ev in row.get("evidence") or []:
            if isinstance(ev, dict) and isinstance(ev.get("timestamp_sec"), (int, float)):
                secs.append(float(ev["timestamp_sec"]))
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for s in sorted(dict.fromkeys(secs)):
        label = _fmt_mmss(s)
        if label in seen:
            continue
        seen.add(label)
        out.append({"sec": s, "label": label})
        if len(out) >= max_stamps:
            break
    return out


def _test_display_name(row: Dict[str, Any]) -> str:
    name = str(row.get("test_name") or "").strip()
    if name:
        return name
    return _claim_id(row).replace("_", " ").strip() or "the documented test"


_PROPER_NOUN_TEST_PREFIXES = (
    "babinski",
    "hoffmann",
    "romberg",
    "spurling",
    "lachman",
    "mcmurray",
    "neer",
    "waddell",
    "tinel",
    "phalen",
)


def _test_name_mid_sentence(test: str) -> str:
    """Lowercase the leading word unless it is a proper-noun test name."""
    if not test:
        return test
    first = test.split(" ", 1)[0].lower().strip("'s")
    if any(first.startswith(p) for p in _PROPER_NOUN_TEST_PREFIXES):
        return test
    return test[0].lower() + test[1:]


def _claim_statement(row: Dict[str, Any]) -> str:
    """'Doctor stated in his report that ...' heading line."""
    verdict = _verdict(row)
    test = _test_display_name(row)
    quote = _short(str(row.get("report_quote") or row.get("claim_text") or ""), limit=160)
    if verdict == "performed_not_reported":
        return f"Doctor's written report omits {test} entirely."
    if verdict == "contradicted" and quote:
        return f'Doctor stated in his report: "{quote}"'
    return f"Doctor stated in his report that he performed {_test_name_mid_sentence(test)}."


def _fact_statement(
    row: Dict[str, Any],
    *,
    exam_window: Optional[Dict[str, Any]] = None,
) -> str:
    """'FACT: ...' rebuttal with an explicit video citation."""
    verdict = _verdict(row)
    test = _test_display_name(row)
    ce = row.get("cross_examination") or {}
    finding = str(
        ce.get("video_finding") or row.get("video_shows") or row.get("reasoning") or ""
    ).strip()
    stamps = _finding_timestamps(row)

    if stamps:
        labels = ", ".join(t["label"] for t in stamps)
        see = f"See {labels} of the video."
    elif exam_window and exam_window.get("start") and exam_window.get("end"):
        see = (
            "See the physical-exam window "
            f"{exam_window['start']}–{exam_window['end']} of the video."
        )
    else:
        see = "See the full examination video."

    if verdict == "not_shown" and not finding:
        finding = (
            f"The examination video was reviewed in full; at no point does it show "
            f"{test} being performed."
        )
    elif verdict == "not_shown":
        finding = _short(finding, 320)
        if not finding.endswith((".", "!", "?")):
            finding += "."
        finding += f" Nowhere on the video is {test} properly performed."
    else:
        finding = _short(finding, 380)

    if not finding:
        finding = "The video does not support the doctor's written claim."
    if not finding.endswith((".", "!", "?")):
        finding += "."
    return f"{finding} {see}"


def _parse_mmss(label: Any) -> Optional[float]:
    m = re.match(r"^\s*(\d+):(\d{2})\s*$", str(label or ""))
    if not m:
        return None
    return float(m.group(1)) * 60 + float(m.group(2))


def build_duration_finding(
    comprehensive_summary: Optional[Dict[str, Any]],
    *,
    exam_window: Optional[Dict[str, Any]] = None,
    max_actual_ratio: float = 0.6,
) -> Optional[Dict[str, Any]]:
    """Synthesize an exam-duration discrepancy finding (a Hunter heavy hitter).

    Fires only when the report claims an exam time and the observed
    hands-on window is materially shorter (< `max_actual_ratio` of the
    claim). Returns a verdict-shaped row or None."""
    cs = comprehensive_summary or {}
    try:
        claimed_min = float(cs.get("claimed_exam_time_min") or 0.0)
        hands_on_sec = float(cs.get("actual_hands_on_exam_sec") or 0.0)
    except (TypeError, ValueError):
        return None
    if claimed_min <= 0 or hands_on_sec <= 0:
        return None
    if hands_on_sec >= claimed_min * 60.0 * max_actual_ratio:
        return None

    ew = exam_window or {}
    start_label = str(ew.get("start") or "")
    end_label = str(ew.get("end") or "")
    start_sec = _parse_mmss(start_label)
    end_sec = _parse_mmss(end_label)
    window_valid = (
        start_sec is not None
        and end_sec is not None
        and end_sec > start_sec
    )
    if not window_valid:
        # Fall back to the full video span so the finding still carries a
        # concrete, citable timestamp range.
        try:
            total_sec = float(cs.get("total_video_duration_sec") or 0.0)
        except (TypeError, ValueError):
            total_sec = 0.0
        if total_sec <= 0:
            return None
        start_sec, end_sec = 0.0, total_sec
        window_txt = f" (full video, 0:00–{_fmt_mmss(total_sec)})"
    else:
        window_txt = f" (exam window {start_label}–{end_label})"

    actual_txt = f"{int(hands_on_sec // 60)} min {int(hands_on_sec % 60)} sec"
    evidence: List[Dict[str, Any]] = [
        {
            "kind": "frame_range",
            "timestamp_sec": start_sec,
            "end_timestamp_sec": end_sec,
            "notes": f"Observed hands-on examination window{window_txt}.",
        },
        {
            "kind": "frame",
            "timestamp_sec": end_sec,
            "notes": "End of observed hands-on examination.",
        },
    ]

    return {
        "claim_id": "exam_duration",
        "test_name": "Examination duration",
        "verdict": "contradicted",
        "confidence": 0.85,
        "report_quote": f"Examination time: {claimed_min:.0f} minutes",
        "claim_text": f"Examination time: {claimed_min:.0f} minutes",
        "video_shows": (
            f"Hands-on examination on video totals only about {actual_txt}"
            f"{window_txt} — a fraction of the {claimed_min:.0f} minutes documented."
        ),
        "reasoning": "Exam duration on video contradicts the duration documented in the report.",
        "evidence": evidence,
        "source": "duration_check",
    }


def build_numbered_cross_examinations(
    verdicts: List[Dict[str, Any]],
    *,
    three_way_ledger: Optional[Dict[str, Any]] = None,
    exam_window: Optional[Dict[str, Any]] = None,
    extra_findings: Optional[List[Dict[str, Any]]] = None,
    max_findings: int = 10,
    min_score: float = 50.0,
) -> List[Dict[str, Any]]:
    """Ordered, gated, numbered cross-examination findings for the report.

    Ranking: most damning first (contradictions > tests never performed >
    omitted-from-report > unverifiable measurements > technique gaps).
    Every returned finding survived `passes_materiality_gate`, so it pits
    a specific written claim against timestamped video evidence and never
    contains administrative/transcription noise."""
    merged = merge_three_way_issues(list(verdicts or []), three_way_ledger)
    if extra_findings:
        existing = {_claim_id(v) for v in merged}
        for row in extra_findings:
            if isinstance(row, dict) and _claim_id(row) not in existing:
                merged.append(row)
                existing.add(_claim_id(row))

    annotated = [
        annotate_egregious_fields(v)
        for v in merged
        if not is_metadata_claim_id(_claim_id(v))
    ]
    gated = [
        a
        for a in annotated
        if passes_materiality_gate(a) and float(a.get("egregious_score") or 0.0) >= min_score
    ]
    ranked = sorted(
        gated,
        key=lambda r: (-float(r.get("egregious_score") or 0), _claim_id(r)),
    )[: max(1, int(max_findings))]

    findings: List[Dict[str, Any]] = []
    for i, row in enumerate(ranked, start=1):
        ce = row.get("cross_examination")
        if not isinstance(ce, dict):
            try:
                from .cme_cross_examination import build_cross_examination

                ce = build_cross_examination(row)
            except Exception:
                ce = {}
        findings.append(
            {
                "number": i,
                "leading_question": str((ce or {}).get("leading_question") or ""),
                "claim_id": _claim_id(row),
                "test_name": _test_display_name(row),
                "verdict": _verdict(row),
                "issue_type_label": str(row.get("issue_type_label") or ""),
                "egregious_score": float(row.get("egregious_score") or 0.0),
                "claim_statement": _claim_statement(row),
                "report_quote": str(row.get("report_quote") or row.get("claim_text") or ""),
                "report_page": row.get("report_page"),
                "fact_statement": _fact_statement(row, exam_window=exam_window),
                "timestamps": _finding_timestamps(row),
                "why_it_matters": str(row.get("why_it_matters") or ""),
            }
        )
    return findings
