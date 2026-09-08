"""Vision-unavailable handling must never fabricate a verdict.

The old fallback scored tests against Dr. Hunter's Gadson-case hands-on
window (907-1661s) and emitted 'not_observed' -- an accusation that the
examiner skipped a test -- for any recording whose clock differed. These
tests lock in the honest behavior.
"""
import importlib.util
import logging
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


def test_nova_video_analysis_uses_s3_video_block(processor, monkeypatch):
    monkeypatch.setenv("CME_BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
    sent = {}

    class _Bedrock:
        def converse(self, **kwargs):
            sent.update(kwargs)
            return {
                "output": {
                    "message": {
                        "content": [{
                            "text": (
                                '{"motion_present":"performed",'
                                '"pose_match":"full_match",'
                                '"confidence":0.86,'
                                '"reasoning":"The patient visibly performs the requested movement.",'
                                '"observed_evidence":["patient moves through the exam action"],'
                                '"missing_evidence":[]}'
                            )
                        }]
                    }
                }
            }

    monkeypatch.setattr(processor, "bedrock_client", _Bedrock())

    result = processor.analyze_with_bedrock(
        test_type="manual_muscle_testing",
        test_timestamp=42.0,
        transcript_excerpt="squeeze my fingers",
        motion_labels=[],
        person_count=2,
        video_s3_key="cme-segments/case/clip.mp4",
        s3_bucket="bucket",
        video_is_segment=True,
    )

    assert result["motion_present"] == "performed"
    assert result["pose_match"] == "full_match"
    assert result["confidence"] == 0.86
    assert result["provider"] == "bedrock"
    assert result["model_id"] == "amazon.nova-lite-v1:0"
    assert sent["modelId"] == "amazon.nova-lite-v1:0"
    content = sent["messages"][0]["content"]
    assert content[1]["video"]["format"] == "mp4"
    assert (
        content[1]["video"]["source"]["s3Location"]["uri"]
        == "s3://bucket/cme-segments/case/clip.mp4"
    )


def test_nova_unsupported_video_format_is_unavailable(processor, monkeypatch):
    monkeypatch.setenv("CME_BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

    class _Bedrock:
        def converse(self, **_kwargs):
            raise AssertionError("unsupported formats should not call Bedrock")

    monkeypatch.setattr(processor, "bedrock_client", _Bedrock())

    result = processor.analyze_with_bedrock(
        test_type="manual_muscle_testing",
        test_timestamp=42.0,
        transcript_excerpt="squeeze my fingers",
        motion_labels=[],
        person_count=2,
        video_s3_key="uploads/input.avi",
        s3_bucket="bucket",
        video_is_segment=False,
    )

    assert result["motion_present"] == "analysis_unavailable"
    assert result["confidence"] == 0.0
    assert result["analysis_error"] == "unsupported_video_format_for_bedrock"


def test_case_specific_heuristic_is_marked_deprecated(processor):
    doc = processor.use_fast_heuristic.__doc__ or ""
    assert "DEPRECATED" in doc
    assert "907-1661" in doc, "the doc must name the hardcoded window it assumed"


def test_process_result_marks_unavailable_status(processor, monkeypatch):
    saved_boto3 = sys.modules.get("boto3")
    persisted = {}

    class _Table:
        def put_item(self, Item):
            persisted["item"] = Item

    class _Dynamo:
        def Table(self, _name):
            return _Table()

    boto3_stub = types.ModuleType("boto3")
    boto3_stub.resource = lambda *a, **k: _Dynamo()
    monkeypatch.setitem(sys.modules, "boto3", boto3_stub)

    class _Processor:
        def __init__(self, _bucket):
            pass

        def extract_video_segment(self, **_kwargs):
            return None

        def analyze_video_segment(self, *_args, **_kwargs):
            return {"motion_detected": {}, "poses_detected": {}}

    monkeypatch.setattr(processor, "CMEVideoProcessor", _Processor)
    monkeypatch.setattr(
        processor,
        "analyze_with_bedrock",
        lambda *_args, **_kwargs: {
            "motion_present": "analysis_unavailable",
            "pose_match": "unknown",
            "confidence": 0.0,
            "analysis_error": "vision_model_unavailable",
        },
    )

    try:
        result = processor.process_video_for_cme_test(
            session_id="cme_test",
            declared_test={
                "label": "manual_muscle_testing",
                "timestamp": 42.0,
                "declared_step_id": "step_1",
                "transcript_text": "squeeze my fingers",
            },
            video_s3_key="input.mp4",
            s3_bucket="bucket",
        )
    finally:
        if saved_boto3 is not None:
            monkeypatch.setitem(sys.modules, "boto3", saved_boto3)

    assert result["motion_present"] == "analysis_unavailable"
    assert result["status"] == "analysis_unavailable"
    assert persisted["item"]["analysis_details"]["analysis_error"] == "vision_model_unavailable"


def test_handler_logs_unavailable_without_discrepancy(processor, monkeypatch, caplog):
    monkeypatch.setattr(
        processor,
        "process_video_for_cme_test",
        lambda **_kwargs: {
            "session_id": "cme_test",
            "test_type": "manual_muscle_testing",
            "timestamp": 42.0,
            "segment_key": "input.mp4",
            "action_id": "action_1",
            "motion_present": "analysis_unavailable",
            "pose_match": "unknown",
            "confidence": 0.0,
            "status": "analysis_unavailable",
        },
    )

    caplog.set_level(logging.INFO)
    result = processor.handler(
        {
            "session_id": "cme_test",
            "declared_test": {"label": "manual_muscle_testing", "timestamp": 42.0},
            "video_s3_key": "input.mp4",
        },
        None,
    )

    assert result["statusCode"] == 200
    assert "Test NOT ANALYZED" in caplog.text
    assert "Test NOT OBSERVED" not in caplog.text
