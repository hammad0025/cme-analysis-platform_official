"""Tests for the provider-agnostic VisionClient abstraction.

No tests in this file make real network calls; the Anthropic adapter is
exercised via a monkey-patched fake SDK that returns a canned response.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.lambda_functions.cme_analysis_utils import DEFAULT_SONNET_MODEL
from backend.lambda_functions.vision_client import (
    AnalyzeResult,
    AnthropicVisionClient,
    PROVIDER_PRICING,
    VisionClient,
    VisionClientConfigError,
    _estimate_cost_usd,
    make_vision_client,
)


def test_make_vision_client_anthropic_defaults(monkeypatch):
    """Anthropic factory returns AnthropicVisionClient with the expected defaults."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = make_vision_client("anthropic", api_key="sk-test")
    assert isinstance(client, AnthropicVisionClient)
    assert client.provider == "anthropic"
    assert client.default_model_id == DEFAULT_SONNET_MODEL


def test_make_vision_client_openai_missing_key_raises(monkeypatch):
    """OpenAI factory must raise a clear config error when no API key is available."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(VisionClientConfigError):
        make_vision_client("openai", api_key=None)


def test_provider_pricing_table_yields_positive_cost():
    """PROVIDER_PRICING lookups produce a positive cost estimate for known models."""
    inp, out = 1000, 500
    cost = _estimate_cost_usd("anthropic", DEFAULT_SONNET_MODEL, inp, out)
    assert cost is not None and cost > 0

    # Sanity-check at least one non-Anthropic entry too so step 2 has working priors.
    assert ("openai", "gpt-4o") in PROVIDER_PRICING
    assert ("gemini", "gemini-2.5-pro") in PROVIDER_PRICING


def test_anthropic_vision_client_happy_path(monkeypatch):
    """AnthropicVisionClient.analyze returns a populated AnalyzeResult and uses
    the shared anthropic_call_with_retry wrapper. No network call is made."""
    import anthropic
    import backend.lambda_functions.vision_client as vc

    real_retry = vc.anthropic_call_with_retry
    seen = {"called": False}

    def spy_retry(fn, **kwargs):
        seen["called"] = True
        return real_retry(fn, **kwargs)

    monkeypatch.setattr(vc, "anthropic_call_with_retry", spy_retry)

    class FakeUsage:
        def __init__(self, ip, op):
            self.input_tokens = ip
            self.output_tokens = op

    class FakeBlock:
        def __init__(self, text):
            self.text = text

    class FakeResponse:
        def __init__(self):
            self.id = "msg_test_123"
            self.usage = FakeUsage(1234, 567)
            self.content = [FakeBlock('{"hello":"world"}')]

    class FakeMessages:
        def __init__(self):
            self.last_kwargs = None

        def create(self, **kwargs):
            self.last_kwargs = kwargs
            return FakeResponse()

    class FakeAnthropic:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)

    client = AnthropicVisionClient(api_key="sk-test")
    assert isinstance(client, VisionClient)
    result = client.analyze(b"\x00\x01\x02", "prompt-text", max_tokens=900)

    assert isinstance(result, AnalyzeResult)
    assert result.text == '{"hello":"world"}'
    assert result.raw_text == '{"hello":"world"}'
    assert result.input_tokens == 1234
    assert result.output_tokens == 567
    assert result.model_id == DEFAULT_SONNET_MODEL
    assert result.provider == "anthropic"
    assert result.latency_ms >= 0
    assert result.request_id == "msg_test_123"
    assert result.usd_cost_estimate is not None and result.usd_cost_estimate > 0
    assert seen["called"], "anthropic_call_with_retry must wrap the API call"

    # Verify the call was shaped like the original analyzer expected:
    sent = client._client.messages.last_kwargs
    assert sent["model"] == DEFAULT_SONNET_MODEL
    assert sent["max_tokens"] == 900
    msg_content = sent["messages"][0]["content"]
    assert any(part.get("type") == "image" for part in msg_content)
    assert any(part.get("type") == "text" for part in msg_content)


def test_make_vision_client_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with pytest.raises(VisionClientConfigError):
        make_vision_client("bedrock", api_key="x")


def test_anthropic_vision_client_text_analyze_happy_path(monkeypatch):
    """text_analyze must reuse the same retry wrapper and shape its
    request payload with NO image content block (text-only). The verifier
    in step 2 depends on these properties."""
    import anthropic
    import backend.lambda_functions.vision_client as vc

    real_retry = vc.anthropic_call_with_retry
    seen = {"called": False}

    def spy_retry(fn, **kwargs):
        seen["called"] = True
        return real_retry(fn, **kwargs)

    monkeypatch.setattr(vc, "anthropic_call_with_retry", spy_retry)

    class FakeUsage:
        def __init__(self, ip, op):
            self.input_tokens = ip
            self.output_tokens = op

    class FakeBlock:
        def __init__(self, text):
            self.text = text

    class FakeResponse:
        def __init__(self):
            self.id = "msg_text_456"
            self.usage = FakeUsage(321, 21)
            self.content = [FakeBlock('{"verdict":"supported"}')]

    class FakeMessages:
        def __init__(self):
            self.last_kwargs = None

        def create(self, **kwargs):
            self.last_kwargs = kwargs
            return FakeResponse()

    class FakeAnthropic:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)

    client = AnthropicVisionClient(api_key="sk-test")
    result = client.text_analyze("prompt only, no image", max_tokens=800)

    assert isinstance(result, AnalyzeResult)
    assert result.text == '{"verdict":"supported"}'
    assert result.input_tokens == 321
    assert result.output_tokens == 21
    assert result.model_id == DEFAULT_SONNET_MODEL
    assert result.provider == "anthropic"
    assert result.usd_cost_estimate is not None and result.usd_cost_estimate > 0
    assert seen["called"], "anthropic_call_with_retry must wrap text_analyze too"

    sent = client._client.messages.last_kwargs
    assert sent["model"] == DEFAULT_SONNET_MODEL
    assert sent["max_tokens"] == 800
    msg_content = sent["messages"][0]["content"]
    # Critical: no image content block in a text-only call.
    assert all(part.get("type") != "image" for part in msg_content)
    assert any(part.get("type") == "text" for part in msg_content)


def test_text_analyze_missing_key_raises(monkeypatch):
    """An Anthropic client built without an API key must fail at construction
    time before any text_analyze call can be made."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(VisionClientConfigError):
        AnthropicVisionClient(api_key="")
