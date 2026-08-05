"""Offline tests for backend.lambda_functions.perplexity_client."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.lambda_functions.perplexity_client import (  # noqa: E402
    PerplexityClient,
    format_research_context,
    load_research_cache,
    save_research_cache,
)


def test_client_disabled_without_key():
    client = PerplexityClient(api_key="")
    assert not client.enabled
    result = client.research_for_claim("rom", "Cervical ROM was normal.")
    assert result.error
    assert result.summary == ""


def test_format_research_context_includes_citations():
    from backend.lambda_functions.perplexity_client import ResearchResult

    result = ResearchResult(
        claim_id="rom",
        query="q",
        summary="Standard ROM requires goniometer.",
        citations=["https://example.com/a", "https://example.com/b"],
    )
    text = format_research_context(result)
    assert "goniometer" in text
    assert "Sources:" in text


@patch("urllib.request.urlopen")
def test_research_for_claim_parses_response(mock_urlopen):
    body = {
        "model": "sonar",
        "choices": [{"message": {"content": "Reflexes should be graded 0-4+."}}],
        "citations": ["https://example.com/reflex"],
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(body).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    client = PerplexityClient(api_key="pplx-test", request_delay_sec=0)
    result = client.research_for_claim("reflexes", "Deep tendon reflexes 2+ bilaterally.")
    assert "Reflexes" in result.summary
    assert result.citations == ["https://example.com/reflex"]
    assert not result.error


def test_research_cache_roundtrip(tmp_path):
    path = tmp_path / "research_cache.json"
    cache = {"rom": {"claim_id": "rom", "summary": "Use goniometer.", "citations": []}}
    save_research_cache(str(path), cache)
    loaded = load_research_cache(str(path))
    assert loaded["rom"]["summary"] == "Use goniometer."
