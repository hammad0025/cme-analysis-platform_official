"""
Provider-agnostic vision client abstraction for CME analysis.

Step 1 of the multi-vendor roadmap. Defines an `AnalyzeResult` payload, a
`VisionClient` ABC, and three concrete adapters (Anthropic, OpenAI, Gemini).
Anthropic remains the default; the other adapters only activate when the
caller passes `--providers openai|gemini` AND sets the matching env var.
Missing keys for opted-in providers raise `VisionClientConfigError` rather
than silently falling back.
"""

from __future__ import annotations

import base64
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

from .cme_analysis_utils import (
    DEFAULT_SONNET_MODEL,
    DEFAULT_VERIFIER_MODEL,
    OPUS_INPUT_PER_MTOK,
    OPUS_OUTPUT_PER_MTOK,
    SONNET_INPUT_PER_MTOK,
    SONNET_OUTPUT_PER_MTOK,
    anthropic_call_with_retry,
)

T = TypeVar("T")


SUPPORTED_PROVIDERS: Tuple[str, ...] = ("anthropic", "openai", "gemini")


class VisionClientConfigError(RuntimeError):
    """Raised when a vision client cannot be configured (missing key, bad provider)."""


# Approximate list pricing (USD per million tokens). Numbers are tracked here
# so cost reconciliation has a single source of truth across providers.
PROVIDER_PRICING: Dict[Tuple[str, str], Dict[str, float]] = {
    ("anthropic", DEFAULT_SONNET_MODEL): {
        "input_per_mtok": SONNET_INPUT_PER_MTOK,
        "output_per_mtok": SONNET_OUTPUT_PER_MTOK,
    },
    ("anthropic", DEFAULT_VERIFIER_MODEL): {
        "input_per_mtok": OPUS_INPUT_PER_MTOK,
        "output_per_mtok": OPUS_OUTPUT_PER_MTOK,
    },
    # Older ids kept so cost reconciliation of past runs stays accurate.
    ("anthropic", "claude-sonnet-4-5-20250929"): {
        "input_per_mtok": SONNET_INPUT_PER_MTOK,
        "output_per_mtok": SONNET_OUTPUT_PER_MTOK,
    },
    ("openai", "gpt-4o"): {"input_per_mtok": 2.5, "output_per_mtok": 10.0},
    ("openai", "gpt-4o-mini"): {"input_per_mtok": 0.15, "output_per_mtok": 0.60},
    ("gemini", "gemini-2.5-pro"): {"input_per_mtok": 1.25, "output_per_mtok": 10.0},
    ("gemini", "gemini-2.5-flash"): {"input_per_mtok": 0.075, "output_per_mtok": 0.30},
}


def _estimate_cost_usd(
    provider: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
) -> Optional[float]:
    price = PROVIDER_PRICING.get((provider, model_id))
    if not price:
        return None
    return (
        input_tokens * price["input_per_mtok"]
        + output_tokens * price["output_per_mtok"]
    ) / 1_000_000.0


@dataclass
class AnalyzeResult:
    """Vendor-agnostic vision API response payload."""

    text: str
    raw_text: str
    model_id: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    request_id: Optional[str] = None
    usd_cost_estimate: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class VisionClient(ABC):
    """Abstract vision client. Concrete subclasses wrap a specific vendor SDK."""

    provider: str = ""
    default_model_id: str = ""

    @abstractmethod
    def analyze(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        model_id: Optional[str] = None,
        max_tokens: int = 1500,
        mime_type: str = "image/jpeg",
    ) -> AnalyzeResult:
        """Analyze one image with the given text prompt. Must not raise on
        transient rate limits / 5xx errors (handled inside via retry wrapper)."""

    @abstractmethod
    def text_analyze(
        self,
        prompt: str,
        *,
        model_id: Optional[str] = None,
        max_tokens: int = 1500,
    ) -> AnalyzeResult:
        """Text-only analysis call (no image part). Used by downstream
        synthesis steps such as the per-claim verifier where there is
        nothing image-shaped to attach. Must reuse the same retry semantics
        as `analyze` and return the same AnalyzeResult shape."""


