"""
Shared helpers for CME video analysis: duration probing, cost estimates, API retries.
"""

from __future__ import annotations

import json
import math
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable, Dict, List, Optional, TypeVar

T = TypeVar("T")

# New runs are OpenAI-first. Frame-by-frame vision runs thousands of calls per
# case, so the per-frame model dominates cost; use the cost-sensitive tier for
# frames, then escalate only the low-volume legal judgment step.
DEFAULT_AI_PROVIDER = "openai"
DEFAULT_OPENAI_VISION_MODEL = "gpt-5.6-luna"
DEFAULT_OPENAI_VERIFIER_MODEL = "gpt-6-astra"

# Anthropic ids are kept for explicit fallback runs and historical cost
# reconciliation.
DEFAULT_SONNET_MODEL = "claude-sonnet-5"

DEFAULT_VERIFIER_MODEL = "claude-opus-5"

# Case metadata keys that must never enter deposition crosswalk / claim verifier.
METADATA_CLAIM_IDS = frozenset(
    {
        "plaintiff",
        "patient",
        "patient_name",
        "plaintiff_name",
        "examiner",
        "examiner_name",
        "doctor",
        "doctor_name",
        "exam_date",
        "date_of_injury",
        "date_of_birth",
        "dob",
        "doi",
        "attorney",
        "attorney_name",
        "case_id",
        "report_context",
        "initial_ime_reference",
        "exam_time",
        "state",
        "video_length",
    }
)


def is_metadata_claim_id(claim_id: str) -> bool:
    """True when claim_id is case metadata, not a medical/exam assertion."""
    key = (claim_id or "").strip().lower().replace("-", "_")
    if not key:
        return True
    if key in METADATA_CLAIM_IDS:
        return True
    for prefix in ("plaintiff_", "patient_", "examiner_", "doctor_", "attorney_", "case_"):
        if key.startswith(prefix):
            return True
    return False


