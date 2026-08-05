import json
from dataclasses import dataclass

from backend.lambda_functions.cme_analysis_utils import (
    add_analyze_result_cost,
    add_message_usage_cost,
    run_claim_verifier_with_merged_observations,
    write_cost_actual_json,
)


def test_write_cost_actual_json(tmp_path):
    p = write_cost_actual_json(
        tmp_path,
        {
            "estimated_total_usd": 10.0,
            "actual_total_usd": 9.5,
            "vision_api_calls": 100,
        },
    )
    assert p.name == "cost_actual.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["actual_total_usd"] == 9.5
    assert "recorded_at" in data


@dataclass
class _Holder:
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class _FakeUsage:
    def __init__(self, ip, op):
        self.input_tokens = ip
        self.output_tokens = op


class _FakeResponse:
    def __init__(self, ip, op):
        self.usage = _FakeUsage(ip, op)


def test_add_analyze_result_cost_matches_message_usage_cost():
    """Same input/output token counts must produce the same total cost
    whether we use the legacy add_message_usage_cost or the new helper.
    The new helper additionally tracks running token counts."""
    h_legacy = _Holder()
    h_new = _Holder()

    add_message_usage_cost(h_legacy, _FakeResponse(1000, 500), fallback_usd=0.10)

    # AnalyzeResult is duck-typed inside the helper; use a lightweight stub
    # rather than importing vision_client to keep this test isolated.
    class _StubResult:
        input_tokens = 1000
        output_tokens = 500
        usd_cost_estimate = None  # force usage_to_cost_usd path

    add_analyze_result_cost(h_new, _StubResult(), fallback_usd=0.10)

    assert abs(h_legacy.total_cost_usd - h_new.total_cost_usd) < 1e-9
    assert h_new.total_input_tokens == 1000
    assert h_new.total_output_tokens == 500


def test_add_analyze_result_cost_fallback_when_no_usage():
    """When the AnalyzeResult has no token counts, add_analyze_result_cost
    must increment total_cost_usd by exactly fallback_usd (matching the
    legacy semantics)."""
    holder = _Holder()

    class _Empty:
        input_tokens = 0
        output_tokens = 0
        usd_cost_estimate = None

    add_analyze_result_cost(holder, _Empty(), fallback_usd=0.015)
    assert holder.total_cost_usd == 0.015
    assert holder.total_input_tokens == 0
    assert holder.total_output_tokens == 0


def test_add_analyze_result_cost_uses_precomputed_estimate():
    """When AnalyzeResult.usd_cost_estimate is set (e.g. for non-Anthropic
    providers whose pricing tables differ), that value is used directly."""
    holder = _Holder()

    class _Result:
        input_tokens = 2000
        output_tokens = 1000
        usd_cost_estimate = 0.0123

    add_analyze_result_cost(holder, _Result(), fallback_usd=0.10)
    assert abs(holder.total_cost_usd - 0.0123) < 1e-9
    assert holder.total_input_tokens == 2000
    assert holder.total_output_tokens == 1000


class _StubVisionResult:
    def __init__(self, text):
        self.text = text
        self.raw_text = text
        self.model_id = "stub-model"
        self.provider = "stub"
        self.input_tokens = 10
        self.output_tokens = 5
        self.usd_cost_estimate = 0.0
        self.latency_ms = 1
        self.request_id = "r"
        self.extra = {}


class _StubVisionClient:
    provider = "stub"
    default_model_id = "stub-model"

    def __init__(self):
        self.calls = 0

    def text_analyze(self, prompt, *, model_id=None, max_tokens=1500):
        self.calls += 1
        return _StubVisionResult(
            json.dumps(
                {
                    "verdict": "not_shown",
                    "confidence": 0.5,
                    "reasoning": "stub",
                    "evidence": [],
                }
            )
        )


def test_run_claim_verifier_with_merged_observations_writes_meta_and_skips_on_resume(
    tmp_path,
):
    """The helper must write claim_verdicts.json + claim_verdicts_meta.json
    and, when resume=True, short-circuit on counter parity."""
    client = _StubVisionClient()

    result = run_claim_verifier_with_merged_observations(
        claims={"reflexes": "DTRs 2+"},
        frame_analyses=[{"frame_id": "f1", "timestamp_sec": 0.0}],
        behavior_observations=[],
        verbal_observations=[],
        vision_client=client,
        output_dir=tmp_path,
        max_workers=1,
        model_id=None,
        resume=False,
    )

    assert isinstance(result, list) and len(result) == 1
    assert client.calls == 1
    assert (tmp_path / "claim_verdicts.json").exists()
    assert (tmp_path / "claim_verdicts_meta.json").exists()

    meta = json.loads((tmp_path / "claim_verdicts_meta.json").read_text())
    assert meta["frame_count"] == 1
    assert meta["behavior_count"] == 0
    assert meta["verbal_count"] == 0

    # Resume with matching counts -> verifier must NOT call text_analyze again.
    result2 = run_claim_verifier_with_merged_observations(
        claims={"reflexes": "DTRs 2+"},
        frame_analyses=[{"frame_id": "f1", "timestamp_sec": 0.0}],
        behavior_observations=[],
        verbal_observations=[],
        vision_client=client,
        output_dir=tmp_path,
        max_workers=1,
        model_id=None,
        resume=True,
    )
    assert client.calls == 1, "resume must skip re-running the verifier"
    assert len(result2) == 1


def test_run_claim_verifier_with_merged_observations_empty_claims_noop(tmp_path):
    client = _StubVisionClient()
    out = run_claim_verifier_with_merged_observations(
        claims={},
        frame_analyses=[],
        behavior_observations=[],
        verbal_observations=[],
        vision_client=client,
        output_dir=tmp_path,
        max_workers=1,
    )
    assert out == []
    assert client.calls == 0
    # No artifacts when there are no claims -> preserves vanilla behavior.
    assert not (tmp_path / "claim_verdicts.json").exists()
    assert not (tmp_path / "claim_verdicts_meta.json").exists()
