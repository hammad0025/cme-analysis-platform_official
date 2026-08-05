"""
Perplexity Sonar client for supplemental CME / neurological exam research.

Used during claim verification to ground verdicts in published examination
standards (e.g., ROM technique, reflex grading). Video evidence always
takes precedence; Perplexity output is advisory context only.
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()


DEFAULT_PERPLEXITY_MODEL = "sonar"
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_PROMPT_VERSION = "1.0.0"


@dataclass
class ResearchResult:
    claim_id: str
    query: str
    summary: str
    citations: List[str] = field(default_factory=list)
    model_id: str = DEFAULT_PERPLEXITY_MODEL
    latency_ms: int = 0
    error: str = ""


class PerplexityClient:
    """Thin wrapper around Perplexity's OpenAI-compatible chat API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        model_id: str = DEFAULT_PERPLEXITY_MODEL,
        timeout_sec: float = 45.0,
        request_delay_sec: float = 0.25,
    ):
        self.api_key = (api_key or os.environ.get("PERPLEXITY_API_KEY") or "").strip()
        self.model_id = model_id
        self.timeout_sec = timeout_sec
        self.request_delay_sec = request_delay_sec
        self._last_request_at = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _throttle(self) -> None:
        if self.request_delay_sec <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.request_delay_sec:
            time.sleep(self.request_delay_sec - elapsed)

    def research_for_claim(self, claim_id: str, claim_text: str) -> ResearchResult:
        """Return brief standards context for a single report claim."""
        if not self.enabled:
            return ResearchResult(
                claim_id=claim_id,
                query="",
                summary="",
                error="PERPLEXITY_API_KEY not configured",
            )

        topic = (claim_text or claim_id or "neurological examination").strip()[:400]
        query = (
            "For an independent medical examination (IME/CME) of a personal-injury "
            f"patient, what are the accepted clinical standards and common documentation "
            f"expectations for this reported finding or test? Be concise (3-5 sentences). "
            f"Cite authoritative sources when possible.\n\n"
            f"Claim ({claim_id}): {topic}"
        )

        self._throttle()
        started = time.monotonic()
        payload = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a medical-legal research assistant. Answer briefly with "
                        "evidence-based clinical standards. Do not speculate about this "
                        "specific patient."
                    ),
                },
                {"role": "user", "content": query},
            ],
            "temperature": 0.1,
            "max_tokens": 450,
        }
        req = urllib.request.Request(
            PERPLEXITY_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout_sec, context=_SSL_CONTEXT
            ) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            self._last_request_at = time.monotonic()
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                err_body = str(e)
            return ResearchResult(
                claim_id=claim_id,
                query=query,
                summary="",
                model_id=self.model_id,
                latency_ms=int((time.monotonic() - started) * 1000),
                error=f"HTTP {e.code}: {err_body[:300]}",
            )
        except Exception as e:
            return ResearchResult(
                claim_id=claim_id,
                query=query,
                summary="",
                model_id=self.model_id,
                latency_ms=int((time.monotonic() - started) * 1000),
                error=f"{type(e).__name__}: {e}",
            )

        summary = _extract_message_content(body)
        citations = _extract_citations(body)
        return ResearchResult(
            claim_id=claim_id,
            query=query,
            summary=summary.strip(),
            citations=citations,
            model_id=str(body.get("model") or self.model_id),
            latency_ms=int((time.monotonic() - started) * 1000),
        )


def _extract_message_content(body: Dict[str, Any]) -> str:
    choices = body.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


def _extract_citations(body: Dict[str, Any]) -> List[str]:
    citations = body.get("citations")
    if isinstance(citations, list):
        return [str(c).strip() for c in citations if str(c).strip()]
    return []


def load_research_cache(path: Optional[str]) -> Dict[str, dict]:
    if not path:
        return {}
    try:
        from pathlib import Path

        p = Path(path)
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_research_cache(path: Optional[str], cache: Dict[str, dict]) -> None:
    if not path:
        return
    try:
        from pathlib import Path

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def format_research_context(result: ResearchResult) -> str:
    """Format a ResearchResult for injection into the claim verifier prompt."""
    if result.error:
        return ""
    if not result.summary:
        return ""
    lines = [result.summary.strip()]
    if result.citations:
        cites = ", ".join(result.citations[:5])
        lines.append(f"Sources: {cites}")
    return "\n".join(lines).strip()[:1200]
