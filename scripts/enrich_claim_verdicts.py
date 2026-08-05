#!/usr/bin/env python3
"""Post-process claim_verdicts.json without re-running vision/LLM.

- Filter metadata claims
- Enrich from claims_atomic.json
- Populate video_shows from evidence
- Attach cross_examination blocks
- Score and rank main issues
- Merge three_way performed_not_reported rows
- Optionally regenerate STANDARD_CME_REPORT
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.lambda_functions.cme_analysis_utils import filter_medical_claim_verdicts
from backend.lambda_functions.cme_claim_verifier import Evidence, sanitize_claim_evidence
from backend.lambda_functions.cme_cross_examination import attach_cross_examination, load_research_cache
from backend.lambda_functions.cme_egregious_ranking import rank_main_issues, sort_all_findings


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_atomic_by_id(path: Path) -> Dict[str, Dict[str, Any]]:
    data = _load_json(path)
    claims = data.get("claims") if isinstance(data, dict) else data
    if not isinstance(claims, list):
        return {}
    return {str(c["claim_id"]): c for c in claims if isinstance(c, dict) and c.get("claim_id")}


def enrich_with_atomic(verdicts: List[Dict[str, Any]], atomic_by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for v in verdicts:
        row = dict(v)
        meta = atomic_by_id.get(str(row.get("claim_id") or ""), {})
        if meta.get("report_quote"):
            row["claim_text"] = meta["report_quote"]
        row["report_page"] = meta.get("report_page", row.get("report_page"))
        row["report_quote"] = meta.get("report_quote") or row.get("claim_text")
        row["report_section"] = meta.get("report_section", row.get("report_section"))
        row["test_name"] = meta.get("test_name", row.get("test_name"))
        row["deposition_prompt"] = meta.get("deposition_prompt", row.get("deposition_prompt"))
        out.append(row)
    return out


def video_shows_from_evidence(evidence: List[Any], *, claim_id: str = "", max_items: int = 2) -> str:
    from backend.lambda_functions.cme_evidence_quality import (
        clean_evidence_note_for_display,
        evidence_notes_are_usable,
    )

    parts: List[str] = []
    seen: set[str] = set()
    for ev in evidence:
        if len(parts) >= max_items:
            break
        notes = ""
        frame = ev if isinstance(ev, dict) else None
        if isinstance(ev, dict):
            notes = str(ev.get("notes") or ev.get("quote") or "").strip()
        if not evidence_notes_are_usable(notes, claim_id, frame=frame):
            continue
        cleaned = clean_evidence_note_for_display(notes, max_sentences=2)
        if not cleaned:
            continue
        key = cleaned[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(cleaned)
    return " ".join(parts)


def upgrade_verbal_contradictions(row: Dict[str, Any]) -> Dict[str, Any]:
    """Promote clear verbal/report mismatches to contradicted for main-issues ranking."""
    out = dict(row)
    if str(out.get("verdict") or "").lower() == "contradicted":
        return out
    quote = str(out.get("report_quote") or out.get("claim_text") or "").lower()
    combined = f"{out.get('reasoning', '')} {out.get('video_shows', '')}".lower()
    has_transcript = any(
        isinstance(ev, dict) and ev.get("kind") == "transcript_span"
        for ev in (out.get("evidence") or [])
    )

    if "5/5" in quote and "strength" in quote:
        verbal_hits = (
            "no leg strength",
            "leg weakness",
            "no leg",
            "atrophy",
            "walker",
            "cannot walk",
            "nothing",
            "hip atrophy",
        )
        if any(k in combined for k in verbal_hits) or has_transcript:
            out["verdict"] = "contradicted"
            out["confidence"] = max(float(out.get("confidence") or 0), 0.85)
            if not str(out.get("video_shows") or "").strip():
                out["video_shows"] = (
                    "Patient verbally denies lower extremity strength; video does not show "
                    "systematic 5/5 MMT of bilateral lower extremities."
                )
    return out


def enrich_verdicts(
    verdicts: List[Dict[str, Any]],
    *,
    atomic_by_id: Dict[str, Dict[str, Any]],
    frame_analyses: List[Any],
    three_way_ledger: Dict[str, Any] | None,
    research_cache: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    verdicts = filter_medical_claim_verdicts(verdicts)
    verdicts = enrich_with_atomic(verdicts, atomic_by_id)

    sanitized: List[Dict[str, Any]] = []
    for row in verdicts:
        v = dict(row)
        claim_id = str(v.get("claim_id") or "")
        claim_text = str(v.get("claim_text") or v.get("report_quote") or "")
        try:
            ev_list = [Evidence(**e) for e in (v.get("evidence") or []) if isinstance(e, dict)]
        except TypeError:
            ev_list = []
        v["evidence"] = [
            asdict(e)
            for e in sanitize_claim_evidence(
                ev_list,
                claim_id=claim_id,
                claim_text=claim_text,
                frame_analyses=frame_analyses,
            )
        ]
        if not str(v.get("video_shows") or "").strip():
            vs = video_shows_from_evidence(v["evidence"], claim_id=claim_id)
            if vs:
                v["video_shows"] = vs
            elif v.get("reasoning"):
                v["video_shows"] = str(v["reasoning"])[:400]
        v = upgrade_verbal_contradictions(v)
        sanitized.append(v)

    with_ce = attach_cross_examination(sanitized, research_cache)
    from backend.lambda_functions.cme_egregious_ranking import merge_three_way_issues, sort_all_findings

    merged = merge_three_way_issues(filter_medical_claim_verdicts(with_ce), three_way_ledger)
    # Re-attach cross-examination for any three_way rows (Hoffmann/Babinski literature refs).
    existing_ids = {str(v.get("claim_id") or "") for v in with_ce}
    extra_rows = [r for r in merged if str(r.get("claim_id") or "") not in existing_ids]
    if extra_rows:
        with_ce = with_ce + attach_cross_examination(extra_rows, research_cache)
        merged = merge_three_way_issues(with_ce, three_way_ledger)
    return sort_all_findings(merged, three_way_ledger=None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich claim_verdicts without LLM re-run")
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=REPO_ROOT / "cme_projects/Deshefy_Alan/analysis_run",
    )
    parser.add_argument(
        "--atomic-claims",
        type=Path,
        default=REPO_ROOT / "cme_projects/Deshefy_Alan/claims_atomic.json",
    )
    parser.add_argument("--session-id", default="cme_89f184bd4e80")
    parser.add_argument(
        "--app-base-url",
        default="https://cme-analysis-platform-official.vercel.app",
    )
    parser.add_argument("--regenerate-report", action="store_true")
    parser.add_argument("--interval-sec", type=float, default=0.5)
    args = parser.parse_args()

    analysis_dir = args.analysis_dir.resolve()
    comp_dir = analysis_dir / "comprehensive"
    verdicts_path = comp_dir / "claim_verdicts.json"
    if not verdicts_path.is_file():
        raise SystemExit(f"Missing {verdicts_path}")

    verdicts = _load_json(verdicts_path)
    if not isinstance(verdicts, list):
        raise SystemExit("claim_verdicts.json must be a list")

    atomic_by_id = load_atomic_by_id(args.atomic_claims) if args.atomic_claims.is_file() else {}
    frames_path = comp_dir / "comprehensive_frame_analyses.json"
    frame_analyses = _load_json(frames_path) if frames_path.is_file() else []
    three_way_path = analysis_dir / "three_way_ledger.json"
    three_way = _load_json(three_way_path) if three_way_path.is_file() else None
    research_cache = load_research_cache(comp_dir / "research_cache.json")

    enriched = enrich_verdicts(
        verdicts,
        atomic_by_id=atomic_by_id,
        frame_analyses=frame_analyses or [],
        three_way_ledger=three_way,
        research_cache=research_cache,
    )
    verdicts_path.write_text(json.dumps(enriched, indent=2, default=str) + "\n", encoding="utf-8")

    main_issues = rank_main_issues(enriched, three_way_ledger=three_way)
    print(f"Wrote {verdicts_path} ({len(enriched)} verdicts, metadata filtered)")
    print(f"Main issues ({len(main_issues)}):")
    for issue in main_issues:
        print(
            f"  [{issue.get('issue_type_label')}] {issue.get('test_name') or issue.get('claim_id')} "
            f"score={issue.get('egregious_score')}"
        )

    if args.regenerate_report:
        from backend.lambda_functions.cme_report_builder import write_standard_reports

        claims_path = args.atomic_claims.parent / "claims.json"
        case_meta = {
            "patient": "Deshefy, Alan",
            "examiner": "Dr. Juan Agudelo",
            "exam_date": "2026-02-11",
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "session_id": args.session_id,
            "app_base_url": args.app_base_url,
        }
        html_path, pdf_path = write_standard_reports(
            analysis_dir, case_meta, claims_path if claims_path.is_file() else None, args.interval_sec
        )
        print(f"Regenerated report: {html_path}")
        if pdf_path:
            print(f"PDF: {pdf_path}")


if __name__ == "__main__":
    main()
