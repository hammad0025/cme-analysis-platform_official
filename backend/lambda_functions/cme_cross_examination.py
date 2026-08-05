"""Cross-examination block builder + literature reference resolution.

Turns a claim verdict (verdict + evidence + timestamps) into the structured
deposition block Dorothy asked for:

    cross_examination: {
        leading_question,   # verdict-aware, courtroom-style
        report_citation,    # page + exact quote from the doctor's report
        video_finding,      # what the video actually shows
        timestamps: [{sec, label}],
        literature_refs: [{title, url, source}],
    }

Literature refs come from (in priority order):
1. Perplexity research citations cached in research_cache.json (real URLs)
2. DOI resolution for Dr. Hunter's parsed reference PDFs (doi.org links)
3. Known-source / StatPearls / PubMed search links for KB source filenames
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlparse

CROSS_EXAM_SCHEMA_VERSION = "1.0.0"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REFERENCE_KB_JSON = _REPO_ROOT / "cme_reference_knowledge_base.json"

# Explicit filename -> online source overrides for frequently cited materials.
KNOWN_SOURCE_URLS: Dict[str, Dict[str, str]] = {
    "sixthedition.pdf": {
        "title": "AMA Guides to the Evaluation of Permanent Impairment, 6th Edition",
        "url": "https://ama-guides.ama-assn.org/",
    },
    "ama 6th crps.pdf": {
        "title": "AMA Guides 6th Edition — CRPS Impairment",
        "url": "https://ama-guides.ama-assn.org/",
    },
}

_STOP_SUFFIXES = (
    "oregon hunter",
    "- copy",
    "(1)",
    "(2)",
)


def clean_reference_title(filename: str) -> str:
    """Human-readable title from a stored reference PDF filename."""
    name = (filename or "").strip()
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    name = name.replace("_", " ")
    lowered = name.lower()
    for suffix in _STOP_SUFFIXES:
        if lowered.endswith(suffix):
            name = name[: len(name) - len(suffix)]
            lowered = name.lower()
    name = re.sub(r"\s{2,}", " ", name).strip(" -–—.")
    return name


def _sanitize_doi(doi: str) -> str:
    """Validate a DOI; the PDF parser sometimes captures truncated suffixes."""
    doi = (doi or "").strip().rstrip(".,;)]}>")
    match = re.match(r"^10\.\d{4,}/(\S+)$", doi)
    if not match or len(match.group(1)) < 6:
        return ""
    return doi


_doi_map_cache: Optional[Dict[str, str]] = None


def load_doi_map(kb_json_path: Optional[Path] = None) -> Dict[str, str]:
    """filename (lowercased) -> DOI, from the parsed reference knowledge base.

    Best-effort: returns {} when the parsed KB JSON is not present (e.g. in
    Lambda), so callers fall back to search links.
    """
    global _doi_map_cache
    if _doi_map_cache is not None and kb_json_path is None:
        return _doi_map_cache

    path = kb_json_path or _REFERENCE_KB_JSON
    mapping: Dict[str, str] = {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        if kb_json_path is None:
            _doi_map_cache = {}
        return {}

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            fname = node.get("filename")
            citation = node.get("citation")
            if fname and isinstance(citation, dict) and citation.get("doi"):
                doi = _sanitize_doi(str(citation["doi"]))
                if doi:
                    mapping.setdefault(str(fname).strip().lower(), doi)
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data)
    if kb_json_path is None:
        _doi_map_cache = mapping
    return mapping


def resolve_reference_url(filename: str) -> Optional[Dict[str, str]]:
    """Resolve a local reference PDF filename to an online link.

    Returns {title, url, source} or None if the filename is unusable.
    """
    fname = (filename or "").strip()
    if not fname:
        return None
    key = fname.lower()
    title = clean_reference_title(fname)
    if not title:
        return None

    known = KNOWN_SOURCE_URLS.get(key)
    if known:
        return {"title": known["title"], "url": known["url"], "source": "known_source"}

    doi = load_doi_map().get(key)
    if doi:
        return {"title": title, "url": f"https://doi.org/{doi}", "source": "doi"}

    if "statpearls" in key or "ncbi bookshelf" in key or "clinical methods" in key:
        # StatPearls / Bookshelf chapter IDs aren't stored locally; a Bookshelf
        # search on the exact title reliably lands on the chapter.
        search_title = re.sub(r"\s*-\s*(statpearls|ncbi bookshelf).*$", "", title, flags=re.I).strip()
        return {
            "title": search_title or title,
            "url": f"https://www.ncbi.nlm.nih.gov/books/?term={quote_plus(search_title or title)}",
            "source": "ncbi_bookshelf",
        }

    return {
        "title": title,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(title)}",
        "source": "pubmed_search",
    }


def _title_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    host = (parsed.netloc or "").replace("www.", "")
    segment = ""
    for part in reversed((parsed.path or "").split("/")):
        part = part.strip()
        if part and not part.isdigit():
            segment = part
            break
    segment = re.sub(r"\.(html?|pdf|aspx?)$", "", segment, flags=re.I)
    segment = segment.replace("-", " ").replace("_", " ").strip()
    if segment and len(segment) > 3:
        return f"{segment.title()} ({host})"
    return host or url


def _refs_from_research_entry(entry: Dict[str, Any], max_refs: int = 4) -> List[Dict[str, str]]:
    refs: List[Dict[str, str]] = []
    seen: set = set()
    for url in list(entry.get("citations") or []):
        url = str(url).strip()
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        refs.append({"title": _title_from_url(url), "url": url, "source": "perplexity"})
        if len(refs) >= max_refs:
            break
    return refs


def _kb_source_filenames_for_claim(claim_id: str, claim_text: str = "") -> List[str]:
    """KB reference PDF filenames relevant to this claim (offline path)."""
    try:
        from .cme_claim_verifier import _CLAIM_HUNTER_KB_KEYS
        from .cme_comprehensive_knowledge_base import CME_COMPREHENSIVE_KNOWLEDGE_BASE
    except ImportError:
        from cme_claim_verifier import _CLAIM_HUNTER_KB_KEYS  # type: ignore
        from cme_comprehensive_knowledge_base import CME_COMPREHENSIVE_KNOWLEDGE_BASE  # type: ignore

    # Exam-KB key -> comprehensive-KB key where the vocabularies differ.
    aliases = {
        "hoffmanns_sign": "hoffmann_sign",
        "babinski_sign": "babinski_reflex",
        "gait_observation": "tandem_gait",
        "pinprick_sensation": "sensory_examination",
        "proprioception": "sensory_examination",
        "mental_status_exam": "mini_mental_status",
        "manual_muscle_testing": "manual_muscle_testing",
    }

    # Deshefy / deposition claim_id -> Hunter comprehensive KB keys for literature.
    claim_literature_keys: Dict[str, List[str]] = {
        "rom_left_knee": ["knee_rom"],
        "rom_right_knee": ["knee_rom"],
        "rom_right_toes": ["knee_rom"],
        "lower_extremity_strength": ["manual_muscle_testing"],
        "upper_extremity_strength": ["manual_muscle_testing"],
        "sensation": ["sensory_examination"],
        "skin": ["sensory_examination"],
        "skin_exam": ["sensory_examination"],
        "three_way_hoffmann_sign": ["hoffmann_sign"],
        "three_way_babinski_sign": ["babinski_reflex"],
    }

    cid = (claim_id or "").strip().lower()
    text = (claim_text or "").lower()
    keys: List[str] = list(claim_literature_keys.get(cid, []))
    keys.extend(_CLAIM_HUNTER_KB_KEYS.get(cid, []))
    if not keys:
        for map_cid, map_keys in _CLAIM_HUNTER_KB_KEYS.items():
            if map_cid and (map_cid in cid or cid in map_cid):
                keys.extend(map_keys)
    if not keys:
        if cid.startswith("rom_") or "range of motion" in text or "flexion contracture" in text:
            keys = ["knee_rom"]
        elif "strength" in cid or "5/5" in text or "muscle group" in text:
            keys = ["manual_muscle_testing"]
        elif "hoffmann" in cid or "hoffmann" in text:
            keys = ["hoffmann_sign"]
        elif "babinski" in cid or "babinski" in text:
            keys = ["babinski_reflex"]
        elif "sensation" in cid or "light touch" in text or "pinprick" in text:
            keys = ["sensory_examination"]
    filenames: List[str] = []
    for kb_key in dict.fromkeys(aliases.get(k, k) for k in keys):
        info = CME_COMPREHENSIVE_KNOWLEDGE_BASE.get(kb_key) or {}
        for fname in info.get("sources") or []:
            if fname not in filenames:
                filenames.append(fname)
    return filenames


def literature_refs_for_claim(
    claim_id: str,
    claim_text: str = "",
    research_entry: Optional[Dict[str, Any]] = None,
    max_refs: int = 4,
) -> List[Dict[str, str]]:
    """Perplexity citations first (real URLs), then resolved KB sources."""
    refs: List[Dict[str, str]] = []
    if isinstance(research_entry, dict):
        refs.extend(_refs_from_research_entry(research_entry, max_refs=max_refs))

    if len(refs) < max_refs:
        seen_urls = {r["url"] for r in refs}
        for fname in _kb_source_filenames_for_claim(claim_id, claim_text):
            resolved = resolve_reference_url(fname)
            if not resolved or resolved["url"] in seen_urls:
                continue
            seen_urls.add(resolved["url"])
            resolved = {**resolved, "source": resolved.get("source") or "hunter_kb"}
            refs.append(resolved)
            if len(refs) >= max_refs:
                break
    return refs


def format_timestamp(sec: float) -> str:
    total = max(0, int(sec))
    return f"{total // 60}:{total % 60:02d}"


def _short_quote(quote: str, limit: int = 180) -> str:
    q = " ".join(str(quote or "").split())
    if len(q) <= limit:
        return q
    return q[: limit - 1].rstrip() + "…"


def _timestamps_from_evidence(row: Dict[str, Any], max_stamps: int = 4) -> List[Dict[str, Any]]:
    secs: List[float] = []
    for ev in row.get("evidence") or []:
        ts = ev.get("timestamp_sec") if isinstance(ev, dict) else getattr(ev, "timestamp_sec", None)
        if ts is None:
            continue
        try:
            secs.append(float(ts))
        except (TypeError, ValueError):
            continue
    stamps: List[Dict[str, Any]] = []
    seen_labels: set = set()
    for s in sorted(dict.fromkeys(secs)):
        label = format_timestamp(s)
        if label in seen_labels:
            continue
        seen_labels.add(label)
        stamps.append({"sec": s, "label": label})
        if len(stamps) >= max_stamps:
            break
    return stamps


def _is_rom_claim(claim_id: str, claim_text: str = "") -> bool:
    cid = (claim_id or "").strip().lower()
    if cid.startswith("rom_") or "_rom" in cid:
        return True
    text = (claim_text or "").lower()
    return "range of motion" in text or "flexion contracture" in text


def build_leading_question(
    verdict: str,
    *,
    test_name: str,
    report_page: Optional[int],
    report_quote: str,
    first_ts_label: str = "",
    claim_id: str = "",
    deposition_prompt: str = "",
) -> str:
    page_ref = f"page {report_page} of your report" if report_page else "your report"
    quote = _short_quote(report_quote, limit=220)
    at_ts = f" at {first_ts_label}" if first_ts_label else ""
    test = test_name or "this test"
    custom = str(deposition_prompt or "").strip()

    v = (verdict or "").strip().lower()
    if v == "contradicted":
        if custom:
            return (
                f"{custom} The video{at_ts} shows the opposite of what you wrote — "
                "your report is inaccurate on this point, isn't it?"
            )
        return (
            f'Doctor, {page_ref} states "{quote}" — yet the video{at_ts} shows the opposite. '
            "Your report is inaccurate on this point, isn't it?"
        )
    if v == "not_shown":
        if custom:
            return custom
        return (
            f'Doctor, {page_ref} states "{quote}" — but you cannot point to anywhere on the '
            f"examination video where {test} was actually performed, can you?"
        )
    if v == "partially_supported":
        if _is_rom_claim(claim_id, report_quote):
            if custom:
                return (
                    f"{custom} On the video{at_ts}, was a goniometer visible for each plane "
                    "you measured, or were measurements taken in street clothes from a wheelchair?"
                )
            return (
                f'Doctor, {page_ref} documents specific ROM degrees for {test} ("{quote}") — '
                f"show each plane on the video{at_ts} and identify whether a goniometer was used."
            )
        if custom:
            return (
                f"{custom} The video{at_ts} does not show the complete documented examination — "
                f"you did not perform all of {test} as written, did you?"
            )
        return (
            f"Doctor, the video{at_ts} shows only part of what {page_ref} describes "
            f'("{quote}") — you did not perform the complete {test}, did you?'
        )
    if v == "performed_not_reported":
        if custom:
            return custom
        return (
            f"Doctor, the video{at_ts} shows {test} being performed, yet it appears nowhere in "
            "your written report — your report does not fully document your examination, does it?"
        )
    if v == "supported":
        return (
            f"Doctor, directing your attention to the video{at_ts} — that is the moment you "
            f"performed {test} as documented on {page_ref}, correct?"
        )
    # insufficient_evidence and anything else
    return (
        f'Doctor, {page_ref} states "{quote}". Nothing on the video clearly shows {test} '
        "performed to published standards — identify the exact moment, technique, and any "
        "instruments used, for the record."
    )


def build_cross_examination(
    row: Dict[str, Any],
    *,
    research_entry: Optional[Dict[str, Any]] = None,
    max_timestamps: int = 4,
) -> Dict[str, Any]:
    """Build the cross_examination block for one enriched verdict row."""
    claim_id = str(row.get("claim_id") or "")
    verdict = str(row.get("verdict") or "insufficient_evidence")
    test_name = str(row.get("test_name") or "").strip()
    report_quote = str(row.get("report_quote") or row.get("claim_text") or "").strip()
    report_page = row.get("report_page")

    timestamps = _timestamps_from_evidence(row, max_stamps=max_timestamps)
    first_label = timestamps[0]["label"] if timestamps else ""

    video_finding = str(row.get("video_shows") or "").strip()
    if not video_finding:
        for ev in row.get("evidence") or []:
            notes = str((ev or {}).get("notes") or "").strip() if isinstance(ev, dict) else ""
            if notes:
                video_finding = notes
                break
    if not video_finding and verdict == "not_shown":
        video_finding = "Not shown on video."

    citation = report_quote
    if report_page:
        citation = f'Page {report_page}: "{_short_quote(report_quote)}"'
    elif report_quote:
        citation = f'"{_short_quote(report_quote)}"'

    return {
        "schema_version": CROSS_EXAM_SCHEMA_VERSION,
        "leading_question": build_leading_question(
            verdict,
            test_name=test_name or claim_id.replace("_", " "),
            report_page=report_page,
            report_quote=report_quote,
            first_ts_label=first_label,
            claim_id=claim_id,
            deposition_prompt=str(row.get("deposition_prompt") or ""),
        ),
        "report_citation": citation,
        "video_finding": video_finding,
        "timestamps": timestamps,
        "literature_refs": literature_refs_for_claim(
            claim_id,
            claim_text=report_quote,
            research_entry=research_entry,
        ),
    }


def load_research_cache(path: Path) -> Dict[str, Dict[str, Any]]:
    """research_cache.json written by the claim verifier: claim_id -> entry."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def attach_cross_examination(
    verdicts: List[Dict[str, Any]],
    research_cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Attach a cross_examination block to every verdict row (in a copy)."""
    cache = research_cache or {}
    out: List[Dict[str, Any]] = []
    for row in verdicts:
        enriched = dict(row)
        entry = cache.get(str(enriched.get("claim_id") or ""))
        enriched["cross_examination"] = build_cross_examination(
            enriched, research_entry=entry if isinstance(entry, dict) else None
        )
        out.append(enriched)
    return out
