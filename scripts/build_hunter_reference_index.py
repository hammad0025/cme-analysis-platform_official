#!/usr/bin/env python3
"""Build the compact Hunter reference index shipped with Lambda.

The raw Hunter PDF/DOCX corpus and large parser outputs stay out of git. This
script distills the parsed artifacts into short, citable records that production
code can search deterministically before prompting a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "backend/lambda_functions/hunter_reference_index.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _clean_text(value: Any, *, limit: int | None = None) -> str:
    text = str(value or "")
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip() + "."
    return text


def _repo_relative(path_value: Any) -> str:
    path = str(path_value or "").strip()
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except Exception:
        return path


def _sanitize_doi(value: Any) -> str:
    doi = str(value or "").strip().rstrip(".,;:)]}>")
    match = re.match(r"^(10\.\d{4,}/\S+)$", doi)
    return match.group(1) if match else ""


def _citation_url(citation: Any) -> str:
    if not isinstance(citation, dict):
        return ""
    doi = _sanitize_doi(citation.get("doi"))
    if doi:
        return f"https://doi.org/{doi}"
    url = str(citation.get("url") or "").strip()
    return url if url.startswith(("http://", "https://")) else ""


def _chunks(text: str, *, max_chars: int = 1500, overlap: int = 180) -> Iterable[str]:
    text = _clean_text(text)
    if not text:
        return
    if len(text) <= max_chars:
        yield text
        return

    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        split = max(text.rfind(". ", start, end), text.rfind("; ", start, end))
        if split > start + max_chars // 2:
            end = split + 1
        yield text[start:end].strip()
        if end >= len(text):
            break
        start = max(0, end - overlap)


def _record_id(*parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"href_{digest}"


def _make_record(
    *,
    family: str,
    title: str,
    text: str,
    source_file: str = "",
    source_path: str = "",
    reference: str = "",
    topic: str = "",
    category: str = "",
    key_concepts: Iterable[str] = (),
    citation: Any = None,
    chunk_index: int = 0,
) -> dict[str, Any]:
    citation_dict = citation if isinstance(citation, dict) else {}
    excerpt = _clean_text(text, limit=1800)
    source = _clean_text(source_file or title)
    return {
        "id": _record_id(family, source, str(chunk_index), excerpt[:240]),
        "family": family,
        "title": _clean_text(title or source),
        "reference": _clean_text(reference),
        "topic": _clean_text(topic),
        "category": _clean_text(category),
        "source_file": source,
        "source_path": _repo_relative(source_path),
        "key_concepts": sorted({_clean_text(c).lower() for c in key_concepts if _clean_text(c)}),
        "citation": {
            "doi": _sanitize_doi(citation_dict.get("doi")),
            "year": _clean_text(citation_dict.get("year")),
            "first_author": _clean_text(citation_dict.get("first_author")),
            "url": _citation_url(citation_dict),
        },
        "chunk_index": chunk_index,
        "excerpt": excerpt,
    }


def _add_hunter_docx_records(records: list[dict[str, Any]], kb: dict[str, Any], family: str) -> None:
    for doc in kb.get("documents") or []:
        if not isinstance(doc, dict):
            continue
        content = doc.get("content") or ""
        title = doc.get("topic") or doc.get("filename") or "Hunter methodology"
        for idx, chunk in enumerate(_chunks(str(content), max_chars=1500, overlap=160)):
            records.append(
                _make_record(
                    family=family,
                    title=title,
                    text=chunk,
                    source_file=doc.get("filename", ""),
                    source_path=doc.get("path", ""),
                    reference=str(doc.get("reference_letter") or ""),
                    topic=str(doc.get("topic") or ""),
                    chunk_index=idx,
                )
            )


def _iter_reference_documents(kb: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any], dict[str, Any]]]:
    for group_name in ("reference_materials", "subject_materials"):
        groups = kb.get(group_name) or {}
        if not isinstance(groups, dict):
            continue
        for category, group in groups.items():
            if not isinstance(group, dict):
                continue
            for doc in group.get("documents") or []:
                if isinstance(doc, dict):
                    yield group_name, group, {**doc, "_category": category}


def _add_reference_pdf_records(records: list[dict[str, Any]], kb: dict[str, Any]) -> None:
    seen: set[tuple[str, str]] = set()
    for group_name, group, doc in _iter_reference_documents(kb):
        summary = _clean_text(doc.get("summary"), limit=1800)
        if not summary:
            continue
        filename = _clean_text(doc.get("filename"))
        dedupe_key = (filename.lower(), summary[:260].lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        category = _clean_text(doc.get("_category") or group.get("name") or group_name)
        title = _clean_text(group.get("name") or category or filename)
        key_concepts = list(doc.get("key_concepts") or [])
        related = group.get("related_tests")
        if isinstance(related, list):
            key_concepts.extend(str(x) for x in related)

        records.append(
            _make_record(
                family="hunter_pdf_reference",
                title=title,
                text=summary,
                source_file=filename,
                source_path=doc.get("path", ""),
                reference=category,
                topic=_clean_text(group.get("description") or title),
                category=group_name,
                key_concepts=key_concepts,
                citation=doc.get("citation") or {},
            )
        )


def _add_exam_technique_records(records: list[dict[str, Any]], kb: dict[str, Any]) -> None:
    techniques = kb.get("exam_techniques") or {}
    if not isinstance(techniques, dict):
        return
    for key, value in techniques.items():
        if not isinstance(value, dict):
            continue
        sources = value.get("sources") or []
        source_text = "; ".join(str(s) for s in sources[:24])
        text = (
            f"Technique index for {value.get('name') or key}. "
            f"Relevant source documents: {source_text}"
        )
        records.append(
            _make_record(
                family="hunter_technique_index",
                title=value.get("name") or str(key),
                text=text,
                source_file=f"{key}.technique-index",
                reference="technique",
                topic=str(key),
                key_concepts=[str(key), *[str(s) for s in value.get("sources", [])[:6]]],
            )
        )


def build_index(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    records: list[dict[str, Any]] = []

    methodology = _read_json(repo_root / "hunter_methodology_knowledge_base.json")
    supplemental = _read_json(repo_root / "hunter_supplemental_knowledge_base.json")
    reference_kb = _read_json(repo_root / "cme_reference_knowledge_base.json")

    _add_hunter_docx_records(records, methodology, "hunter_methodology")
    _add_hunter_docx_records(records, supplemental, "hunter_supplemental")
    _add_reference_pdf_records(records, reference_kb)
    _add_exam_technique_records(records, reference_kb)

    records = sorted(records, key=lambda r: (r["family"], r["title"], r["source_file"], r["chunk_index"]))
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_artifacts": [
            "hunter_methodology_knowledge_base.json",
            "hunter_supplemental_knowledge_base.json",
            "cme_reference_knowledge_base.json",
        ],
        "record_count": len(records),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    index = build_index()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, indent=2, sort_keys=True, ensure_ascii=True), encoding="utf-8")
    print(f"Wrote {index['record_count']} Hunter reference records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
