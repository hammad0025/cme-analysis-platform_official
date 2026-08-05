#!/usr/bin/env python3
"""
Run the text-only per-claim verifier against an existing local analysis run.

Loads frame analyses, behavior observations, and claims.json — then calls
run_claim_verifier_with_merged_observations (same path as analyze_cme_full.py
phase 3.5). Does NOT re-run vision frame analysis.

Requires CME_ALLOW_LOCAL_ANALYSIS=1 (unless --force). LLM verdicts need
ANTHROPIC_API_KEY (~$0.025/claim heuristic; 11 claims ≈ $0.28). Perplexity
research is opt-in via --with-research (~+$0.01/claim). Max typical spend for
Osborne sample: ~$0.50 LLM + ~$0.15 research. Use --dry-run to preview counts.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.lambda_functions.cme_analysis_utils import filter_medical_claims


def _format_timestamp(sec: float) -> str:
    total = max(0, int(sec))
    return f"{total // 60}:{total % 60:02d}"

DEFAULT_ANALYSIS_DIR = REPO_ROOT / "cme_projects/osborn_2021_03/analysis_run_halfsec"
DEFAULT_CLAIMS = REPO_ROOT / "cme_projects/osborn_2021_03/claims.json"
DEFAULT_ATOMIC_CLAIMS = REPO_ROOT / "cme_projects/osborn_2021_03/claims_atomic.json"
DEFAULT_SAMPLE_OUT = REPO_ROOT / "frontend/public/sample-case/claim_verdicts.json"
DEFAULT_SAMPLE_ATOMIC_OUT = REPO_ROOT / "frontend/public/sample-case/claims_atomic.json"
DEFAULT_TRANSCRIPT_SESSION = "cme_6f506df9ebf9"
DEFAULT_BUCKET = "cme-analysis-recordings-388846700527"
ALLOW_LOCAL_ENV = "CME_ALLOW_LOCAL_ANALYSIS"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _download_transcript(
    session_id: str,
    dest: Path,
    *,
    bucket: str,
    region: str,
) -> Optional[Path]:
    """Best-effort transcript fetch for logging / future use."""
    try:
        import boto3
    except ImportError:
        print("boto3 not installed; skipping S3 transcript download.")
        return None

    key = f"cme-transcripts/{session_id}/transcript_0.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        boto3.client("s3", region_name=region).download_file(bucket, key, str(dest))
        print(f"Downloaded transcript s3://{bucket}/{key} -> {dest}")
        return dest
    except Exception as exc:
        print(f"Could not download transcript ({exc})")
        return None


def _load_behavior_observations(behavior_dir: Path) -> tuple[list, list]:
    summary_path = behavior_dir / "behavior_summary.json"
    analysis_path = behavior_dir / "behavior_analysis.json"

    if analysis_path.is_file():
        data = _load_json(analysis_path)
        visual = list(data.get("visual_observations") or [])
        verbal = list(data.get("verbal_observations") or [])
        return visual, verbal

    if summary_path.is_file():
        data = _load_json(summary_path)
        visual = list(data.get("visual_observations") or [])
        verbal = list(data.get("verbal_observations") or [])
        return visual, verbal

    return [], []


def _load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def load_atomic_claims(path: Path) -> Dict[str, Dict[str, Any]]:
    data = _load_json(path)
    claims = data.get("claims") if isinstance(data, dict) else data
    if not isinstance(claims, list):
        return {}
    return {str(c["claim_id"]): c for c in claims if isinstance(c, dict) and c.get("claim_id")}


def claims_dict_from_atomic(atomic_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for cid, meta in atomic_by_id.items():
        out[cid] = meta.get("report_quote") or meta.get("test_name") or cid
    return out


def enrich_verdicts_with_atomic(
    verdicts: List[Dict[str, Any]],
    atomic_by_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
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
        if meta and row.get("claim_payload") in (None, "", row.get("claim_id")):
            row["claim_payload"] = meta
        enriched.append(row)
    return enriched


def _video_shows_from_evidence(
    evidence: List[Any],
    *,
    claim_id: str = "",
    max_items: int = 2,
) -> str:
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
        else:
            notes = str(getattr(ev, "notes", "") or getattr(ev, "quote", "") or "").strip()
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
    return " ".join(parts) if parts else ""


def _check_local_gate(*, force: bool) -> None:
    if force:
        return
    if os.environ.get(ALLOW_LOCAL_ENV) != "1":
        print("\n" + "=" * 60, file=sys.stderr)
        print("REFUSED: Local claim verifier is disabled by default.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(
            f"Set {ALLOW_LOCAL_ENV}=1 to enable (~$0.025/claim LLM; use --dry-run first).",
            file=sys.stderr,
        )
        print("Or pass --force to bypass (not recommended).", file=sys.stderr)
        raise SystemExit(1)


def _has_api_key() -> bool:
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )


def run_offline_heuristic_verifier(
    claims: Dict[str, Any],
    frame_analyses: List[Any],
    behavior_observations: List[Any],
    verbal_observations: List[Any],
) -> List[Dict[str, Any]]:
    """Keyword-matched offline verdicts when no LLM key is available (demo / CI)."""
    from dataclasses import asdict

    from backend.lambda_functions.cme_claim_verifier import (
        CLAIM_VERIFIER_PROMPT_VERSION,
        ClaimVerdict,
        Evidence,
        relevant_observations,
    )
    from backend.lambda_functions.cme_evidence_quality import (
        cluster_evidence_timestamps,
        clean_evidence_note_for_display,
        evidence_description_for_frame,
        evidence_notes_are_usable,
        filter_frames_for_claim,
        select_evidence_frames_for_claim,
    )

    verdicts: List[Dict[str, Any]] = []
    for claim_id, payload in (claims or {}).items():
        claim_text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
        matched = filter_frames_for_claim(frame_analyses, claim_id, claim_text)
        frames = select_evidence_frames_for_claim(
            matched, claim_id, claim_text, max_frames=4
        )
        behavior = relevant_observations(
            claim_id, claim_text, behavior_observations, max_items=5
        )
        verbal = relevant_observations(claim_id, claim_text, verbal_observations, max_items=5)

        evidence: List[Evidence] = []
        for fa in frames:
            ts = fa.get("timestamp_sec") if isinstance(fa, dict) else getattr(fa, "timestamp_sec", None)
            fid = fa.get("frame_id") if isinstance(fa, dict) else getattr(fa, "frame_id", None)
            desc = evidence_description_for_frame(fa, claim_id)
            raw_notes = fa.get("notes") if isinstance(fa, dict) else getattr(fa, "notes", "")
            notes = desc or clean_evidence_note_for_display(str(raw_notes or ""), max_sentences=2)
            if not notes:
                continue
            if not evidence_notes_are_usable(notes, claim_id, frame=fa):
                continue
            evidence.append(
                Evidence(
                    kind="frame",
                    frame_id=str(fid) if fid else None,
                    timestamp_sec=float(ts) if ts is not None else None,
                    notes=notes,
                )
            )

        stamps = cluster_evidence_timestamps(frames, max_stamps=4)
        ts_list = ", ".join(_format_timestamp(ts) for ts in stamps)
        video_shows = _video_shows_from_evidence(evidence, claim_id=claim_id)

        if not frames and not behavior and not verbal:
            verdict = "not_shown"
            confidence = 0.55
            reasoning = (
                "No corresponding examination moment appears on the deposition video for this report statement."
            )
            evidence = []
            video_shows = "Not shown on video"
        elif frames and stamps:
            verdict = "insufficient_evidence"
            confidence = 0.45
            reasoning = (
                f"Video at {ts_list} shows activity that may relate to this report statement. "
                "Cross-examination should require the doctor to identify the exact test performed."
            )
            if not video_shows:
                video_shows = f"Activity observed at {ts_list}; technique and completeness need deposition follow-up."
        elif frames and not stamps:
            verdict = "insufficient_evidence"
            confidence = 0.4
            reasoning = (
                "Some frames matched keywords but failed evidence quality gates; deposition should "
                "require the doctor to identify the exact test performed."
            )
            evidence = []
            video_shows = "No clear examination timestamp on video."
        elif not frames and (behavior or verbal):
            verdict = "insufficient_evidence"
            confidence = 0.4
            reasoning = (
                "Transcript or behavior cues may relate to this claim, but no clear video timestamp was identified."
            )
            if not video_shows:
                video_shows = "No clear examination timestamp on video."
        else:
            verdict = "not_shown"
            confidence = 0.55
            reasoning = (
                "No corresponding examination moment appears on the deposition video for this report statement."
            )
            evidence = []
            video_shows = "Not shown on video"

        row = asdict(
            ClaimVerdict(
                claim_id=str(claim_id),
                claim_text=claim_text,
                claim_payload=payload,
                verdict=verdict,
                confidence=confidence,
                reasoning=reasoning,
                evidence=evidence,
                model_id="offline-heuristic",
                provider="offline",
                prompt_version=CLAIM_VERIFIER_PROMPT_VERSION,
            )
        )
        row["video_shows"] = video_shows
        verdicts.append(row)

    verdicts.sort(key=lambda v: str(v.get("claim_id") or ""))
    return verdicts


def print_summary(verdicts: List[Dict[str, Any]]) -> None:
    counts = Counter((v.get("verdict") or "insufficient_evidence") for v in verdicts)
    print("\nClaim verdict summary:")
    for label in (
        "supported",
        "partially_supported",
        "contradicted",
        "not_shown",
        "insufficient_evidence",
    ):
        print(f"  {label}: {counts.get(label, 0)}")
    print(f"  total: {len(verdicts)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run claim vs video verifier on local analysis")
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=DEFAULT_ANALYSIS_DIR,
        help="Local analysis run directory (halfsec Osborne default)",
    )
    parser.add_argument(
        "--claims",
        type=Path,
        default=None,
        help="claims.json path (legacy flat claims file)",
    )
    parser.add_argument(
        "--atomic-claims",
        type=Path,
        default=DEFAULT_ATOMIC_CLAIMS,
        help="claims_atomic.json path (preferred; 11 deposition rows)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for claim_verdicts.json (default: analysis-dir/comprehensive)",
    )
    parser.add_argument(
        "--sample-out",
        type=Path,
        default=DEFAULT_SAMPLE_OUT,
        help="Copy verdicts JSON to frontend sample-case bundle",
    )
    parser.add_argument(
        "--transcript-session",
        default=DEFAULT_TRANSCRIPT_SESSION,
        help="Session id for S3 transcript download",
    )
    parser.add_argument(
        "--transcript-local",
        type=Path,
        help="Local transcript JSON path (skips S3)",
    )
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--model", help="Override vision model id")
    parser.add_argument("--resume", action="store_true", help="Reuse checkpoint / meta skip")
    parser.add_argument(
        "--force",
        action="store_true",
        help=f"Bypass {ALLOW_LOCAL_ENV} gate",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load inputs and print counts without calling the LLM",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use keyword heuristic verdicts (no LLM); auto-selected when no API key",
    )
    parser.add_argument(
        "--with-research",
        action="store_true",
        help=(
            "Opt-in Perplexity Sonar research per claim (~+$0.01/claim). "
            "Requires PERPLEXITY_API_KEY; never auto-enabled."
        ),
    )
    parser.add_argument(
        "--no-sample",
        action="store_true",
        help="Skip copying verdicts/atomic claims into frontend/public/sample-case (use for non-Osborne cases)",
    )
    args = parser.parse_args()

    _load_dotenv()
    _check_local_gate(force=args.force)

    analysis_dir = args.analysis_dir.resolve()
    comp_dir = analysis_dir / "comprehensive"
    behavior_dir = analysis_dir / "behavior"
    out_dir = (args.out_dir or comp_dir).resolve()

    frames_path = comp_dir / "comprehensive_frame_analyses.json"
    if not frames_path.is_file():
        raise SystemExit(f"Frame analyses not found: {frames_path}")

    atomic_by_id: Dict[str, Dict[str, Any]] = {}
    claims_path = args.claims
    if args.atomic_claims and args.atomic_claims.is_file():
        atomic_by_id = load_atomic_claims(args.atomic_claims)
        claims = claims_dict_from_atomic(atomic_by_id)
        print(f"Atomic claims: {len(claims)} from {args.atomic_claims}")
    elif claims_path and claims_path.is_file():
        claims = _load_json(claims_path)
        print(f"Legacy claims: {len(claims)} from {claims_path}")
    else:
        fallback = DEFAULT_CLAIMS
        if not fallback.is_file():
            raise SystemExit(
                f"No claims found. Expected {args.atomic_claims} or {fallback}"
            )
        claims = _load_json(fallback)
        print(f"Legacy claims: {len(claims)} from {fallback}")

    claims = filter_medical_claims(claims)
    if atomic_by_id:
        atomic_by_id = {
            cid: meta for cid, meta in atomic_by_id.items() if cid in claims
        }

    frame_analyses = _load_json(frames_path)
    behavior_visual, behavior_verbal = _load_behavior_observations(behavior_dir)

    transcript_path = args.transcript_local
    if transcript_path is None:
        local_candidate = analysis_dir / "transcript_0.json"
        if local_candidate.is_file():
            transcript_path = local_candidate
        else:
            transcript_path = analysis_dir / "transcript_0.json"
            _download_transcript(
                args.transcript_session,
                transcript_path,
                bucket=args.bucket,
                region=args.region,
            )

    print(f"Analysis dir: {analysis_dir}")
    print(f"Frames: {len(frame_analyses)}")
    print(f"Behavior visual: {len(behavior_visual)}, verbal: {len(behavior_verbal)}")
    print(f"Claims: {len(claims)}")
    if transcript_path and transcript_path.is_file():
        print(f"Transcript: {transcript_path}")
    else:
        print("Transcript: not loaded (verifier uses behavior verbal observations)")

    if args.dry_run:
        from backend.lambda_functions.cme_analysis_utils import estimate_claim_verifier_cost_usd

        est = estimate_claim_verifier_cost_usd(
            len(claims), with_research=args.with_research
        )
        print("Dry run — skipping verifier.")
        print(f"  Claims: {est['claim_count']}")
        print(f"  Est. LLM USD: ${est['estimated_llm_cost_usd']:.2f}")
        if args.with_research:
            print(f"  Est. research USD: ${est['estimated_research_cost_usd']:.2f}")
        print(f"  Est. total USD: ${est['estimated_total_usd']:.2f}")
        return

    use_offline = args.offline or not _has_api_key()
    if use_offline:
        if not args.offline:
            print(
                "No vision API key — using offline keyword heuristic (--offline). "
                "Set ANTHROPIC_API_KEY for LLM verdicts.",
                file=sys.stderr,
            )
        verdicts = run_offline_heuristic_verifier(
            claims, frame_analyses, behavior_visual, behavior_verbal
        )
    else:
        from backend.lambda_functions.cme_analysis_utils import (
            estimate_claim_verifier_cost_usd,
            run_claim_verifier_with_merged_observations,
        )
        from backend.lambda_functions.perplexity_client import PerplexityClient
        from backend.lambda_functions.vision_client import (
            default_verifier_model_for,
            make_vision_client,
        )

        est = estimate_claim_verifier_cost_usd(
            len(claims), with_research=args.with_research
        )
        print(
            f"Cost estimate: {est['claim_count']} claims, "
            f"LLM ~${est['estimated_llm_cost_usd']:.2f}"
            + (
                f", research ~${est['estimated_research_cost_usd']:.2f}"
                if args.with_research
                else ""
            )
            + f", total ~${est['estimated_total_usd']:.2f}"
        )

        research_client = None
        if args.with_research:
            research_client = PerplexityClient()
            if not research_client.enabled:
                print(
                    "WARNING: --with-research set but PERPLEXITY_API_KEY missing; "
                    "continuing without Perplexity.",
                    file=sys.stderr,
                )
                research_client = None
            else:
                print("Perplexity research: enabled (opt-in).")

        provider = os.environ.get("CME_VISION_PROVIDER", "anthropic")
        client = make_vision_client(provider)
        # Verdicts are the legal judgement step and run tens of times per case,
        # so they default to the stronger Opus-tier model rather than the
        # per-frame vision default. --model still overrides.
        model_id = args.model or default_verifier_model_for(provider)

        print(f"Running claim verifier ({provider} / {model_id})…")
        verdicts = run_claim_verifier_with_merged_observations(
            claims=claims,
            frame_analyses=frame_analyses,
            behavior_observations=behavior_visual,
            verbal_observations=behavior_verbal,
            vision_client=client,
            output_dir=out_dir,
            max_workers=args.max_workers,
            model_id=model_id,
            resume=args.resume,
            research_client=research_client,
        )

    if atomic_by_id:
        verdicts = enrich_verdicts_with_atomic(verdicts, atomic_by_id)

    from backend.lambda_functions.cme_claim_verifier import Evidence, sanitize_claim_evidence

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
        sanitized.append(v)
    verdicts = sanitized

    # Attach the structured cross-examination block (leading question, report
    # citation, video finding, timestamps, literature refs). Uses sanitized
    # evidence for timestamps and the Perplexity research cache (if any run
    # produced one) for real citation URLs.
    from backend.lambda_functions.cme_cross_examination import (
        attach_cross_examination,
        load_research_cache,
    )

    research_cache = load_research_cache(out_dir / "research_cache.json")
    if not research_cache:
        research_cache = load_research_cache(comp_dir / "research_cache.json")
    verdicts = attach_cross_examination(verdicts, research_cache)
    ref_count = sum(
        len((v.get("cross_examination") or {}).get("literature_refs") or []) for v in verdicts
    )
    print(f"Cross-examination blocks attached ({ref_count} literature refs total).")

    out_dir.mkdir(parents=True, exist_ok=True)
    verdicts_path = out_dir / "claim_verdicts.json"
    verdicts_path.write_text(json.dumps(verdicts, indent=2, default=str) + "\n", encoding="utf-8")
    meta_path = out_dir / "claim_verdicts_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "frame_count": len(frame_analyses),
                "behavior_count": len(behavior_visual),
                "verbal_count": len(behavior_verbal),
                "verdict_count": len(verdicts),
                "mode": "offline" if use_offline else "llm",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {verdicts_path} ({len(verdicts)} verdicts)")

    if args.sample_out and not args.no_sample:
        args.sample_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(verdicts_path, args.sample_out)
        print(f"Copied -> {args.sample_out}")

    if not args.no_sample and atomic_by_id and args.atomic_claims and args.atomic_claims.is_file():
        atomic_out = DEFAULT_SAMPLE_ATOMIC_OUT
        atomic_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.atomic_claims, atomic_out)
        print(f"Copied atomic claims -> {atomic_out}")

    print_summary(verdicts)


if __name__ == "__main__":
    main()
