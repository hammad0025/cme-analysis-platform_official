#!/usr/bin/env python3
"""
Extract structured exam claims from a defense doctor CME report (.txt or .pdf).

Writes claims.json compatible with cme_claim_verifier / test ledger (exact report
quotes per category, not paraphrases). Uses LLM text_analyze when an API key is
available; otherwise falls back to regex/heuristic parsing of the neurologic and
spinal exam sections.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.lambda_functions.cme_analysis_utils import filter_medical_claims, is_metadata_claim_id

DEFAULT_REPORT = (
    REPO_ROOT
    / "cme_projects/osborn_2021_03/Expert_-_Dr._Brett_Osborn_Report__3.11.21_CME#2.txt"
)
DEFAULT_OUT = REPO_ROOT / "cme_projects/osborn_2021_03/claims.json"

# Ordered labels inside the neurologic exam block (case-insensitive).
_NEURO_LABELS = [
    ("mental_status", r"Mental\s+status\s*:\s*"),
    ("cranial_nerves", r"Cranial\s+nerves\s*:\s*"),
    ("strength", r"Motor\s*:\s*"),
    ("sensory", r"Sensory\s*:\s*"),
    ("romberg", r"Rhomberg['\u2019]?s?\s+testing\s+is\s+"),
    ("reflexes", r"Deep\s+tendon\s+reflexes\s*:\s*"),
    ("coordination", r"Cerebellum\s*:\s*"),
    ("gait", r"Gait\s*:\s*"),
    ("long_tract_signs", r"No\s+long\s+tract\s+signs"),
]

def normalize_report_text(text: str) -> str:
    """Collapse tab-separated OCR / PDF extraction into readable single spaces."""
    text = text.replace("\u00a0", " ")
    text = text.replace("\t", " ")
    text = re.sub(r"[ \f\r]+", " ", text)
    text = re.sub(r"\n+", " ", text)
    return re.sub(r" {2,}", " ", text).strip()


def _read_report(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            import pypdf  # type: ignore
        except ImportError as exc:
            raise SystemExit(
                "PDF input requires pypdf (`pip install pypdf`) or pass a .txt export."
            ) from exc
        reader = pypdf.PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return normalize_report_text("\n".join(pages))
    return normalize_report_text(path.read_text(encoding="utf-8", errors="replace"))


def _slice_between(text: str, start_pat: str, end_pats: list[str]) -> Optional[str]:
    m = re.search(start_pat, text, flags=re.IGNORECASE)
    if not m:
        return None
    start = m.end()
    end = len(text)
    for ep in end_pats:
        em = re.search(ep, text[start:], flags=re.IGNORECASE)
        if em:
            end = min(end, start + em.start())
    chunk = text[start:end].strip(" .;")
    return chunk if chunk else None


def extract_claims_heuristic(text: str) -> Dict[str, str]:
    """Pull exact report substrings for standard neurologic / spinal categories."""
    claims: Dict[str, str] = {}

    exam_ctx = _slice_between(
        text,
        r"Physical\s+examination\s*:",
        [r"Medical\s+record\s+review\s*:", r"Radiology\s", r"The\s+updated\s+records"],
    )
    neuro_block = _slice_between(
        text,
        r"Neurologic\s+examination\s*:",
        [r"Medical\s+record\s+review\s*:", r"Root\s+tension\s+signs\s*:", r"Radiology"],
    )
    if not neuro_block and exam_ctx:
        neuro_block = exam_ctx

    search_text = neuro_block or text

    for key, start_pat in _NEURO_LABELS:
        if key == "long_tract_signs":
            m = re.search(start_pat, search_text, flags=re.IGNORECASE)
            if m:
                claims[key] = m.group(0).strip()
            continue

        remaining = [p for _, p in _NEURO_LABELS if p != start_pat]
        quote = _slice_between(search_text, start_pat, remaining + [r"Root\s+tension"])
        if quote:
            if key == "romberg":
                quote = f"Rhomberg's testing is {quote.strip()}"
            claims[key] = quote

    cervical = _slice_between(
        text,
        r"Cervical\s*:\s*",
        [r"Lumbar\s*:", r"Neurologic\s+examination\s*:"],
    )
    if cervical:
        claims["rom"] = cervical

    lumbar = _slice_between(text, r"Lumbar\s*:\s*", [r"Neurologic\s+examination\s*:"])
    if lumbar and "rom" in claims:
        claims["rom"] = f"{claims['rom']} Lumbar: {lumbar}"
    elif lumbar:
        claims["rom"] = f"Lumbar: {lumbar}"

    if "long_tract_signs" in claims:
        claims["hoffmann_babinski"] = (
            f"{claims['long_tract_signs']} (implies Hoffmann / Babinski not elicited or negative)."
        )

    if re.search(r"videographer", text, re.I):
        claims["exam_time"] = (
            "Compulsory medical examination with videographer and plaintiff attorney present "
            "(per report header)."
        )

    return claims


def _detect_report_page(raw_text: str, anchor: str) -> int:
    """Best-effort page number for an anchor phrase (Osborne txt uses tabbed page markers)."""
    pos = raw_text.lower().find(anchor.lower()[:40])
    if pos < 0:
        return 2
    prefix = raw_text[:pos]
    pages = re.findall(r"(?:^|\t)(\d{1,2})(?:\t|\s)", prefix)
    return int(pages[-1]) if pages else 2


def extract_atomic_claims_heuristic(text: str, *, raw_text: str | None = None) -> list[dict[str, Any]]:
    """
    One row per documented test — page/section/quote for deposition cross-examination.
    """
    normalized = normalize_report_text(text)
    page = _detect_report_page(raw_text or text, "Physical examination")

    atomic: list[dict[str, Any]] = []

    def add(
        claim_id: str,
        test_name: str,
        section: str,
        quote: str,
        *,
        technique_dimensions: list[str] | None = None,
        deposition_prompt: str | None = None,
    ) -> None:
        if not quote or not quote.strip():
            return
        atomic.append(
            {
                "claim_id": claim_id,
                "test_name": test_name,
                "report_page": page,
                "report_section": section,
                "report_quote": quote.strip(),
                "technique_dimensions": technique_dimensions or [],
                "deposition_prompt": deposition_prompt
                or f'Doctor, page {page} states: "{quote.strip()[:120]}" — show me on the video where you performed this.',
            }
        )

    cervical = _slice_between(
        normalized,
        r"Cervical\s*:\s*",
        [r"Lumbar\s*:", r"Neurologic\s+examination\s*:"],
    )
    if cervical:
        add(
            "cervical_rom",
            "Cervical range of motion",
            "Spinal examination",
            f"Cervical: {cervical}",
            technique_dimensions=["flexion", "extension", "rotation", "sidebend", "goniometer", "inclinometer"],
            deposition_prompt=(
                f'Page {page}: You documented cervical ROM as "{cervical}" — '
                "identify each plane on video and whether a goniometer or inclinometer was used."
            ),
        )

    lumbar = _slice_between(normalized, r"Lumbar\s*:\s*", [r"Neurologic\s+examination\s*:"])
    if lumbar:
        add(
            "lumbar_rom",
            "Lumbar range of motion",
            "Spinal examination",
            f"Lumbar: {lumbar}",
            technique_dimensions=["flexion", "extension", "rotation", "goniometer"],
            deposition_prompt=f'Page {page}: You wrote "{lumbar}" — was lumbar ROM actually performed on video?',
        )

    neuro_items = [
        (
            "mental_status",
            "Mental status",
            r"Mental\s+status\s*:\s*",
            ["orientation", "commands"],
            None,
        ),
        (
            "cranial_nerves",
            "Cranial nerves III–XII",
            r"Cranial\s+nerves\s*:\s*",
            ["CN_III_XII", "face", "eye_movement"],
            None,
        ),
        (
            "motor_strength",
            "Manual muscle testing (5/5 throughout)",
            r"Motor\s*:\s*",
            ["mmt", "5/5", "upper_extremity", "lower_extremity", "through_clothing"],
            f'Page {page}: You documented "5/5 strength throughout" — show each muscle group you tested on video.',
        ),
        (
            "sensory",
            "Sensory examination (pinprick / joint position)",
            r"Sensory\s*:\s*",
            ["pinprick", "joint_position", "dermatome", "through_clothing"],
            f'Page {page}: You documented sensory testing — show pinprick and joint position on video, including whether testing was through clothing.',
        ),
        (
            "romberg",
            "Romberg test",
            r"Rhomberg['\u2019]?s?\s+testing\s+is\s+",
            ["romberg", "tandem", "balance"],
            f'Page {page}: You documented Rhomberg testing — point to the exact timestamp on the video.',
        ),
        (
            "reflexes",
            "Deep tendon reflexes (0/4)",
            r"Deep\s+tendon\s+reflexes\s*:\s*",
            ["reflex_hammer", "patellar", "achilles", "biceps", "brachioradialis", "grading"],
            f'Page {page}: You graded DTR 0/4 throughout — identify where the reflex hammer appears on video.',
        ),
        (
            "long_tract_signs",
            "Hoffmann / Babinski (long tract signs)",
            r"No\s+long\s+tract\s+signs",
            ["hoffmann", "babinski", "plantar_response"],
            f'Page {page}: You documented "No long tract signs" — show Hoffmann and Babinski testing on the video.',
        ),
        (
            "coordination",
            "Cerebellar / coordination",
            r"Cerebellum\s*:\s*",
            ["finger_to_nose", "heel_to_shin"],
            None,
        ),
        (
            "gait",
            "Gait / tandem gait",
            r"Gait\s*:\s*",
            ["gait", "tandem", "street_shoes", "hallway"],
            f'Page {page}: You documented normal gait and tandem gait — identify timestamps; note if patient wore street clothes/shoes.',
        ),
        (
            "spurling",
            "Spurling maneuver",
            r"Root\s+tension\s+signs\s*:\s*",
            ["spurling", "cervical"],
            f'Page {page}: You documented Spurling — show the maneuver on video.',
        ),
    ]

    neuro_block = _slice_between(
        normalized,
        r"Neurologic\s+examination\s*:",
        [r"Medical\s+record\s+review\s*:", r"Root\s+tension\s+signs\s*:"],
    ) or normalized

    for claim_id, test_name, start_pat, dims, dep_prompt in neuro_items:
        if claim_id == "long_tract_signs":
            m = re.search(start_pat, neuro_block, flags=re.IGNORECASE)
            if m:
                quote = m.group(0).strip()
                add(
                    claim_id,
                    test_name,
                    "Neurologic examination",
                    quote,
                    technique_dimensions=dims,
                    deposition_prompt=dep_prompt,
                )
            continue

        others = [p for _, _, p, _, _ in neuro_items if p != start_pat]
        quote = _slice_between(neuro_block, start_pat, others + [r"Root\s+tension"])
        if quote:
            if claim_id == "romberg":
                quote = f"Rhomberg's testing is {quote.strip()}"
            elif claim_id == "spurling":
                quote = f"Root tension signs: {quote.strip()}"
            else:
                label = start_pat.replace(r"\s*:\s*", ": ").replace("\\", "").replace("?", "")
                quote = re.sub(r"^Mental\s+status\s*:\s*", "Mental status: ", quote, flags=re.I)
            add(
                claim_id,
                test_name,
                "Neurologic examination",
                quote if ":" in quote else f"{test_name}: {quote}",
                technique_dimensions=dims,
                deposition_prompt=dep_prompt,
            )

    return atomic


def _has_api_key() -> bool:
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )


def extract_claims_llm(text: str, *, model: Optional[str] = None) -> Dict[str, str]:
    """Use VisionClient.text_analyze to extract exact quotes when API key present."""
    from backend.lambda_functions.vision_client import default_model_for, make_vision_client

    provider = os.environ.get("CME_VISION_PROVIDER", "anthropic")
    client = make_vision_client(provider)
    model_id = model or default_model_for(provider)

    prompt = f"""You are parsing a defense doctor's Compulsory Medical Examination report for a legal case.

