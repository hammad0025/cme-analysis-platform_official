"""
Lawyer-facing standard CME report (HTML + optional PDF) from comprehensive + behavior outputs.
"""

from __future__ import annotations

import json
import subprocess
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .cme_analysis_utils import filter_medical_claim_verdicts
from .cme_egregious_ranking import (
    build_duration_finding,
    build_numbered_cross_examinations,
    rank_main_issues,
)


def _fmt_ts(sec: float) -> str:
    m = int(sec // 60)
    s = int(sec % 60)
    return f"{m}:{s:02d}"


# Web app that hosts /sessions/{id}; timestamps in the report deep-link here
# (the app re-fetches a fresh presigned video URL, so links never expire).
DEFAULT_APP_BASE_URL = "https://cme-analysis-platform-official.vercel.app"


def _session_link_base(case_meta: Dict[str, Any]) -> str:
    """`{app_base_url}/sessions/{session_id}` when a session id is known,
    else empty string (timestamps render as plain spans)."""
    session_id = str(case_meta.get("session_id") or "").strip()
    if not session_id:
        return ""
    base = str(case_meta.get("app_base_url") or "").strip() or DEFAULT_APP_BASE_URL
    return f"{base.rstrip('/')}/sessions/{session_id}"


def _ts_html(sec: float, session_link_base: str, label: Optional[str] = None) -> str:
    """Clickable timestamp when a session link base is available; plain
    span otherwise. The deep-link seeks the session video to `sec`."""
    text = label if label is not None else _fmt_ts(sec)
    if session_link_base:
        return (
            f'<a class="timestamp" href="{session_link_base}?t={int(sec)}" '
            f'title="Open session video at {text}">{text}</a>'
        )
    return f'<span class="timestamp">{text}</span>'


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_VISIBILITY_LEVELS = ("full", "partial", "obscured")


def _normalize_visibility(value: Any) -> str:
    """Coerce a raw visibility token into one of `full|partial|obscured`.

    Anything outside the canonical set (including empty, `unknown`, or
    null) is collapsed to an empty string so it does not get counted in
    the visibility breakdown. This is intentional: silence is not
    `obscured` and silence is not `full`."""
    v = str(value or "").strip().lower()
    if v in _VISIBILITY_LEVELS:
        return v
    return ""


def _safe_confidence(value: Any) -> Optional[float]:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return None
    if c < 0.0:
        return 0.0
    if c > 1.0:
        return 1.0
    return c


def merge_frame_rows(
    comprehensive_frames: List[dict],
    behavior_result: Optional[dict],
    interval_sec: float,
) -> Tuple[List[dict], Dict[str, Any]]:
    """Merge per-frame comprehensive JSON with behavior visual_observations by frame_id.

    Each merged row carries visibility / occlusion / confidence fields
    from both passes so downstream sections in the standard report can
    surface where findings sit on the evidentiary scale:

    - `visibility`, `occlusion_notes`, `confidence` come from the
      comprehensive (technique) frame analysis.
    - `behavior_visibility`, `behavior_confidence` come from the
      behavior pass when a sibling observation exists.

    Old checkpoints that lack these fields rehydrate cleanly via
    `.get(..., default)` so the report degrades gracefully."""
    beh_by_id: Dict[str, dict] = {}
    if behavior_result and behavior_result.get("visual_observations"):
        for o in behavior_result["visual_observations"]:
            fid = o.get("frame_id")
            if fid:
                beh_by_id[fid] = o

    merged = []
    for c in comprehensive_frames:
        fid = c.get("frame_id", "")
        b = beh_by_id.get(fid, {})
        ts = float(c.get("timestamp_sec", 0))
        gonio = any(
            (x or "").lower() in ("goniometer", "inclinometer")
            for x in (c.get("equipment_visible") or [])
        )
        beh_look = b.get("doctor_looking_at_patient")
        if beh_look is None:
            beh_look = c.get("doctor_making_eye_contact")

        row = {
            "frame_id": fid,
            "timestamp_sec": ts,
            "timestamp": _fmt_ts(ts),
            "activity": "physical_exam" if (c.get("test_type") or "") not in ("", "none", "conversation") else "conversation",
            "test_type": (c.get("test_type") or "none").lower().replace(" ", "_"),
            "body_part": (c.get("body_region") or "none").lower().replace(" ", "_"),
            "goniometer_used": gonio,
            "doctor_looking_at_patient": bool(c.get("doctor_making_eye_contact", False)),
            "patient_in_gown": (c.get("patient_attire") or "").lower() == "gown",
            "patient_distress": bool(c.get("patient_visible_distress", False)),
            "reflex_hammer_visible": any(
                "reflex" in (x or "").lower() or "hammer" in (x or "").lower()
                for x in (c.get("equipment_visible") or [])
            ),
            "notes": c.get("notes") or "",
            "behavior_notes": b.get("notes", ""),
            "behavior_looking": beh_look,
            "visibility": _normalize_visibility(c.get("visibility")),
            "occlusion_notes": str(c.get("occlusion_notes") or ""),
            "confidence": _safe_confidence(c.get("confidence")),
            "behavior_visibility": _normalize_visibility(b.get("visibility")),
            "behavior_confidence": _safe_confidence(b.get("confidence")),
        }
        merged.append(row)

    stats = {
        "goniometer_frames": sum(1 for r in merged if r["goniometer_used"]),
        "distress_count": sum(1 for r in merged if r["patient_distress"]),
        "looking_count": sum(1 for r in merged if r.get("behavior_looking") is True),
        "total_frames": len(merged),
    }
    if stats["total_frames"]:
        known = [r for r in merged if r.get("behavior_looking") is not None]
        if known:
            stats["looking_pct"] = round(
                100 * sum(1 for r in known if r.get("behavior_looking") is True) / len(known)
            )
        else:
            stats["looking_pct"] = round(
                100 * sum(1 for r in merged if r.get("doctor_looking_at_patient")) / stats["total_frames"]
            )
    else:
        stats["looking_pct"] = 0
    return merged, stats


def compute_visibility_breakdown(
    rows: List[dict],
    *,
    field: str = "visibility",
) -> Dict[str, Any]:
    """Return `{full, partial, obscured, unknown, total, full_pct, partial_pct, obscured_pct}`.

    Percentages are integer-rounded against `total` (the number of rows,
    including ones with unknown visibility) so callers can show an honest
    `unknown` slice without it disappearing. Percentages for the three
    canonical buckets sum to <=100 by design when there are unknown
    rows; the inline pill only shows the canonical three."""
    counts = {"full": 0, "partial": 0, "obscured": 0, "unknown": 0}
    for r in rows or []:
        v = _normalize_visibility(r.get(field))
        if v:
            counts[v] += 1
        else:
            counts["unknown"] += 1
    total = (counts["full"] + counts["partial"] + counts["obscured"] + counts["unknown"])
    if total:
        full_pct = round(100 * counts["full"] / total)
        partial_pct = round(100 * counts["partial"] / total)
        obscured_pct = round(100 * counts["obscured"] / total)
    else:
        full_pct = partial_pct = obscured_pct = 0
    return {
        **counts,
        "total": total,
        "full_pct": full_pct,
        "partial_pct": partial_pct,
        "obscured_pct": obscured_pct,
    }


def _confidence_stats(
    rows: List[dict],
    *,
    field: str = "confidence",
) -> Dict[str, Any]:
    """Return `{count, mean, p25, p75}` for the named confidence field.

    Rows with None / unparseable confidence are skipped; the count is
    over rows that contributed a value. Returns zeros when no row had a
    usable confidence."""
    values: List[float] = []
    for r in rows or []:
        c = r.get(field)
        if isinstance(c, (int, float)) and 0.0 <= float(c) <= 1.0:
            values.append(float(c))
    if not values:
        return {"count": 0, "mean": 0.0, "p25": 0.0, "p75": 0.0}
    values.sort()
    n = len(values)
    mean = sum(values) / n

    def _pct(p: float) -> float:
        if n == 1:
            return values[0]
        idx = p * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return values[lo] * (1 - frac) + values[hi] * frac

    return {
        "count": n,
        "mean": round(mean, 3),
        "p25": round(_pct(0.25), 3),
        "p75": round(_pct(0.75), 3),
    }


def _visibility_pill(rows: List[dict]) -> str:
    """Render the inline `[full visibility: X% · partial: Y% · obscured: Z%]`
    pill for a window of merged rows. Uses palette colors already defined
    by the report stylesheet -- no new colors."""
    bd = compute_visibility_breakdown(rows)
    if bd["total"] == 0:
        return ""
    return (
        '<span class="vis-pill" title="Visibility distribution across '
        f'{bd["total"]} cited frame(s).">'
        f'[full visibility: {bd["full_pct"]}% '
        f'&middot; partial: {bd["partial_pct"]}% '
        f'&middot; obscured: {bd["obscured_pct"]}%]'
        "</span>"
    )


def _build_timeline(merged: List[dict], interval_sec: float) -> Dict[str, Any]:
    test_timeline: Dict[str, List[dict]] = defaultdict(list)
    body_timeline: Dict[str, List[dict]] = defaultdict(list)
    distress_events = []
    not_looking = []

    for r in merged:
        ts = r["timestamp"]
        ts_sec = r["timestamp_sec"]
        tt = r["test_type"]
        if tt and tt != "none":
            test_timeline[tt].append(
                {
                    "timestamp": ts,
                    "seconds": ts_sec,
                    "body_part": r["body_part"],
                    "notes": r["notes"],
                }
            )
        bp = r["body_part"]
        if bp and bp != "none":
            body_timeline[bp].append(
                {
                    "timestamp": ts,
                    "seconds": ts_sec,
                    "test_type": tt,
                    "notes": r["notes"],
                }
            )
        if r["patient_distress"]:
            distress_events.append({"timestamp": ts, "seconds": ts_sec, "notes": r["notes"]})
        if r.get("behavior_looking") is False and r["activity"] == "physical_exam":
            not_looking.append({"timestamp": ts, "seconds": ts_sec, "notes": r["notes"]})

    exam_times = [r["timestamp_sec"] for r in merged if r["test_type"] not in ("none", "conversation", "")]
    window = {}
    if exam_times:
        lo, hi = min(exam_times), max(exam_times)
        window = {
            "start": _fmt_ts(lo),
            "end": _fmt_ts(hi),
            "duration_seconds": int(hi - lo),
        }
    else:
        window = {"start": "0:00", "end": "0:00", "duration_seconds": 0}

    return {
        "exam_window": window,
        "test_timeline": {k: v for k, v in test_timeline.items()},
        "body_part_timeline": {k: v for k, v in body_timeline.items()},
        "distress_events": distress_events,
        "doctor_behavior_concerns": not_looking,
    }


def _get_claim_text(claims: dict, *path: str, default: str = "") -> str:
    """Resolve a claim's display text.

    Backwards-compatible with the original use site (deep-key lookup into
    raw claims.json). When the first path component matches a structured
    ClaimVerdict entry under a top-level "claim_verdicts" key
    (e.g. when callers pass the merged verdict bundle here), prefer the
    verdict's claim_text since it has already been coerced from a string
    or a dict to a stable display string."""
    if not isinstance(claims, dict):
        return default
    verdicts = claims.get("claim_verdicts")
    if path and isinstance(verdicts, list):
        for v in verdicts:
            if isinstance(v, dict) and v.get("claim_id") == path[0]:
                txt = v.get("claim_text") or ""
                if txt:
                    return str(txt)[:200]
    d = claims
    for p in path:
        if not isinstance(d, dict) or p not in d:
            return default
        d = d[p]
    if d is None:
        return default
    return str(d)[:200]


_VERDICT_COLORS = {
    "supported": "#22c55e",
    "partially_supported": "#f59e0b",
    "contradicted": "#c53030",
    "not_shown": "#718096",
    "insufficient_evidence": "#718096",
}

_VERDICT_LABELS = {
    "supported": "Supported",
    "partially_supported": "Partially supported",
    "contradicted": "Contradicted",
    "not_shown": "Not shown",
    "insufficient_evidence": "Insufficient evidence",
}


def _truncate(text: str, limit: int) -> str:
    s = str(text or "")
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "..."


def _escape_attr(text: str) -> str:
    s = str(text or "")
    return (
        s.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _escape_html(text: str) -> str:
    s = str(text or "")
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _visibility_caveat_for_verdict(
    evidence_list: List[Any],
    visibility_by_frame_id: Optional[Dict[str, str]],
) -> str:
    """If any cited Evidence frame_id has a non-`full` visibility in the
    merged-row lookup, return a short parenthetical describing the
    dominant non-full visibility level. Empty string when all cited
    frames are `full` or when the lookup is unavailable."""
    if not visibility_by_frame_id:
        return ""
    bad: Dict[str, int] = {"partial": 0, "obscured": 0}
    seen_any = False
    for ev in evidence_list or []:
        if not isinstance(ev, dict):
            continue
        fid = ev.get("frame_id")
        if not fid:
            continue
        seen_any = True
        v = _normalize_visibility(visibility_by_frame_id.get(str(fid), ""))
        if v in bad:
            bad[v] += 1
    if not seen_any:
        return ""
    if bad["partial"] == 0 and bad["obscured"] == 0:
        return ""
    if bad["obscured"] >= bad["partial"]:
        dominant = "obscured"
    else:
        dominant = "partial"
    return f" (visibility: {dominant} at most cited frames)"


def _has_transcript_evidence(evidence_list: List[Any]) -> bool:
    """True iff any cited Evidence dict has ``kind == 'transcript_span'``.

    Used to flag claim verdicts whose reasoning cites verbal/audio
    evidence so the report can append a terse `(verbal evidence)`
    parenthetical to the reasoning cell."""
    for ev in evidence_list or []:
        if isinstance(ev, dict) and str(ev.get("kind") or "") == "transcript_span":
            return True
    return False


def _extract_verdict_timestamp_secs(verdict: dict, *, limit: int = 3) -> List[float]:
    stamps: List[float] = []
    for ev in verdict.get("evidence") or []:
        if not isinstance(ev, dict):
            continue
        ts = ev.get("timestamp_sec")
        if isinstance(ts, (int, float)):
            stamps.append(float(ts))
    return sorted(set(stamps))[:limit]


def _extract_verdict_timestamps(verdict: dict, *, limit: int = 3) -> List[str]:
    return [_fmt_ts(s) for s in _extract_verdict_timestamp_secs(verdict, limit=limit)]


def _render_deposition_crosswalk_top_findings(
    claim_verdicts: Optional[List[dict]],
    *,
    session_link_base: str = "",
    three_way_ledger: Optional[dict] = None,
) -> str:
    if not claim_verdicts:
        return (
            "            <li><em>Claim verification not run — run "
            "scripts/run_claim_verifier.py with claims_atomic.json.</em></li>"
        )
    claim_verdicts = filter_medical_claim_verdicts(claim_verdicts)
    main_issues = rank_main_issues(
        claim_verdicts,
        three_way_ledger=three_way_ledger,
        max_issues=7,
    )
    if not main_issues:
        return "            <li><em>No high-priority discrepancies met the main-issues threshold.</em></li>"

    items: List[str] = []
    for v in main_issues:
        label = str(v.get("test_name") or v.get("claim_id") or "Claim")
        issue_label = str(v.get("issue_type_label") or "ISSUE")
        ce = v.get("cross_examination") if isinstance(v.get("cross_examination"), dict) else {}
        leading = str(ce.get("leading_question") or v.get("issue_punch_line") or "")
        report_cite = str(ce.get("report_citation") or v.get("report_quote") or "")
        video_finding = str(ce.get("video_finding") or v.get("video_shows") or "")
        why = str(v.get("why_it_matters") or "")

        stamps = [t for t in (ce.get("timestamps") or []) if isinstance(t, dict)]
        if stamps:
            ts_str = ", ".join(
                _ts_html(float(t.get("sec") or 0.0), session_link_base, str(t.get("label") or ""))
                for t in stamps
            )
        else:
            secs = _extract_verdict_timestamp_secs(v)
            ts_str = (
                ", ".join(_ts_html(s, session_link_base) for s in secs)
                if secs
                else '<span class="timestamp">—</span>'
            )

        refs = [r for r in (ce.get("literature_refs") or []) if isinstance(r, dict) and r.get("url")]
        refs_html = ""
        if refs:
            refs_html = (
                "<br/><span class='ce-refs'>Refs: "
                + ", ".join(
                    f'<a href="{_escape_html(str(r.get("url")))}" target="_blank" rel="noopener">'
                    f'{_escape_html(_truncate(str(r.get("title") or r.get("url")), 60))}</a>'
                    for r in refs[:4]
                )
                + "</span>"
            )

        verdict_key = str(v.get("verdict") or "insufficient_evidence").lower()
        color = _VERDICT_COLORS.get(verdict_key, "#c53030")
        items.append(
            "            <li class='main-issue'>"
            f"<span class='issue-badge' style='background:{color}'>{_escape_html(issue_label)}</span> "
            f"<strong>{_escape_html(label)}</strong><br/>"
            f"<span class='ce-q'><strong>Q:</strong> {_escape_html(_truncate(leading, 280))}</span><br/>"
            f"<span class='ce-cite'><strong>Report:</strong> {_escape_html(_truncate(report_cite, 180))}</span><br/>"
            f"<span class='ce-video'><strong>Video:</strong> {_escape_html(_truncate(video_finding, 180))} "
            f"({ts_str})</span>"
            + (f"<br/><span class='ce-why'><em>{_escape_html(_truncate(why, 200))}</em></span>" if why else "")
            + refs_html
            + "</li>"
        )
    return "\n".join(items)


def _render_numbered_cross_exam_findings(
    findings: List[dict],
    *,
    claim_verdicts_present: bool,
    session_link_base: str = "",
) -> str:
    """Numbered, litigation-ready CROSS EXAMINATION findings (leads the report).

    Format per finding:

        CROSS EXAMINATION #1: Doctor stated in his report that he performed
        the Babinski test.
        FACT: What was performed could barely qualify as a Babinski — it was
        hardly one plane of motion. See 22:13 of the video.

    Only findings that survived the materiality gate reach this renderer,
    ranked most-damning first."""
    if not claim_verdicts_present:
        return (
            '        <p><em>Claim verification not run — run '
            "scripts/run_claim_verifier.py with claims_atomic.json to generate "
            "cross-examination findings.</em></p>"
        )
    if not findings:
        return (
            "        <p><em>No cross-examination findings met the materiality "
            "threshold for this session.</em></p>"
        )

    blocks: List[str] = []
    for f in findings:
        number = int(f.get("number") or 0)
        heading = f"CROSS EXAMINATION #{number}: {f.get('claim_statement') or ''}"
        quote = str(f.get("report_quote") or "")
        page = f.get("report_page")
        cite = ""
        if quote:
            page_txt = f"p. {page}, " if page is not None else ""
            cite = (
                f'<p class="cx-cite"><strong>Report ({page_txt}verbatim):</strong> '
                f'&ldquo;{_escape_html(_truncate(quote, 300))}&rdquo;</p>'
            )
        fact = str(f.get("fact_statement") or "")
        stamps = [t for t in (f.get("timestamps") or []) if isinstance(t, dict)]
        ts_links = ""
        if stamps and session_link_base:
            ts_links = (
                '<p class="cx-links">Video: '
                + ", ".join(
                    _ts_html(float(t.get("sec") or 0.0), session_link_base, str(t.get("label") or ""))
                    for t in stamps
                )
                + "</p>"
            )
        question = str(f.get("leading_question") or "")
        q_html = (
            f'<p class="cx-q"><strong>Q:</strong> {_escape_html(_truncate(question, 320))}</p>'
            if question
            else ""
        )
        blocks.append(
            '        <div class="cx-finding">\n'
            f"            <h3>{_escape_html(heading)}</h3>\n"
            f"            {cite}\n"
            f'            <p class="cx-fact"><strong>FACT:</strong> {_escape_html(fact)}</p>\n'
            f"            {ts_links}\n"
            f"            {q_html}\n"
            "        </div>"
        )
    return "\n".join(blocks)


def _render_cross_examination_section(
    verdicts: List[dict],
    *,
    session_link_base: str = "",
) -> str:
    """CROSS-EXAMINATION SCRIPT section: one block per claim with the
    leading question, report citation, video finding + timestamp links,
    and literature references. Rows without a cross_examination block
    get one built on the fly (offline resolver only)."""
    if not verdicts:
        return ""

    blocks: List[str] = []
    for v in verdicts:
        ce = v.get("cross_examination")
        if not isinstance(ce, dict):
            try:
                try:
                    from .cme_cross_examination import build_cross_examination
                except ImportError:
                    from cme_cross_examination import build_cross_examination  # type: ignore
                ce = build_cross_examination(v)
            except Exception:
                continue

        verdict_key = str(v.get("verdict") or "insufficient_evidence").lower()
        verdict_label = _VERDICT_LABELS.get(verdict_key, verdict_key.replace("_", " ").title())
        color = _VERDICT_COLORS.get(verdict_key, "#4a5568")
        title = str(v.get("test_name") or v.get("claim_id") or "Claim")

        ts_links = ""
        stamps = [t for t in (ce.get("timestamps") or []) if isinstance(t, dict)]
        if stamps:
            ts_links = " ".join(
                _ts_html(float(t.get("sec") or 0.0), session_link_base, str(t.get("label") or ""))
                for t in stamps
            )

        refs_html = ""
        refs = [r for r in (ce.get("literature_refs") or []) if isinstance(r, dict) and r.get("url")]
        if refs:
            ref_links = " &middot; ".join(
                f'<a href="{_escape_attr(str(r["url"]))}" target="_blank" rel="noopener">'
                f"{_escape_html(_truncate(str(r.get('title') or r['url']), 90))}</a>"
                for r in refs
            )
            refs_html = f'<p class="ce-refs"><strong>References:</strong> {ref_links}</p>'

        video_line = _escape_html(str(ce.get("video_finding") or ""))
        if ts_links:
            video_line = f"{video_line} {ts_links}" if video_line else ts_links

        blocks.append(
            f"""    <div class="crossexam-block">
        <h4>{_escape_html(title)} — <span style="color: {color}">{_escape_html(verdict_label)}</span></h4>
        <p class="ce-q"><strong>Q:</strong> {_escape_html(str(ce.get("leading_question") or ""))}</p>
        <p class="ce-cite"><strong>Report:</strong> {_escape_html(str(ce.get("report_citation") or ""))}</p>
        <p class="ce-video"><strong>Video:</strong> {video_line or "—"}</p>
        {refs_html}
    </div>"""
        )

    if not blocks:
        return ""
    return (
        "    <h2>CROSS-EXAMINATION SCRIPT</h2>\n"
        "    <p>Verdict-aware leading questions for deposition. Each question pairs the doctor's "
        "written statement with what the video actually shows; timestamps open the session video "
        "at that moment, and references link to the supporting literature online.</p>\n"
        + "\n".join(blocks)
    )


def render_claim_verdicts_table(
    verdicts: List[dict],
    *,
    visibility_by_frame_id: Optional[Dict[str, str]] = None,
    session_link_base: str = "",
) -> Tuple[str, str]:
    """Render the per-claim verdict table plus the evidence footnotes
    section. Returns (table_html, footnotes_html). When `verdicts` is
    empty, returns a 'verification not run' notice for the table slot and
    an empty string for the footnotes.

    When `visibility_by_frame_id` is supplied, the reasoning cell is
    suffixed with a short caveat for any verdict whose cited Evidence
    sits on frames with non-`full` visibility, so the lawyer can see at
    a glance which verdicts are visibility-limited."""
    if not verdicts:
        notice = (
            '<div class="info">'
            "<strong>Claim verification not run.</strong> "
            "No claim_verdicts.json was found alongside this report; the "
            "claim vs. video panel below falls back to the raw claims file."
            "</div>"
        )
        return notice, ""

    rows = []
    footnote_blocks = []
    for v in verdicts:
        cid = str(v.get("claim_id") or "")
        verdict = str(v.get("verdict") or "insufficient_evidence").lower()
        label = _VERDICT_LABELS.get(verdict, verdict.replace("_", " ").title())
        color = _VERDICT_COLORS.get(verdict, "#4a5568")
        try:
            conf_pct = round(float(v.get("confidence") or 0.0) * 100)
        except (TypeError, ValueError):
            conf_pct = 0
        claim_text_full = str(v.get("report_quote") or v.get("claim_text") or "")
        page = v.get("report_page")
        page_cell = f"p.{page}" if page is not None else "—"
        ts_secs = _extract_verdict_timestamp_secs(v, limit=4)
        ts_cell = (
            ", ".join(_ts_html(s, session_link_base) for s in ts_secs)
            if ts_secs
            else '<span class="timestamp">—</span>'
        )
        reasoning_full = str(v.get("video_shows") or v.get("reasoning") or "")
        evidence_list = v.get("evidence") or []
        ev_count = len(evidence_list)
        footnote_id = f"fn-{cid or 'unknown'}"
        caveat = _visibility_caveat_for_verdict(evidence_list, visibility_by_frame_id)
        reasoning_with_caveat = reasoning_full + (caveat or "")
        if _has_transcript_evidence(evidence_list):
            reasoning_with_caveat += " (verbal evidence)"

        rows.append(
            f"""        <tr>
            <td><code>{_escape_html(cid)}</code></td>
            <td>{_escape_html(page_cell)}</td>
            <td title="{_escape_attr(claim_text_full)}">{_escape_html(_truncate(claim_text_full, 200))}</td>
            <td>{ts_cell}</td>
            <td><strong style="color: {color}">{_escape_html(label)}</strong></td>
            <td title="{_escape_attr(reasoning_with_caveat)}">{_escape_html(_truncate(reasoning_with_caveat, 240))}</td>
            <td><a href="#{footnote_id}">{ev_count}</a></td>
        </tr>"""
        )

        if evidence_list:
            ev_items = []
            for ev in evidence_list:
                if not isinstance(ev, dict):
                    continue
                kind = _escape_html(str(ev.get("kind") or "frame"))
                frame_id = _escape_html(str(ev.get("frame_id") or ""))
                ts = ev.get("timestamp_sec")
                end_ts = ev.get("end_timestamp_sec")
                quote = _escape_html(str(ev.get("quote") or ""))
                speaker = _escape_html(str(ev.get("speaker") or ""))
                raw_ref = _escape_html(str(ev.get("raw_response_ref") or ""))
                notes = _escape_html(str(ev.get("notes") or ""))
                head_parts = [f"<strong>{kind}</strong>"]
                if frame_id:
                    head_parts.append(f"frame=<code>{frame_id}</code>")
                if isinstance(ts, (int, float)):
                    if isinstance(end_ts, (int, float)):
                        head_parts.append(
                            f"@ {_fmt_ts(float(ts))} - {_fmt_ts(float(end_ts))}"
                        )
                    else:
                        head_parts.append(f"@ {_fmt_ts(float(ts))}")
                if speaker:
                    head_parts.append(f"speaker={speaker}")
                if raw_ref:
                    head_parts.append(f"raw=<code>{raw_ref}</code>")
                body_parts = []
                if quote:
                    body_parts.append(f'"{quote}"')
                if notes:
                    body_parts.append(notes)
                head = " | ".join(head_parts)
                body = " - ".join(body_parts) if body_parts else ""
                ev_items.append(f"<li>{head}{(': ' + body) if body else ''}</li>")
            footnote_blocks.append(
                f'<div id="{footnote_id}" class="footnote-block">'
                f"<h4><code>{_escape_html(cid)}</code> evidence ({ev_count})</h4>"
                f"<ul>{''.join(ev_items)}</ul>"
                f"</div>"
            )
        else:
            footnote_blocks.append(
                f'<div id="{footnote_id}" class="footnote-block">'
                f"<h4><code>{_escape_html(cid)}</code> evidence (0)</h4>"
                "<p><em>No specific frame or quote evidence cited.</em></p>"
                "</div>"
            )

    table_html = f"""    <h2>REPORT VS VIDEO — DEPOSITION CROSSWALK</h2>
    <p>Each row is a statement from the insurance doctor&apos;s written report, checked against
    deposition video timestamps. Click timestamps in counsel&apos;s working copy to seek the master recording.</p>
    <table class="claim-verdicts">
        <tr>
            <th>Claim ID</th>
            <th>Page</th>
            <th>Report quote</th>
            <th>Video timestamp</th>
            <th>Verdict</th>
            <th>What video shows</th>
            <th>Evidence</th>
        </tr>
{chr(10).join(rows)}
    </table>"""
    footnotes_html = (
        '<h2>CLAIM VERDICT EVIDENCE (footnotes)</h2>'
        + "\n".join(footnote_blocks)
    )
    return table_html, footnotes_html


_VERBAL_FLAG_LABELS = (
    ("rude_comment", "rude"),
    ("sarcastic", "sarcastic"),
    ("condescending", "condescending"),
    ("inappropriate_comment", "inappropriate"),
    ("dismissing_symptom", "dismissive"),
)


def _verbal_flag_label(obs: dict) -> Optional[str]:
    """Return the first matching label for a `VerbalBehaviorObservation` dict,
    or `None` if no problematic flag is set."""
    if not isinstance(obs, dict):
        return None
    for field_name, label in _VERBAL_FLAG_LABELS:
        if bool(obs.get(field_name)):
            return label
    return None


def render_verbal_evidence_section(
    transcript: Optional[dict],
    behavior_result: Optional[dict],
) -> str:
    """Render the VERBAL EVIDENCE section HTML, or empty string when no
    transcript was produced for this run.

    `transcript` is the `transcript.json` payload (asdict of `Transcript`).
    `behavior_result` is the `behavior_analysis.json` payload (asdict of
    `BehaviorAnalysisResult`). When the transcript is absent we return
    `""` so no empty stub renders in the report.

    Per the spec: top 5 problematic quotes where any of `rude_comment`,
    `sarcastic`, `condescending`, `inappropriate_comment`, or
    `dismissing_symptom` (the closest analogue to "dismissive" on
    `VerbalBehaviorObservation`) is True. Each quote is timestamped via
    the observation's `start_sec` when available; otherwise the
    timestamp slot reads `[--:--]` rather than a fabricated `0:00`.

    Honest-uncertainty rule: when the backend is `openai-whisper-api`
    and the response shape lacked word probabilities
    (`mean_word_confidence == 0.0`), we append a parenthetical to the
    section header so the reader knows the per-word confidence number
    is not available from this backend.
    """
    if not isinstance(transcript, dict):
        return ""

    backend = str(transcript.get("backend") or "")
    model_id = str(transcript.get("model_id") or "")
    word_count = int(transcript.get("word_count") or 0)
    segments = transcript.get("segments") or []
    seg_count = len(segments)
    try:
        mean_conf = float(transcript.get("mean_word_confidence") or 0.0)
    except (TypeError, ValueError):
        mean_conf = 0.0
    conf_pct_str = f"{mean_conf * 100:.0f}%"

    header_caveat = ""
    if backend == "openai-whisper-api" and mean_conf == 0.0:
        header_caveat = " (transcript confidence not estimable for this backend)"

    summary_line = (
        f"Transcribed via {_escape_html(backend or 'unknown')}/"
        f"{_escape_html(model_id or 'unknown')} &mdash; "
        f"{word_count} words across {seg_count} segments "
        f"(mean confidence {conf_pct_str})."
    )

    verbal_obs: List[dict] = []
    if isinstance(behavior_result, dict):
        candidate = behavior_result.get("verbal_observations") or []
        if isinstance(candidate, list):
            verbal_obs = [o for o in candidate if isinstance(o, dict)]

    flagged: List[Tuple[dict, str]] = []
    for o in verbal_obs:
        label = _verbal_flag_label(o)
        if label is None:
            continue
        flagged.append((o, label))
        if len(flagged) >= 5:
            break

    quotes_html = ""
    if flagged:
        items = []
        for o, label in flagged:
            quote_text = str(o.get("problematic_quote") or o.get("text") or "").strip()
            if not quote_text:
                continue
            start = o.get("start_sec")
            if isinstance(start, (int, float)):
                ts_str = f"[{_fmt_ts(float(start))}]"
            else:
                ts_str = "[--:--]"
            items.append(
                "<li>"
                f"<span class=\"timestamp\">{_escape_html(ts_str)}</span> "
                f'"{_escape_html(quote_text)}" &mdash; flag: '
                f"<strong>{_escape_html(label)}</strong>"
                "</li>"
            )
        if items:
            quotes_html = (
                "<h3>Top problematic quotes</h3>"
                f"<ol class=\"verbal-quotes\">{''.join(items)}</ol>"
            )

    full_text = "\n".join(
        str(seg.get("text") or "").strip()
        for seg in segments
        if isinstance(seg, dict)
    ).strip()
    full_text_block = ""
    if full_text:
        full_text_block = (
            "<details class=\"verbal-fulltext\">"
            "<summary>Full transcript</summary>"
            f"<pre>{_escape_html(full_text)}</pre>"
            "</details>"
        )

    return (
        f'<h2>VERBAL EVIDENCE{_escape_html(header_caveat)}</h2>'
        '<div class="info">'
        f"<p>{summary_line}</p>"
        f"{quotes_html}"
        f"{full_text_block}"
        "</div>"
    )


def build_standard_html(
    case_meta: Dict[str, Any],
    merged: List[dict],
    timeline: Dict[str, Any],
    stats: Dict[str, Any],
    claims: Optional[dict],
    claim_verdicts: Optional[List[dict]] = None,
    transcript: Optional[dict] = None,
    behavior_result: Optional[dict] = None,
    three_way_ledger: Optional[dict] = None,
    comprehensive_summary: Optional[dict] = None,
) -> str:
    """Produce HTML matching the standard CME report layout.

    When `claim_verdicts` is provided (loaded from claim_verdicts.json),
    the claim vs. video panel renders a full per-claim verdict table with
    a footnotes section listing each piece of evidence. When the file is
    absent, a 'verification not run' notice is rendered instead and the
    legacy raw-claims display is preserved as the fallback view."""
    claim_verdicts = filter_medical_claim_verdicts(claim_verdicts or [])
    patient = case_meta.get("patient", "Unknown")
    dob = case_meta.get("dob", "")
    examiner = case_meta.get("examiner", "")
    exam_date = case_meta.get("exam_date", "")
    injury_date = case_meta.get("injury_date", "")
    video_len = case_meta.get("video_length", "")
    nframes = stats.get("total_frames", len(merged))
    interval_sec = float(case_meta.get("interval_sec", 5))
    bundle_sha256 = str(case_meta.get("bundle_sha256") or "")
    run_id = str(case_meta.get("run_id") or "")

    looking_pct = stats.get("looking_pct", 0)
    doc_concerns = timeline.get("doctor_behavior_concerns", [])
    ew = timeline.get("exam_window", {})

    claims = claims or {}
    cervical_claim = _get_claim_text(claims, "cervical_spine", "rom")
    neuro_claim = _get_claim_text(claims, "neurological_upper_extremities", "strength")
    reflex_claim = _get_claim_text(claims, "neurological_upper_extremities", "reflexes")

    test_counts: Dict[str, int] = defaultdict(int)
    for r in merged:
        t = r["test_type"]
        if t and t != "none":
            test_counts[t] += 1

    def test_table_rows():
        rows = ""
        order = ["palpation", "rom", "inspection", "reflex", "strength", "cranial_nerve", "gait", "sensory"]
        for test_type in order:
            count = test_counts.get(test_type, 0)
            if count == 0:
                continue
            entries = timeline["test_timeline"].get(test_type, [])
            first_ts = entries[0]["timestamp"] if entries else "N/A"
            last_ts = entries[-1]["timestamp"] if entries else "N/A"
            rows += f"""        <tr>
            <td>{test_type.replace('_', ' ').title()}</td>
            <td>{count}</td>
            <td><span class="timestamp">{first_ts}</span></td>
            <td><span class="timestamp">{last_ts}</span></td>
        </tr>
"""
        return rows

    log_html = ""
    test_order = ["inspection", "palpation", "rom", "strength", "reflex", "sensory", "cranial_nerve", "gait"]
    for test_type in test_order:
        entries = timeline["test_timeline"].get(test_type, [])
        if not entries:
            continue
        first_ts = entries[0]["timestamp"]
        last_ts = entries[-1]["timestamp"]
        log_html += f'<div style="margin: 8px 0;"><span class="test">=== {test_type.upper().replace("_", " ")} ({first_ts} - {last_ts}) ===</span></div>\n'
        for e in entries:
            bp = (e.get("body_part") or "general").replace("_", " ").title()
            notes = (e.get("notes") or "")[:50]
            log_html += f'<div><span class="ts">[{e["timestamp"]}]</span> <span class="body-part">{bp}</span>: {notes}...</div>\n'

    body_rows = ""
    body_order = [
        "cervical_spine",
        "thoracic_spine",
        "lumbar_spine",
        "neck",
        "shoulder",
        "right_shoulder",
        "left_shoulder",
        "right_elbow",
        "left_elbow",
        "right_knee",
        "left_knee",
        "back",
        "hip",
    ]
    seen = set()
    for bp in sorted(timeline["body_part_timeline"].keys(), key=lambda x: (body_order.index(x) if x in body_order else 99, x)):
        entries = timeline["body_part_timeline"][bp]
        if not entries or bp in seen:
            continue
        seen.add(bp)
        first = entries[0]["timestamp"]
        last = entries[-1]["timestamp"]
        tests = ", ".join(sorted({e.get("test_type", "") for e in entries if e.get("test_type")}))
        body_rows += f"""        <tr>
            <td><strong>{bp.replace('_', ' ').title()}</strong></td>
            <td><span class="timestamp">{first}</span></td>
            <td><span class="timestamp">{last}</span></td>
            <td>{tests}</td>
            <td>{len(entries)}</td>
        </tr>
"""

    distress_rows = ""
    for d in timeline["distress_events"]:
        distress_rows += f"""            <tr>
                <td><span class="timestamp">{d['timestamp']}</span></td>
                <td>{d.get('notes', '')}</td>
            </tr>
"""

    doc_rows = ""
    for d in doc_concerns[:12]:
        doc_rows += f"""            <tr>
                <td><span class="timestamp">{d['timestamp']}</span></td>
                <td>{(d.get('notes') or '')[:55]}...</td>
                <td class="not-done">Not observing patient</td>
            </tr>
"""

    more_doc = len(doc_concerns) - 12 if len(doc_concerns) > 12 else 0
    more_doc_html = f'<tr><td colspan="3"><em>...and {more_doc} more instances</em></td></tr>' if more_doc > 0 else ""

    # frame_id -> comprehensive visibility lookup for per-claim caveats.
    visibility_by_frame_id: Dict[str, str] = {
        str(r.get("frame_id") or ""): r.get("visibility") or ""
        for r in merged
        if r.get("frame_id")
    }

    session_link_base = _session_link_base(case_meta)

    verdicts_table_html, verdicts_footnotes_html = render_claim_verdicts_table(
        claim_verdicts,
        visibility_by_frame_id=visibility_by_frame_id,
        session_link_base=session_link_base,
    )

    # Numbered, ranked, materiality-gated CROSS EXAMINATION findings.
    # The exam-duration discrepancy (report time vs. hands-on video time)
    # is synthesized here because it never flows through the claim verifier.
    duration_row = build_duration_finding(comprehensive_summary, exam_window=ew)
    crossexam_findings = build_numbered_cross_examinations(
        claim_verdicts,
        three_way_ledger=three_way_ledger,
        exam_window=ew,
        extra_findings=[duration_row] if duration_row else None,
    )
    crossexam_findings_html = _render_numbered_cross_exam_findings(
        crossexam_findings,
        claim_verdicts_present=bool(claim_verdicts),
        session_link_base=session_link_base,
    )

    # Per-finding visibility pills for TOP FINDINGS bullets.
    # Each bullet's pill is computed over the merged rows whose
    # observation contributes to that finding. `_visibility_pill` returns
    # empty string when the row set is empty, so absent windows render
    # cleanly without a placeholder.
    rom_rows = [r for r in merged if r.get("test_type") == "rom"]
    distress_rows_list = [r for r in merged if r.get("patient_distress")]
    not_looking_rows = [
        r for r in merged
        if r.get("behavior_looking") is False and r.get("activity") == "physical_exam"
    ]
    gonio_pill = _visibility_pill(rom_rows) if rom_rows else _visibility_pill(merged)
    attention_pill = _visibility_pill(not_looking_rows) if not_looking_rows else ""
    distress_pill = _visibility_pill(distress_rows_list)
    sampling_pill = _visibility_pill(merged)

    # Visibility Coverage section data.
    comp_breakdown = compute_visibility_breakdown(merged, field="visibility")
    beh_breakdown = compute_visibility_breakdown(merged, field="behavior_visibility")
    comp_conf = _confidence_stats(merged, field="confidence")
    beh_conf = _confidence_stats(merged, field="behavior_confidence")

    # Top 3 lowest-visibility windows: contiguous spans of non-full
    # (partial+obscured) rows, sorted by length descending. Each window
    # is the (start_ts, end_ts) wall-clock string for the section text.
    def _low_vis_windows(rows_in: List[dict], top_k: int = 3) -> List[str]:
        spans: List[Tuple[float, float, int]] = []
        cur_start: Optional[float] = None
        cur_end: Optional[float] = None
        cur_count = 0
        for r in rows_in:
            v = _normalize_visibility(r.get("visibility"))
            beh_v = _normalize_visibility(r.get("behavior_visibility"))
            non_full = (v in ("partial", "obscured")) or (beh_v in ("partial", "obscured"))
            ts = float(r.get("timestamp_sec") or 0.0)
            if non_full:
                if cur_start is None:
                    cur_start = ts
                cur_end = ts
                cur_count += 1
            else:
                if cur_start is not None and cur_end is not None and cur_count > 0:
                    spans.append((cur_start, cur_end, cur_count))
                cur_start = cur_end = None
                cur_count = 0
        if cur_start is not None and cur_end is not None and cur_count > 0:
            spans.append((cur_start, cur_end, cur_count))
        spans.sort(key=lambda s: s[2], reverse=True)
        out: List[str] = []
        for s, e, cnt in spans[:top_k]:
            if s == e:
                out.append(f"<span class=\"timestamp\">{_fmt_ts(s)}</span> ({cnt} frame)")
            else:
                out.append(
                    f"<span class=\"timestamp\">{_fmt_ts(s)} - {_fmt_ts(e)}</span> ({cnt} frames)"
                )
        return out

    low_vis_windows = _low_vis_windows(merged)
    if low_vis_windows:
        low_vis_sentence = (
            "Lowest-visibility windows by run length: "
            + ", ".join(low_vis_windows)
            + "."
        )
    else:
        low_vis_sentence = (
            "No contiguous non-full visibility windows were detected "
            "in the analyzed frames."
        )

    # Low-confidence callout uses the existing amber/warn palette.
    low_conf_threshold = 0.6
    comp_mean = comp_conf["mean"] if comp_conf["count"] else None
    beh_mean = beh_conf["mean"] if beh_conf["count"] else None
    low_conf_callout = ""
    if (comp_mean is not None and comp_mean < low_conf_threshold) or (
        beh_mean is not None and beh_mean < low_conf_threshold
    ):
        pieces = []
        if comp_mean is not None and comp_mean < low_conf_threshold:
            pieces.append(f"technique pass mean {comp_mean:.2f}")
        if beh_mean is not None and beh_mean < low_conf_threshold:
            pieces.append(f"behavior pass mean {beh_mean:.2f}")
        joined = "; ".join(pieces)
        low_conf_callout = (
            '<div class="warning">'
            f"<strong>Low average model confidence ({joined}).</strong> "
            "Consider reviewing flagged moments manually."
            "</div>"
        )

    def _vis_bar(bd: Dict[str, Any], label: str) -> str:
        if bd["total"] == 0:
            return (
                f'<div class="vis-pass"><h4>{label}</h4>'
                "<p><em>No frames analyzed.</em></p></div>"
            )
        unknown_pct = max(
            0,
            100 - bd["full_pct"] - bd["partial_pct"] - bd["obscured_pct"],
        )
        return f"""<div class="vis-pass">
            <h4>{label}</h4>
            <div class="vis-bar">
                <div class="vis-bar-full" style="width: {bd['full_pct']}%" title="full visibility">{bd['full_pct']}%</div>
                <div class="vis-bar-partial" style="width: {bd['partial_pct']}%" title="partial visibility">{bd['partial_pct']}%</div>
                <div class="vis-bar-obscured" style="width: {bd['obscured_pct']}%" title="obscured">{bd['obscured_pct']}%</div>
                <div class="vis-bar-unknown" style="width: {unknown_pct}%" title="visibility not coded">{unknown_pct}%</div>
            </div>
            <p class="vis-legend"><span class="vis-swatch vis-swatch-full"></span> full {bd['full']} &middot;
            <span class="vis-swatch vis-swatch-partial"></span> partial {bd['partial']} &middot;
            <span class="vis-swatch vis-swatch-obscured"></span> obscured {bd['obscured']} &middot;
            <span class="vis-swatch vis-swatch-unknown"></span> unknown {bd['unknown']}
            (n={bd['total']})</p>
        </div>"""

    def _conf_line(stats: Dict[str, Any], label: str) -> str:
        if not stats.get("count"):
            return f"<li>{label}: <em>no confidence values recorded</em></li>"
        return (
            f"<li>{label}: mean {stats['mean']:.2f}, "
            f"p25 {stats['p25']:.2f}, p75 {stats['p75']:.2f} "
            f"(n={stats['count']})</li>"
        )

    verbal_evidence_section_html = render_verbal_evidence_section(
        transcript, behavior_result
    )

    visibility_section_html = f"""
    <h2>VISIBILITY COVERAGE</h2>
    <div class="info">
        <p>Honest accounting of how much of the analyzed footage was actually
        visible enough to support a finding. <em>Obscured</em> frames are surfaced
        as real numbers, not buried -- a high obscured share weakens any
        downstream claim sitting on top of those frames.</p>
        {_vis_bar(comp_breakdown, "Technique (comprehensive) pass")}
        {_vis_bar(beh_breakdown, "Behavior pass")}
        <h4>Confidence (model-reported, per pass)</h4>
        <ul class="vis-conf-list">
            {_conf_line(comp_conf, "Technique pass")}
            {_conf_line(beh_conf, "Behavior pass")}
        </ul>
        {low_conf_callout}
        <p class="vis-windows">{low_vis_sentence}</p>
    </div>"""

    legacy_fallback_html = ""
    if not claim_verdicts:
        legacy_fallback_html = f"""    <h3>Fallback: raw claim snapshot (claim_verdicts.json absent)</h3>
    <div class="comparison">
        <div class="claim-box">
            <h4>REPORT CLAIMS (from supplied claims file)</h4>
            <p>Cervical ROM: {cervical_claim or 'N/A'}</p>
            <p>Strength: {neuro_claim or 'N/A'}</p>
            <p>Reflexes: {reflex_claim or 'N/A'}</p>
        </div>
        <div class="reality-box">
            <h4>VIDEO SAMPLING SUMMARY</h4>
            <p>Strength-related frames: {test_counts.get('strength', 0)}</p>
            <p>Reflex-related frames: {test_counts.get('reflex', 0)}</p>
            <p>ROM-related frames: {test_counts.get('rom', 0)}</p>
            <p class="not-done">Compare counts and timestamps to the report narrative.</p>
        </div>
    </div>"""

    behavior_appendix_html = f"""
    <h2>APPENDIX — DOCTOR ATTENTION &amp; PATIENT DISTRESS</h2>
    <p class="info">Supplemental behavior review. Primary findings are in the deposition crosswalk above.</p>
    <div class="behavior-section">
        <h3>Attention (visual behavior pass)</h3>
        <div class="progress-bar">
            <div class="progress-fill {'warning' if looking_pct < 80 else ''}" style="width: {min(100, looking_pct)}%;">{looking_pct}%</div>
        </div>
        <h3>Timestamps coded as not observing patient during exam activity</h3>
        <table>
            <tr><th>Timestamp</th><th>Activity</th><th>Concern</th></tr>
            {doc_rows}
            {more_doc_html}
        </table>
    </div>
    <div class="warning">
        <h3>Patient distress</h3>
        <table>
            <tr><th>Timestamp</th><th>Observation</th></tr>
{distress_rows}
        </table>
    </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Comprehensive CME Video Analysis - {patient}</title>
    <style>
        body {{ font-family: Georgia, serif; max-width: 1000px; margin: 0 auto; padding: 30px; line-height: 1.6; color: #333; }}
        h1 {{ color: #1a365d; border-bottom: 3px solid #c53030; padding-bottom: 10px; }}
        h2 {{ color: #2c5282; margin-top: 30px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
        h3 {{ color: #2d3748; }}
        .header-table {{ width: auto; margin-bottom: 25px; }}
        .header-table td {{ padding: 5px 15px 5px 0; }}
        .critical {{ background: #c53030; color: white; padding: 20px; margin: 20px 0; border-radius: 8px; }}
        .critical h2 {{ color: white; border: none; margin-top: 0; }}
        .critical ol {{ margin: 0; padding-left: 20px; }}
        .critical li {{ margin: 10px 0; }}
        .critical .cx-intro {{ color: #fed7d7; font-size: 0.95em; margin: 0 0 14px 0; }}
        .cx-finding {{ background: rgba(255,255,255,0.10); border-left: 4px solid white; padding: 12px 16px; margin: 14px 0; border-radius: 4px; }}
        .cx-finding h3 {{ color: white; margin: 0 0 8px 0; font-size: 1.08em; }}
        .cx-finding p {{ margin: 6px 0; color: white; }}
        .cx-finding .cx-cite {{ color: #fed7d7; font-size: 0.95em; }}
        .cx-finding .cx-fact {{ font-size: 1.02em; }}
        .cx-finding .cx-q {{ color: #fbd38d; font-size: 0.95em; }}
        .cx-finding .cx-links a.timestamp {{ color: #1a365d; }}
        .warning {{ background: #feebc8; border-left: 5px solid #dd6b20; padding: 15px; margin: 15px 0; }}
        .info {{ background: #e2e8f0; padding: 15px; margin: 15px 0; border-radius: 4px; }}
        .comparison {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
        .claim-box {{ background: #e2e8f0; padding: 15px; border-radius: 8px; }}
        .reality-box {{ background: #fed7d7; padding: 15px; border-radius: 8px; }}
        .claim-box h4, .reality-box h4 {{ margin-top: 0; color: #2d3748; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
        th, td {{ border: 1px solid #ccc; padding: 10px; text-align: left; }}
        th {{ background: #2c5282; color: white; }}
        tr:nth-child(even) {{ background: #f7fafc; }}
        .timestamp {{ font-family: monospace; background: #edf2f7; padding: 2px 6px; border-radius: 3px; color: #2d3748; }}
        a.timestamp {{ color: #2c5282; text-decoration: none; border-bottom: 1px dashed #2c5282; }}
        a.timestamp:hover {{ background: #bee3f8; }}
        .crossexam-block {{ background: #fffaf0; border-left: 4px solid #c53030; padding: 14px 18px; margin: 14px 0; border-radius: 4px; }}
        .crossexam-block h4 {{ margin: 0 0 8px 0; color: #1a365d; }}
        .crossexam-block p {{ margin: 6px 0; }}
        .crossexam-block .ce-q {{ font-size: 1.02em; }}
        .crossexam-block .ce-refs {{ font-size: 0.9em; color: #4a5568; }}
        .crossexam-block .ce-refs a {{ color: #2c5282; }}
        .not-done {{ color: #c53030; font-weight: bold; }}
        .summary-box {{ background: #1a365d; color: white; padding: 25px; border-radius: 8px; margin: 25px 0; }}
        .summary-box h2 {{ color: white; border: none; margin-top: 0; }}
        .ref {{ background: #ebf8ff; border-left: 4px solid #3182ce; padding: 12px; margin: 10px 0; font-size: 0.9em; }}
        .behavior-section {{ background: #f7fafc; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #e2e8f0; }}
        .progress-bar {{ height: 24px; background: #e2e8f0; border-radius: 12px; overflow: hidden; margin: 10px 0; }}
        .progress-fill {{ height: 100%; background: linear-gradient(90deg, #48bb78, #38a169); display: flex; align-items: center; justify-content: flex-end; padding-right: 10px; color: white; font-weight: bold; }}
        .progress-fill.warning {{ background: linear-gradient(90deg, #ed8936, #dd6b20); }}
        .test-log {{ font-family: monospace; background: #1a202c; color: #e2e8f0; padding: 15px; border-radius: 8px; max-height: 350px; overflow-y: auto; font-size: 0.85em; }}
        .test-log .ts {{ color: #68d391; }}
        .test-log .body-part {{ color: #63b3ed; }}
        .test-log .test {{ color: #fbd38d; }}
        table.claim-verdicts td {{ vertical-align: top; }}
        table.claim-verdicts td:nth-child(2) {{ max-width: 360px; }}
        table.claim-verdicts td:nth-child(5) {{ max-width: 320px; font-size: 0.92em; }}
        .footnote-block {{ background: #f7fafc; padding: 12px 16px; margin: 12px 0; border-left: 3px solid #2c5282; border-radius: 4px; }}
        .footnote-block h4 {{ margin-top: 0; color: #1a365d; }}
        .footnote-block li {{ margin: 4px 0; }}
        .vis-pill {{ display: inline-block; margin-left: 8px; padding: 1px 8px; font-size: 0.78em; color: #2d3748; background: #edf2f7; border: 1px solid #cbd5e0; border-radius: 9999px; vertical-align: middle; }}
        .vis-pass {{ margin: 14px 0; }}
        .vis-pass h4 {{ margin: 4px 0; color: #1a365d; }}
        .vis-bar {{ display: flex; height: 22px; border-radius: 6px; overflow: hidden; border: 1px solid #cbd5e0; background: #edf2f7; }}
        .vis-bar > div {{ color: white; font-size: 0.78em; line-height: 22px; text-align: center; overflow: hidden; }}
        .vis-bar-full {{ background: #38a169; }}
        .vis-bar-partial {{ background: #dd6b20; }}
        .vis-bar-obscured {{ background: #c53030; }}
        .vis-bar-unknown {{ background: #a0aec0; color: #2d3748; }}
        .vis-legend {{ font-size: 0.85em; color: #4a5568; margin-top: 6px; }}
        .vis-swatch {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; vertical-align: middle; margin-right: 2px; }}
        .vis-swatch-full {{ background: #38a169; }}
        .vis-swatch-partial {{ background: #dd6b20; }}
        .vis-swatch-obscured {{ background: #c53030; }}
        .vis-swatch-unknown {{ background: #a0aec0; }}
        .vis-conf-list {{ margin: 8px 0 8px 18px; }}
        .vis-windows {{ font-size: 0.92em; color: #2d3748; margin-top: 8px; }}
        .verbal-quotes {{ margin: 8px 0 12px 22px; }}
        .verbal-quotes li {{ margin: 6px 0; }}
        .verbal-fulltext {{ margin-top: 10px; }}
        .verbal-fulltext summary {{ cursor: pointer; color: #2c5282; font-weight: 600; }}
        .verbal-fulltext pre {{ background: #f7fafc; padding: 12px; border-radius: 6px; white-space: pre-wrap; font-family: Georgia, serif; font-size: 0.95em; max-height: 360px; overflow-y: auto; margin-top: 8px; }}
    </style>
</head>
<body>
    <h1>COMPREHENSIVE CME VIDEO ANALYSIS</h1>
    <table class="header-table">
        <tr><td><strong>Patient:</strong></td><td>{patient}</td></tr>
        <tr><td><strong>DOB:</strong></td><td>{dob}</td></tr>
        <tr><td><strong>Examiner:</strong></td><td>{examiner}</td></tr>
        <tr><td><strong>Date of CME:</strong></td><td>{exam_date}</td></tr>
        <tr><td><strong>Date of Injury:</strong></td><td>{injury_date}</td></tr>
        <tr><td><strong>Video Length:</strong></td><td>{video_len}</td></tr>
    </table>

    <div class="critical">
        <h2>MAIN ISSUES IDENTIFIED — CROSS-EXAMINATION FINDINGS</h2>
        <p class="cx-intro">Ranked most-damning first. Every finding pits a specific statement
        from the doctor&apos;s written report against timestamped video evidence.</p>
{crossexam_findings_html}
    </div>

    <h2>EXAMINATION TIMELINE OVERVIEW</h2>
    <table>
        <tr><th>Metric</th><th>Value</th><th>Standard</th></tr>
        <tr>
            <td>Physical Exam Window (observed tests)</td>
            <td><span class="timestamp">{ew.get('start', 'N/A')}</span> - <span class="timestamp">{ew.get('end', 'N/A')}</span></td>
            <td>N/A</td>
        </tr>
        <tr>
            <td>Approx. Hands-On Span</td>
            <td>~{ew.get('duration_seconds', 0) // 60} min {ew.get('duration_seconds', 0) % 60} sec</td>
            <td class="not-done">30-45 min typical for complex cases</td>
        </tr>
        <tr>
            <td>Goniometer/Inclinometer frames</td>
            <td class="not-done">{stats.get('goniometer_frames', 0)} / {nframes}</td>
            <td>Objective ROM requires instrumentation</td>
        </tr>
    </table>

    <h2>TIMESTAMPED EXAMINATION LOG</h2>
    <div class="test-log">
{log_html}
    </div>

{verdicts_table_html}

{legacy_fallback_html}

    <h2>BODY PART EXAMINATION TIMELINE</h2>
    <table>
        <tr><th>Body Part</th><th>First</th><th>Last</th><th>Tests</th><th>Frames</th></tr>
{body_rows}
    </table>

    <h2>EXAMINATION COMPONENTS OBSERVED</h2>
    <table>
        <tr><th>Test Type</th><th>Frames</th><th>First</th><th>Last</th></tr>
{test_table_rows()}
    </table>

    <h2>STANDARD OF CARE REFERENCES</h2>
    <div class="info">
        <h3>Range of motion</h3>
        <p>Objective ROM typically requires a goniometer or inclinometer, documented values, and comparison to reference norms (e.g., AMA Guides).</p>
    </div>

    <div class="summary-box">
        <h2>EXECUTIVE SUMMARY</h2>
        <p>Video length: {video_len}. This report prioritizes report-statement vs. video-timestamp crosswalk for deposition preparation. Counsel should correlate timestamps with the master recording.</p>
    </div>

{behavior_appendix_html}

{visibility_section_html}

{verbal_evidence_section_html}

{verdicts_footnotes_html}

    <hr>
    <p style="font-size: 0.85em; color: #666;">
        Analysis method: dual vision passes, ~{interval_sec}s frame interval.<br>
        Generated: {case_meta.get('generated', '')}<br>
        Run ID: {run_id or 'N/A'}<br>
        Bundle SHA-256: <code style="font-size: 0.9em;">{bundle_sha256 or 'not yet computed'}</code>
    </p>
</body>
</html>"""
    return html


def write_standard_reports(
    output_dir: Path,
    case_meta: Dict[str, Any],
    claims_path: Optional[Path],
    interval_sec: float,
) -> Tuple[Path, Optional[Path]]:
    """
    Read comprehensive_frame_analyses.json + behavior_analysis.json from default subdirs.
    Writes STANDARD_CME_REPORT.html and attempts STANDARD_CME_REPORT.pdf via Chrome.
    """
    comp_dir = output_dir / "comprehensive"
    beh_dir = output_dir / "behavior"
    comp_frames = _load_json(comp_dir / "comprehensive_frame_analyses.json") or []
    behavior = _load_json(beh_dir / "behavior_analysis.json")
    claims = _load_json(claims_path) if claims_path else {}
    # Prefer the merged verdicts written by analyze_cme_full; the
    # comprehensive-only verdicts were overwritten by that stage when
    # behavior data was available. Absent file -> verifier disabled.
    claim_verdicts = filter_medical_claim_verdicts(
        _load_json(comp_dir / "claim_verdicts.json") or []
    )

    # ASR transcript (A3): when audio/transcript.json exists, the
    # VERBAL EVIDENCE section renders. Absent -> section is suppressed
    # entirely so we never emit an empty stub.
    transcript = _load_json(output_dir / "audio" / "transcript.json")
    three_way_ledger = _load_json(output_dir / "three_way_ledger.json")
    comprehensive_summary = (
        _load_json(comp_dir / "comprehensive_analysis.json")
        or _load_json(output_dir / "comprehensive_analysis.json")
    )

    merged, stats = merge_frame_rows(comp_frames, behavior, interval_sec)
    timeline = _build_timeline(merged, interval_sec)
    case_meta = dict(case_meta)
    case_meta["interval_sec"] = interval_sec
    html = build_standard_html(
        case_meta,
        merged,
        timeline,
        stats,
        claims,
        claim_verdicts=claim_verdicts,
        transcript=transcript,
        behavior_result=behavior,
        three_way_ledger=three_way_ledger,
        comprehensive_summary=comprehensive_summary,
    )

    html_path = output_dir / "STANDARD_CME_REPORT.html"
    html_path.write_text(html, encoding="utf-8")

    pdf_path: Optional[Path] = output_dir / "STANDARD_CME_REPORT.pdf"
    chrome_bin = None
    mac_chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if Path(mac_chrome).is_file():
        chrome_bin = mac_chrome
    else:
        for name in ("google-chrome", "chromium", "chrome"):
            chrome_bin = shutil.which(name)
            if chrome_bin:
                break
    if chrome_bin:
        proc = subprocess.run(
            [
                chrome_bin,
                "--headless",
                "--disable-gpu",
                f"--print-to-pdf={pdf_path}",
                "--no-pdf-header-footer",
                str(html_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0 or not pdf_path.exists():
            pdf_path = None
    else:
        pdf_path = None

    return html_path, pdf_path