def filter_medical_claims(claims: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Drop metadata keys from a flat claims.json mapping."""
    return {
        str(k): v
        for k, v in (claims or {}).items()
        if not is_metadata_claim_id(str(k))
    }


def filter_medical_claim_verdicts(verdicts: Optional[List[Any]]) -> List[Any]:
    """Drop metadata rows from claim_verdicts output."""
    out: List[Any] = []
    for row in verdicts or []:
        cid = row.get("claim_id") if isinstance(row, dict) else getattr(row, "claim_id", "")
        if is_metadata_claim_id(str(cid or "")):
            continue
        out.append(row)
    return out

# half_second and max both sample one frame every 0.5s of video (~2 frames/s of timeline).
PRESET_INTERVALS = {"standard": 5.0, "high": 1.0, "max": 0.5, "half_second": 0.5}
# Approximate list pricing (USD per million tokens) when usage-based billing is applied
SONNET_INPUT_PER_MTOK = 3.0
SONNET_OUTPUT_PER_MTOK = 15.0
# Opus-tier pricing, used by the claim verifier stage.
OPUS_INPUT_PER_MTOK = 5.0
OPUS_OUTPUT_PER_MTOK = 25.0
DEFAULT_HEURISTIC_COST_PER_VISION_CALL = 0.005


def probe_video_duration_sec(video_path: str) -> float:
    """Return duration in seconds via ffprobe, or 0.0 on failure."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except (ValueError, TypeError):
        return 0.0


def total_video_duration_sec(video_paths: List[str]) -> float:
    return sum(probe_video_duration_sec(p) for p in video_paths)


def estimate_frame_count(duration_sec: float, interval_sec: float) -> int:
    """Upper-bound style estimate matching ffmpeg fps sampling (ceil)."""
    if interval_sec <= 0:
        return 0
    return int(math.ceil(duration_sec / interval_sec))


def estimate_full_analysis_cost_usd(
    video_paths: List[str],
    interval_sec: float,
    *,
    dual_vision_pass: bool = True,
    cost_per_vision_call: float = DEFAULT_HEURISTIC_COST_PER_VISION_CALL,
    transcript_word_count: int = 0,
    words_per_transcript_segment: int = 400,
    cost_per_transcript_segment: float = 0.01,
) -> dict:
    """
    Pre-flight cost estimate for analyze_cme_full style runs.
    """
    total_dur = total_video_duration_sec(video_paths)
    frames = estimate_frame_count(total_dur, interval_sec)
    passes = 2 if dual_vision_pass else 1
    vision_cost = frames * passes * cost_per_vision_call
    seg_count = (
        (transcript_word_count + words_per_transcript_segment - 1) // words_per_transcript_segment
        if transcript_word_count
        else 0
    )
    transcript_cost = seg_count * cost_per_transcript_segment if seg_count else 0.0
    return {
        "total_duration_sec": total_dur,
        "estimated_frames": frames,
        "vision_api_calls": frames * passes,
        "estimated_vision_cost_usd": vision_cost,
        "estimated_transcript_cost_usd": transcript_cost,
        "estimated_total_usd": vision_cost + transcript_cost,
    }


DEFAULT_HEURISTIC_COST_PER_CLAIM_VERDICT = 0.15
DEFAULT_HEURISTIC_COST_PER_RESEARCH_CALL = 0.01


def estimate_claim_verifier_cost_usd(
    claim_count: int,
    *,
    with_research: bool = False,
    cost_per_claim: float = DEFAULT_HEURISTIC_COST_PER_CLAIM_VERDICT,
    cost_per_research: float = DEFAULT_HEURISTIC_COST_PER_RESEARCH_CALL,
) -> dict:
    """Pre-flight cost estimate for text-only claim verifier runs."""
    claims = max(0, int(claim_count))
    llm_cost = claims * cost_per_claim
    research_cost = claims * cost_per_research if with_research else 0.0
    return {
        "claim_count": claims,
        "estimated_llm_cost_usd": llm_cost,
        "estimated_research_cost_usd": research_cost,
        "estimated_total_usd": llm_cost + research_cost,
    }


def usage_to_cost_usd(
    input_tokens: int,
    output_tokens: int,
    *,
    input_per_mtok: float = SONNET_INPUT_PER_MTOK,
    output_per_mtok: float = SONNET_OUTPUT_PER_MTOK,
) -> float:
    return (input_tokens * input_per_mtok + output_tokens * output_per_mtok) / 1_000_000.0


def add_message_usage_cost(
    total_cost_holder: Any,
    response: Any,
    *,
    fallback_usd: float,
    attr_name: str = "total_cost_usd",
) -> None:
    """Add API cost from response.usage if present; else add fallback_usd.

    Deprecated: prefer add_analyze_result_cost together with a VisionClient
    AnalyzeResult. Kept here for backwards compatibility with the audio /
    transcript code paths that still call the raw Anthropic messages API.
    """
    u = getattr(response, "usage", None)
    if u is not None:
        inp = getattr(u, "input_tokens", None)
        out = getattr(u, "output_tokens", None)
        if inp is not None and out is not None:
            setattr(
                total_cost_holder,
                attr_name,
                getattr(total_cost_holder, attr_name) + usage_to_cost_usd(inp, out),
            )
            return
    setattr(total_cost_holder, attr_name, getattr(total_cost_holder, attr_name) + fallback_usd)


def add_analyze_result_cost(
    result_obj: Any,
    analyze_result: Any,
    *,
    fallback_usd: float,
    cost_attr: str = "total_cost_usd",
    input_attr: str = "total_input_tokens",
    output_attr: str = "total_output_tokens",
) -> None:
    """Update result_obj with cost + token counts from a VisionClient AnalyzeResult.

    Mirrors the prior add_message_usage_cost behavior for the cost field
    (usage-driven when token counts are present, else fallback) but also
    tracks running input/output token totals so multi-vendor consensus and
    cost_actual.json reconciliation can rely on the same numbers.

    The AnalyzeResult is duck-typed (so this module avoids importing
    vision_client and creating a cycle): only `input_tokens`, `output_tokens`,
    and `usd_cost_estimate` attributes are read.
    """
    inp = int(getattr(analyze_result, "input_tokens", 0) or 0)
    out = int(getattr(analyze_result, "output_tokens", 0) or 0)

    if inp or out:
        usd = getattr(analyze_result, "usd_cost_estimate", None)
        if usd is None:
            usd = usage_to_cost_usd(inp, out)
        setattr(
            result_obj,
            cost_attr,
            getattr(result_obj, cost_attr, 0.0) + float(usd),
        )
        setattr(result_obj, input_attr, getattr(result_obj, input_attr, 0) + inp)
        setattr(result_obj, output_attr, getattr(result_obj, output_attr, 0) + out)
        return

    setattr(
        result_obj,
        cost_attr,
        getattr(result_obj, cost_attr, 0.0) + fallback_usd,
    )


def anthropic_call_with_retry(
    fn: Callable[[], T],
    *,
    max_retries: int = 8,
    base_delay_sec: float = 1.0,
) -> T:
    """
    Retry on rate limits (429) and transient server errors (529).
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            msg = str(e).lower()
            retryable = (
                "429" in msg
                or "rate_limit" in msg
                or "529" in msg
                or "overloaded" in msg
            )
            if not retryable or attempt == max_retries - 1:
                raise
            delay = base_delay_sec * (2**attempt)
            time.sleep(min(delay, 120.0))
    raise last_exc  # pragma: no cover


def cost_history_file() -> Path:
    d = Path.home() / ".cme_analysis"
    d.mkdir(parents=True, exist_ok=True)
    return d / "cost_history.jsonl"


def write_cost_actual_json(output_dir: str | Path, payload: Dict[str, Any]) -> Path:
    """Write post-run reconciliation to output_dir/cost_actual.json."""
    p = Path(output_dir)
    p.mkdir(parents=True, exist_ok=True)
    path = p / "cost_actual.json"
    out = {
        **payload,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return path


def append_cost_history(entry: Dict[str, Any]) -> None:
    """Append one JSON line for rolling calibration (under ~/.cme_analysis/)."""
    row = {**entry, "recorded_at": datetime.now(timezone.utc).isoformat()}
    hist = cost_history_file()
    with open(hist, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def run_claim_verifier_with_merged_observations(
    *,
    claims: Optional[Dict[str, Any]],
    frame_analyses: List[Any],
    behavior_observations: List[Any],
    verbal_observations: List[Any],
    vision_client: Any,
    output_dir: Path,
    max_workers: int = 4,
    model_id: Optional[str] = None,
    resume: bool = False,
    research_client: Any = None,
) -> List[Dict[str, Any]]:
    """Run the per-claim verifier against the merged observation set and
    write `claim_verdicts.json` to `output_dir`.

    When `resume` is True and `output_dir/claim_verdicts.json` already
    exists with the same number of frame_analyses + behavior_observations
    recorded in a sibling `claim_verdicts_meta.json`, the verifier is
    skipped (with a log line). This is a cheap correctness check, not a
    strict identity check, as described in roadmap step 2's resume
    hardening notes.

    Returns the verdict list as JSON-ready dicts (already round-tripped
    through `asdict`)."""

    # Import lazily so cme_analysis_utils does not depend on the
    # verifier module at import time (no cycle, easy testing).
    from dataclasses import asdict as _asdict
    from .cme_claim_verifier import verify_all_claims

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    claims = filter_medical_claims(claims)
    if not claims:
        return []

    verdicts_path = output_dir / "claim_verdicts.json"
    meta_path = output_dir / "claim_verdicts_meta.json"
    per_claim_checkpoint = output_dir / "claim_verdicts_checkpoint.jsonl"

    if resume and verdicts_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        if (
            int(meta.get("frame_count", -1)) == len(frame_analyses or [])
            and int(meta.get("behavior_count", -1))
            == len(behavior_observations or [])
            and int(meta.get("verbal_count", -1)) == len(verbal_observations or [])
        ):
            print(
                f"Resume: skipping claim verifier (already have "
                f"{verdicts_path.name} with matching counts)."
            )
            try:
                return filter_medical_claim_verdicts(
                    json.loads(verdicts_path.read_text(encoding="utf-8"))
                )
            except (OSError, json.JSONDecodeError):
                pass

    # Sibling check: even when the meta-path short-circuit cannot fire
    # (counts changed, meta missing, or read failure), the per-claim
    # checkpoint allows partial resume so previously-completed claims
    # don't burn a second model call.
    if resume and per_claim_checkpoint.exists():
        print(
            f"Resume: claim verifier will reuse "
            f"{per_claim_checkpoint.name} for already-completed claims."
        )

    verdicts = verify_all_claims(
        claims=claims,
        frame_analyses=frame_analyses,
        behavior_observations=behavior_observations,
        verbal_observations=verbal_observations,
        vision_client=vision_client,
        output_dir=output_dir,
        max_workers=max_workers,
        model_id=model_id,
        resume=resume,
        research_client=research_client,
    )

    meta_payload = {
        "frame_count": len(frame_analyses or []),
        "behavior_count": len(behavior_observations or []),
        "verbal_count": len(verbal_observations or []),
        "verdict_count": len(verdicts),
    }
    meta_path.write_text(
        json.dumps(meta_payload, indent=2, default=str), encoding="utf-8"
    )

    return [_asdict(v) for v in verdicts]


def median_cost_per_vision_call_usd(
    *,
    max_entries: int = 200,
) -> Optional[float]:
    """
    Median of (actual_total_usd / vision_api_calls) from recent history rows
    that include both fields. Returns None if insufficient data.
    """
    hist = cost_history_file()
    if not hist.exists():
        return None
    lines = hist.read_text(encoding="utf-8").splitlines()
    lines = lines[-max_entries:]
    ratios: List[float] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        actual = row.get("actual_total_usd")
        calls = row.get("vision_api_calls")
        if actual is None or not calls:
            continue
        try:
            ratios.append(float(actual) / float(calls))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
    if len(ratios) < 3:
        return None
    return float(median(ratios))