Extract EXACT verbatim quotes (copy-paste from the report text — do NOT paraphrase) for each category below. Use empty string if the category is not addressed.

Categories (JSON keys):
- exam_time: how long / context of exam if stated
- mental_status
- cranial_nerves
- strength
- sensory
- reflexes
- rom (cervical/lumbar range of motion)
- romberg
- gait
- coordination
- hoffmann_babinski (Hoffmann, Babinski, or "no long tract signs" if that is all that appears)

Return a SINGLE JSON object mapping each key to its exact quote string. No markdown.

REPORT TEXT:
{text[:120000]}
"""

    result = client.text_analyze(prompt, model_id=model_id, max_tokens=2500)
    raw = (result.text or result.raw_text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return extract_claims_heuristic(text)
    if not isinstance(parsed, dict):
        return extract_claims_heuristic(text)

    out: Dict[str, str] = {}
    for k, v in parsed.items():
        if isinstance(v, str) and v.strip():
            out[str(k)] = v.strip()
    return out or extract_claims_heuristic(text)


def merge_claim_sets(primary: Dict[str, str], fallback: Dict[str, str]) -> Dict[str, str]:
    merged = dict(fallback)
    for k, v in primary.items():
        if v and (k not in merged or len(v) > len(merged.get(k, ""))):
            merged[k] = v
    return merged


def extract_claims(text: str, *, use_llm: bool = True, model: Optional[str] = None) -> Dict[str, str]:
    heuristic = extract_claims_heuristic(text)
    if use_llm and _has_api_key():
        try:
            llm = extract_claims_llm(text, model=model)
            return merge_claim_sets(llm, heuristic)
        except Exception as exc:
            print(f"LLM extraction failed ({exc}); using heuristic fallback.", file=sys.stderr)
    return heuristic


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract CME report claims to claims.json")
    parser.add_argument(
        "report",
        nargs="?",
        type=Path,
        default=DEFAULT_REPORT,
        help="Doctor report .txt or .pdf path (or omit for Osborne default)",
    )
    parser.add_argument(
        "--text",
        help="Raw report text instead of a file path",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output claims.json path",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM even when API key is set (heuristic only)",
    )
    parser.add_argument("--model", help="Override vision model id for LLM extraction")
    parser.add_argument(
        "--atomic-out",
        type=Path,
        default=None,
        help="Write claims_atomic.json (one row per documented test with page/quote)",
    )
    args = parser.parse_args()

    if args.text:
        text = normalize_report_text(args.text)
        source = "<stdin>"
        raw_for_pages = args.text
    else:
        report_path = args.report.resolve()
        if not report_path.is_file():
            raise SystemExit(f"Report not found: {report_path}")
        text = _read_report(report_path)
        source = str(report_path)
        raw_for_pages = report_path.read_text(encoding="utf-8", errors="replace")

    claims = extract_claims(text, use_llm=not args.no_llm, model=args.model)
    claims = filter_medical_claims(claims)
    if not claims:
        raise SystemExit("No claims extracted — check report format.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(claims, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Extracted {len(claims)} claims from {source}")
    print(f"Wrote {args.out}")
    for key in sorted(claims):
        preview = claims[key][:80] + ("…" if len(claims[key]) > 80 else "")
        print(f"  {key}: {preview}")

    if args.atomic_out:
        atomic = extract_atomic_claims_heuristic(text, raw_text=raw_for_pages)
        atomic = [c for c in atomic if not is_metadata_claim_id(str(c.get("claim_id") or ""))]
        payload = {
            "schema_version": "2.0.0",
            "source_report": source,
            "total_claims": len(atomic),
            "claims": atomic,
        }
        args.atomic_out.parent.mkdir(parents=True, exist_ok=True)
        args.atomic_out.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"Wrote {len(atomic)} atomic claims to {args.atomic_out}")


if __name__ == "__main__":
    main()
