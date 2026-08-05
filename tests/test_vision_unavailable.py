"""Vision-unavailable handling must never fabricate a verdict.

The old fallback scored tests against Dr. Hunter's Gadson-case hands-on
window (907-1661s) and emitted 'not_observed' -- an accusation that the
examiner skipped a test -- for any recording whose clock differed. These
tests lock in the honest behavior.
"""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "backend" / "lambda_functions" / "cme_video_processor.py"


@pytest.fixture(scope="module")
def processor():
    """Import the Lambda module with boto3 clients stubbed out."""
    boto3_stub = types.ModuleType("boto3")

    class _Client:
        def __getattr__(self, _name):
            def _call(*_args, **_kwargs):
                raise RuntimeError("AWS not available in tests")

            return _call

    boto3_stub.client = lambda *a, **k: _Client()
    boto3_stub.resource = lambda *a, **k: _Client()
    saved = sys.modules.get("boto3")
    sys.modules["boto3"] = boto3_stub
    try:
        spec = importlib.util.spec_from_file_location(
            "cme_video_processor_undertest", MODULE_PATH
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is not None:
            sys.modules["boto3"] = saved
        else:
            del sys.modules["boto3"]
    return module


def test_bedrock_failure_returns_analysis_unavailable(processor):
    """Bedrock is unreachable in tests, so this exercises the failure path."""
    result = processor.analyze_with_bedrock(
        test_type="deep_tendon_reflexes",
        test_timestamp=42.0,
        transcript_excerpt="I will check your reflexes now",
        motion_labels=[],
        person_count=2,
    )
    assert result["motion_present"] == "analysis_unavailable"
    assert result["confidence"] == 0.0
    assert result["analysis_error"] == "vision_model_unavailable"


def test_failure_never_claims_test_was_skipped(processor):
    """The dangerous outputs are 'not_observed' and 'performed'."""
    for timestamp in (10.0, 950.0, 1700.0):  # inside and outside Gadson's window
        result = processor.analyze_with_bedrock(
            test_type="manual_muscle_testing",
            test_timestamp=timestamp,
            transcript_excerpt="squeeze my fingers",
            motion_labels=[],
            person_count=2,
        )
        assert result["motion_present"] not in ("not_observed", "performed", "brief")


def test_case_specific_heuristic_is_marked_deprecated(processor):
    doc = processor.use_fast_heuristic.__doc__ or ""
    assert "DEPRECATED" in doc
    assert "907-1661" in doc, "the doc must name the hardcoded window it assumed"