def openai_call_with_retry(
    fn: Callable[[], T],
    *,
    max_retries: int = 8,
    base_delay_sec: float = 1.0,
) -> T:
    """Retry helper for the OpenAI SDK. Modeled after anthropic_call_with_retry.

    Treats 429 rate limits, timeouts, connection errors, and 500-class server
    errors as transient. Uses duck-typed exception class names so this module
    does not need to import openai at the top level.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            cls = e.__class__.__name__.lower()
            msg = str(e).lower()
            retryable = (
                "ratelimit" in cls
                or "apitimeout" in cls
                or "apiconnection" in cls
                or "internalserver" in cls
                or "serviceunavailable" in cls
                or "429" in msg
                or "rate_limit" in msg
                or "rate limit" in msg
                or "500" in msg
                or "502" in msg
                or "503" in msg
                or "504" in msg
                or "timeout" in msg
            )
            if not retryable or attempt == max_retries - 1:
                raise
            delay = base_delay_sec * (2**attempt)
            time.sleep(min(delay, 120.0))
    raise last_exc  # pragma: no cover


def gemini_call_with_retry(
    fn: Callable[[], T],
    *,
    max_retries: int = 8,
    base_delay_sec: float = 1.0,
) -> T:
    """Retry helper for google-generativeai. Treats ResourceExhausted /
    ServiceUnavailable / DeadlineExceeded as transient."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            cls = e.__class__.__name__.lower()
            msg = str(e).lower()
            retryable = (
                "resourceexhausted" in cls
                or "serviceunavailable" in cls
                or "deadlineexceeded" in cls
                or "internalservererror" in cls
                or "internal" in cls
                or "429" in msg
                or "rate_limit" in msg
                or "503" in msg
                or "500" in msg
                or "timeout" in msg
            )
            if not retryable or attempt == max_retries - 1:
                raise
            delay = base_delay_sec * (2**attempt)
            time.sleep(min(delay, 120.0))
    raise last_exc  # pragma: no cover


