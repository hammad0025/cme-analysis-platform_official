"""Deterministic search over the packaged Dr. Hunter reference index."""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, List


INDEX_FILENAME = "hunter_reference_index.json"
CONTEXT_HEADER = (
    "HUNTER CORPUS REFERENCES "
    "(retrieved standards/citations; use video/report evidence to decide facts):"
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}

SYNONYMS = {
    "rom": {"range", "motion", "goniometer", "inclinometer", "flexion", "extension"},
    "range": {"rom", "motion", "goniometer", "inclinometer"},
    "motion": {"rom", "range", "goniometer", "inclinometer"},
    "cervical": {"neck", "spine", "inclinometer", "goniometer"},
    "lumbar": {"low", "back", "spine", "inclinometer", "goniometer"},
    "strength": {"motor", "muscle", "resistance", "myotome", "5/5"},
    "motor": {"strength", "muscle", "myotome", "resistance"},
    "sensory": {"sensation", "dermatome", "pinprick", "vibration", "proprioception"},
    "sensation": {"sensory", "dermatome", "pinprick", "light", "touch"},
    "reflex": {"dtr", "deep", "tendon", "clonus", "babinski", "hoffmann"},
    "romberg": {"balance", "feet", "together", "eyes", "closed", "minute"},
    "palpation": {"palpate", "spasm", "tenderness", "pressure", "clothing"},
    "palpate": {"palpation", "spasm", "tenderness", "pressure"},
    "slr": {"straight", "leg", "raise", "lasegue"},
    "straight": {"slr", "leg", "raise"},
    "cranial": {"nerve", "olfactory", "eye", "pupil", "facial"},
    "waddell": {"nonorganic", "simulation", "tenderness"},
    "crps": {"rsd", "budapest", "temperature", "sudomotor"},
}


def _module_dir() -> Path:
    return Path(__file__).resolve().parent


@lru_cache(maxsize=2)
def load_hunter_reference_index(index_path: str | None = None) -> list[dict[str, Any]]:
    """Load packaged reference records. Returns an empty list if unavailable."""
    path = Path(index_path) if index_path else _module_dir() / INDEX_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    records = data.get("records") if isinstance(data, dict) else None
    return [r for r in records or [] if isinstance(r, dict)]


def _tokenize(text: str) -> list[str]:
    raw = re.findall(r"[a-zA-Z0-9]+(?:/[0-9]+)?", str(text or "").lower())
    return [t for t in raw if len(t) > 1 and t not in STOPWORDS]


def _expanded_terms(parts: Iterable[str]) -> list[str]:
    terms: list[str] = []
    for part in parts:
        terms.extend(_tokenize(part))
    expanded = set(terms)
    for term in list(expanded):
        expanded.update(SYNONYMS.get(term, set()))
    return sorted(expanded)


def _field_text(record: dict[str, Any], *fields: str) -> str:
    pieces: list[str] = []
    for field in fields:
        value = record.get(field)
        if isinstance(value, list):
            pieces.extend(str(v) for v in value)
        elif isinstance(value, dict):
            pieces.extend(str(v) for v in value.values())
        elif value is not None:
            pieces.append(str(value))
    return " ".join(pieces).lower()


def _score_record(record: dict[str, Any], terms: list[str], phrase_terms: list[str]) -> float:
    if not terms:
        return 0.0

    title = _field_text(record, "title", "source_file", "topic", "reference")
    tags = _field_text(record, "key_concepts", "category", "family")
    excerpt = _field_text(record, "excerpt")

    score = 0.0
    matched = 0
    for term in terms:
        term_score = 0.0
        if term in title:
            term_score += 7.0
        if term in tags:
            term_score += 5.0
        occurrences = excerpt.count(term)
        if occurrences:
            term_score += min(occurrences, 4) * 1.2
        if term_score:
            matched += 1
            score += term_score

    phrase = " ".join(t for t in phrase_terms if t not in STOPWORDS)
    haystack = f"{title} {tags} {excerpt}"
    if len(phrase) >= 8 and phrase in haystack:
        score += 12.0

    coverage = matched / max(len(set(terms)), 1)
    score *= 0.7 + coverage

    family = str(record.get("family") or "")
    if family == "hunter_methodology":
        score *= 1.25
    elif family == "hunter_supplemental":
        score *= 1.15
    elif family == "hunter_technique_index":
        score *= 0.85

    length = max(len(excerpt), 240)
    return score / math.log(length, 10)