class AnthropicVisionClient(VisionClient):
    """Adapter around anthropic.Anthropic. Default model is Claude Sonnet."""

    provider = "anthropic"
    default_model_id = DEFAULT_SONNET_MODEL

    def __init__(self, api_key: str, model_id: str = DEFAULT_SONNET_MODEL):
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - anthropic is required
            raise VisionClientConfigError(
                "anthropic package not installed. Run `pip install anthropic`."
            ) from e
        if not api_key:
            raise VisionClientConfigError(
                "Anthropic API key required (set ANTHROPIC_API_KEY)."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model_id = model_id or DEFAULT_SONNET_MODEL

    def analyze(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        model_id: Optional[str] = None,
        max_tokens: int = 1500,
        mime_type: str = "image/jpeg",
    ) -> AnalyzeResult:
        used_model = model_id or self._model_id
        image_data = base64.standard_b64encode(image_bytes).decode("utf-8")

        def _call():
            return self._client.messages.create(
                model=used_model,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": image_data,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

        t0 = time.perf_counter()
        response = anthropic_call_with_retry(_call)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        try:
            text = response.content[0].text or ""
        except Exception:
            text = ""

        usage = getattr(response, "usage", None)
        inp = int(getattr(usage, "input_tokens", 0) or 0) if usage is not None else 0
        out = int(getattr(usage, "output_tokens", 0) or 0) if usage is not None else 0
        request_id = getattr(response, "id", None)
        cost = (
            _estimate_cost_usd(self.provider, used_model, inp, out)
            if (inp or out)
            else None
        )

        return AnalyzeResult(
            text=text,
            raw_text=text,
            model_id=used_model,
            provider=self.provider,
            input_tokens=inp,
            output_tokens=out,
            latency_ms=latency_ms,
            request_id=request_id,
            usd_cost_estimate=cost,
            extra={},
        )

    def text_analyze(
        self,
        prompt: str,
        *,
        model_id: Optional[str] = None,
        max_tokens: int = 1500,
    ) -> AnalyzeResult:
        used_model = model_id or self._model_id

        def _call():
            return self._client.messages.create(
                model=used_model,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

        t0 = time.perf_counter()
        response = anthropic_call_with_retry(_call)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        try:
            text = response.content[0].text or ""
        except Exception:
            text = ""

        usage = getattr(response, "usage", None)
        inp = int(getattr(usage, "input_tokens", 0) or 0) if usage is not None else 0
        out = int(getattr(usage, "output_tokens", 0) or 0) if usage is not None else 0
        request_id = getattr(response, "id", None)
        cost = (
            _estimate_cost_usd(self.provider, used_model, inp, out)
            if (inp or out)
            else None
        )

        return AnalyzeResult(
            text=text,
            raw_text=text,
            model_id=used_model,
            provider=self.provider,
            input_tokens=inp,
            output_tokens=out,
            latency_ms=latency_ms,
            request_id=request_id,
            usd_cost_estimate=cost,
            extra={},
        )


class OpenAIVisionClient(VisionClient):
    """Adapter around the openai SDK (>=1.0). Default model is gpt-4o."""

    provider = "openai"
    default_model_id = "gpt-4o"

    def __init__(self, api_key: str, model_id: str = "gpt-4o"):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise VisionClientConfigError(
                "openai package not installed. Run `pip install 'openai>=1.40'`."
            ) from e
        if not api_key:
            raise VisionClientConfigError(
                "OpenAI API key required (set OPENAI_API_KEY)."
            )
        self._client = OpenAI(api_key=api_key)
        self._model_id = model_id or "gpt-4o"

    def analyze(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        model_id: Optional[str] = None,
        max_tokens: int = 1500,
        mime_type: str = "image/jpeg",
    ) -> AnalyzeResult:
        used_model = model_id or self._model_id
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64}"

        def _call():
            return self._client.chat.completions.create(
                model=used_model,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    }
                ],
            )

        t0 = time.perf_counter()
        response = openai_call_with_retry(_call)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        try:
            text = response.choices[0].message.content or ""
        except Exception:
            text = ""

        usage = getattr(response, "usage", None)
        inp = int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else 0
        out = (
            int(getattr(usage, "completion_tokens", 0) or 0) if usage is not None else 0
        )
        request_id = getattr(response, "id", None)
        cost = (
            _estimate_cost_usd(self.provider, used_model, inp, out)
            if (inp or out)
            else None
        )

        return AnalyzeResult(
            text=text,
            raw_text=text,
            model_id=used_model,
            provider=self.provider,
            input_tokens=inp,
            output_tokens=out,
            latency_ms=latency_ms,
            request_id=request_id,
            usd_cost_estimate=cost,
            extra={},
        )

    def text_analyze(
        self,
        prompt: str,
        *,
        model_id: Optional[str] = None,
        max_tokens: int = 1500,
    ) -> AnalyzeResult:
        used_model = model_id or self._model_id

        def _call():
            return self._client.chat.completions.create(
                model=used_model,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

        t0 = time.perf_counter()
        response = openai_call_with_retry(_call)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        try:
            text = response.choices[0].message.content or ""
        except Exception:
            text = ""

        usage = getattr(response, "usage", None)
        inp = int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else 0
        out = (
            int(getattr(usage, "completion_tokens", 0) or 0) if usage is not None else 0
        )
        request_id = getattr(response, "id", None)
        cost = (
            _estimate_cost_usd(self.provider, used_model, inp, out)
            if (inp or out)
            else None
        )

        return AnalyzeResult(
            text=text,
            raw_text=text,
            model_id=used_model,
            provider=self.provider,
            input_tokens=inp,
            output_tokens=out,
            latency_ms=latency_ms,
            request_id=request_id,
            usd_cost_estimate=cost,
            extra={},
        )


class GeminiVisionClient(VisionClient):
    """Adapter around google-generativeai. Default model is gemini-2.5-pro."""

    provider = "gemini"
    default_model_id = "gemini-2.5-pro"

    def __init__(self, api_key: str, model_id: str = "gemini-2.5-pro"):
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise VisionClientConfigError(
                "google-generativeai not installed. "
                "Run `pip install 'google-generativeai>=0.7'`."
            ) from e
        if not api_key:
            raise VisionClientConfigError(
                "Gemini API key required (set GOOGLE_API_KEY or GEMINI_API_KEY)."
            )
        genai.configure(api_key=api_key)
        self._genai = genai
        self._model_id = model_id or "gemini-2.5-pro"
        self._model = genai.GenerativeModel(self._model_id)

    def analyze(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        model_id: Optional[str] = None,
        max_tokens: int = 1500,
        mime_type: str = "image/jpeg",
    ) -> AnalyzeResult:
        used_model = model_id or self._model_id
        model_obj = (
            self._model
            if used_model == self._model_id
            else self._genai.GenerativeModel(used_model)
        )

        def _call():
            return model_obj.generate_content(
                [
                    {"mime_type": mime_type, "data": image_bytes},
                    prompt,
                ],
                generation_config={"max_output_tokens": max_tokens},
            )

        t0 = time.perf_counter()
        response = gemini_call_with_retry(_call)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        try:
            text = response.text or ""
        except Exception:
            try:
                text = response.candidates[0].content.parts[0].text or ""
            except Exception:
                text = ""

        meta = getattr(response, "usage_metadata", None)
        inp = (
            int(getattr(meta, "prompt_token_count", 0) or 0) if meta is not None else 0
        )
        out = (
            int(getattr(meta, "candidates_token_count", 0) or 0)
            if meta is not None
            else 0
        )
        cost = (
            _estimate_cost_usd(self.provider, used_model, inp, out)
            if (inp or out)
            else None
        )

        return AnalyzeResult(
            text=text,
            raw_text=text,
            model_id=used_model,
            provider=self.provider,
            input_tokens=inp,
            output_tokens=out,
            latency_ms=latency_ms,
            request_id=None,
            usd_cost_estimate=cost,
            extra={},
        )

    def text_analyze(
        self,
        prompt: str,
        *,
        model_id: Optional[str] = None,
        max_tokens: int = 1500,
    ) -> AnalyzeResult:
        used_model = model_id or self._model_id
        model_obj = (
            self._model
            if used_model == self._model_id
            else self._genai.GenerativeModel(used_model)
        )

        def _call():
            return model_obj.generate_content(
                [prompt],
                generation_config={"max_output_tokens": max_tokens},
            )

        t0 = time.perf_counter()
        response = gemini_call_with_retry(_call)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        try:
            text = response.text or ""
        except Exception:
            try:
                text = response.candidates[0].content.parts[0].text or ""
            except Exception:
                text = ""

        meta = getattr(response, "usage_metadata", None)
        inp = (
            int(getattr(meta, "prompt_token_count", 0) or 0) if meta is not None else 0
        )
        out = (
            int(getattr(meta, "candidates_token_count", 0) or 0)
            if meta is not None
            else 0
        )
        cost = (
            _estimate_cost_usd(self.provider, used_model, inp, out)
            if (inp or out)
            else None
        )

        return AnalyzeResult(
            text=text,
            raw_text=text,
            model_id=used_model,
            provider=self.provider,
            input_tokens=inp,
            output_tokens=out,
            latency_ms=latency_ms,
            request_id=None,
            usd_cost_estimate=cost,
            extra={},
        )


_PROVIDER_ENV: Dict[str, Tuple[str, ...]] = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "gemini": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
}


def _resolve_api_key(provider: str, explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    for var in _PROVIDER_ENV.get(provider, ()):
        v = os.environ.get(var)
        if v:
            return v
    env_list = " or ".join(_PROVIDER_ENV.get(provider, ()))
    raise VisionClientConfigError(
        f"Missing API key for provider {provider!r}. Set {env_list}."
    )


def default_verifier_model_for(provider: str) -> str:
    """Default model for the claim-verdict stage.

    Separate from `default_model_for` (per-frame vision): verdicts run tens of
    times per case rather than thousands, so the stronger Opus-tier model is
    worth its higher per-call cost there.
    """
    p = (provider or "").strip().lower()
    if p == "anthropic":
        return DEFAULT_VERIFIER_MODEL
    # Non-Anthropic providers have no separate verifier tier configured.
    return default_model_for(provider)


def default_model_for(provider: str) -> str:
    """Return the default model id used when none is specified for a provider."""
    p = (provider or "").strip().lower()
    if p == "anthropic":
        return DEFAULT_SONNET_MODEL
    if p == "openai":
        return "gpt-4o"
    if p == "gemini":
        return "gemini-2.5-pro"
    raise VisionClientConfigError(f"Unsupported provider {provider!r}")


def make_vision_client(
    provider: str,
    api_key: Optional[str] = None,
    model_id: Optional[str] = None,
) -> VisionClient:
    """Build a `VisionClient` for the given provider.

    Pulls the API key from the provider-specific env var when `api_key` is
    None. Raises `VisionClientConfigError` with a clear message when the key
    is missing or the provider is unknown -- no silent fallback to Anthropic.
    """
    p = (provider or "").strip().lower()
    if p not in SUPPORTED_PROVIDERS:
        raise VisionClientConfigError(
            f"Unsupported provider {provider!r}. Supported: {SUPPORTED_PROVIDERS}."
        )
    key = _resolve_api_key(p, api_key)
    if p == "anthropic":
        return AnthropicVisionClient(
            api_key=key, model_id=model_id or DEFAULT_SONNET_MODEL
        )
    if p == "openai":
        return OpenAIVisionClient(api_key=key, model_id=model_id or "gpt-4o")
    if p == "gemini":
        return GeminiVisionClient(
            api_key=key, model_id=model_id or "gemini-2.5-pro"
        )
    raise VisionClientConfigError(f"Unhandled provider {provider!r}")  # pragma: no cover