def _public_citation(record: dict[str, Any]) -> dict[str, str]:
    citation = record.get("citation") if isinstance(record.get("citation"), dict) else {}
    return {
        "doi": str(citation.get("doi") or ""),
        "year": str(citation.get("year") or ""),
        "first_author": str(citation.get("first_author") or ""),
        "url": str(citation.get("url") or ""),
    }


def search_hunter_references(
    query: str,
    *,
    claim_id: str = "",
    test_name: str = "",
    max_results: int = 5,
    min_score: float = 1.0,
    index_path: str | None = None,
) -> list[dict[str, Any]]:
    """Return ranked Hunter reference records for a claim/test query."""
    query_parts = [claim_id, test_name, query]
    terms = _expanded_terms(query_parts)
    phrase_terms = _tokenize(" ".join(query_parts))

    ranked: list[tuple[float, dict[str, Any]]] = []
    for record in load_hunter_reference_index(index_path):
        score = _score_record(record, terms, phrase_terms)
        if score >= min_score:
            ranked.append((score, record))

    ranked.sort(key=lambda item: item[0], reverse=True)
    results: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for score, record in ranked:
        source_key = str(record.get("source_file") or record.get("title") or record.get("id"))
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        results.append(
            {
                "id": record.get("id"),
                "score": round(score, 3),
                "title": record.get("title", ""),
                "reference": record.get("reference", ""),
                "topic": record.get("topic", ""),
                "source_file": record.get("source_file", ""),
                "source_path": record.get("source_path", ""),
                "key_concepts": record.get("key_concepts", []),
                "citation": _public_citation(record),
                "excerpt": record.get("excerpt", ""),
            }
        )
        if len(results) >= max_results:
            break
    return results


def _trim(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "."


def format_hunter_reference_context(results: list[dict[str, Any]], *, max_chars: int = 2600) -> str:
    """Render search hits as concise prompt context."""
    if not results:
        return ""

    lines = [CONTEXT_HEADER]
    for item in results:
        source = item.get("source_file") or item.get("title") or "Hunter reference"
        ref = item.get("reference") or item.get("topic") or ""
        citation = item.get("citation") or {}
        cite_bits = []
        if citation.get("url"):
            cite_bits.append(citation["url"])
        elif citation.get("year"):
            cite_bits.append(f"year {citation['year']}")
        if citation.get("first_author"):
            cite_bits.append(citation["first_author"])

        prefix = f"- {source}"
        if ref:
            prefix += f" [{ref}]"
        if cite_bits:
            prefix += f" ({'; '.join(cite_bits[:2])})"
        lines.append(prefix)
        lines.append(f"  Excerpt: {_trim(item.get('excerpt'), 420)}")

    context = "\n".join(lines)
    if len(context) > max_chars:
        return context[: max_chars - 1].rstrip() + "."
    return context


def hunter_reference_context_for_claim(
    claim_id: str,
    claim_text: str,
    *,
    test_name: str = "",
    max_results: int = 4,
    max_chars: int = 2600,
) -> str:
    """Search and format Hunter references for a claim verifier/model prompt."""
    query = " ".join(str(x or "") for x in (claim_id, test_name, claim_text))
    results = search_hunter_references(
        query,
        claim_id=claim_id,
        test_name=test_name,
        max_results=max_results,
    )
    return format_hunter_reference_context(results, max_chars=max_chars)
