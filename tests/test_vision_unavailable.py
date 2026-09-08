"""Vision-unavailable handling must never fabricate a verdict.

The old fallback scored tests against Dr. Hunter's Gadson-case hands-on
window (907-1661s) and emitted 'not_observed' -- an accusation that the
examiner skipped a test -- for any recording whose clock differed. These
tests lock in the honest behavior.
"""
import importlib.util
import json
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


def test_nova_video_analysis_attaches_review_frames_and_filters_unknown_ids(processor, monkeypatch):
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
                                '"reasoning":"Visible arm movement is shown.",'
                                '"observed_evidence":["arm movement"],'
                                '"missing_evidence":[],'
                                '"observed_frame_ids":["frame_0001","invented_frame"]}'
                            )
                        }]
                    }
                }
            }

    monkeypatch.setattr(processor, "bedrock_client", _Bedrock())
    evidence_frames = [
        {
            "frame_id": f"frame_{index:04d}",
            "timestamp_seconds": index / 2,
            "s3_uri": f"s3://bucket/cme-evidence/case/step/frames/frame_{index:04d}.jpg",
        }
        for index in range(1, 23)
    ]

    result = processor.analyze_with_bedrock(
        test_type="manual_muscle_testing",
        test_timestamp=42.0,
        transcript_excerpt="squeeze my fingers",
        motion_labels=[],
        person_count=2,
        video_s3_key="cme-segments/case/clip.mp4",
        s3_bucket="bucket",
        video_is_segment=True,
        evidence_frames=evidence_frames,
    )

    content = sent["messages"][0]["content"]
    image_blocks = [block["image"] for block in content if "image" in block]
    assert len(image_blocks) == 20
    assert image_blocks[0]["source"]["s3Location"]["uri"].endswith("frame_0001.jpg")
    assert "frame_0001: 0.500s" in content[0]["text"]
    assert result["reviewed_frame_ids"] == ["frame_0001"]


def test_deterministic_evidence_requires_a_valid_frame_citation(processor):
    result = processor._normalize_video_verdict(
        {
            "motion_present": "performed",
            "pose_match": "full_match",
            "confidence": 0.9,
            "observed_evidence": ["movement"],
            "observed_frame_ids": ["invented_frame"],
        },
        "amazon.nova-lite-v1:0",
        allowed_frame_ids={"frame_0001"},
    )

    assert result["motion_present"] == "analysis_unavailable"
    assert result["pose_match"] == "unknown"
    assert result["confidence"] == 0.0
    assert result["reviewed_frame_ids"] == []
    assert "No valid deterministic evidence frame was cited." in result["missing_evidence"]


def test_segment_extraction_skips_s3_download_without_ffmpeg(processor, monkeypatch):
    class _S3:
        def download_file(self, *_args, **_kwargs):
            raise AssertionError("should not download the full video when ffmpeg is unavailable")

    monkeypatch.setattr(processor, "s3_client", _S3())
    monkeypatch.setattr(processor.os.path, "exists", lambda _path: False)

    segment = processor.CMEVideoProcessor("bucket").extract_video_segment(
        video_s3_key="cme-recordings/case/hour-long.mp4",
        start_time=1800,
    )

    assert segment is None


def test_evidence_frame_extraction_creates_timestamped_manifest(processor, monkeypatch):
    uploads = []
    manifests = []

    class _S3:
        def download_file(self, _bucket, _key, target):
            Path(target).write_bytes(b"segment")

        def upload_file(self, source, bucket, key, ExtraArgs=None):
            uploads.append({
                "source": Path(source).name,
                "bucket": bucket,
                "key": key,
                "extra_args": ExtraArgs,
            })

        def put_object(self, **kwargs):
            manifests.append(kwargs)

    def _run(command, **_kwargs):
        if '-f' in command and command[command.index('-f') + 1] == 'null':
            class _Result:
                returncode = 0

            return _Result()

        pattern = Path(command[-1])
        pattern.parent.mkdir(parents=True, exist_ok=True)
        for index in range(25):
            (pattern.parent / f"frame_{index + 1:04d}.jpg").write_bytes(b"jpeg")

        class _Result:
            returncode = 0

        return _Result()

    monkeypatch.setattr(processor, "s3_client", _S3())
    monkeypatch.setattr(processor.CMEVideoProcessor, "_ffmpeg_path", lambda _self: "/opt/bin/ffmpeg")
    monkeypatch.setattr(processor.subprocess, "run", _run)

    evidence = processor.CMEVideoProcessor("bucket").extract_evidence_frames(
        segment_s3_key="cme-segments/case/segment.mp4",
        session_id="case/with unsafe chars",
        declared_step_id="step 1",
        window_start_seconds=12.0,
    )

    assert {
        key: evidence["sampling"][key]
        for key in ("frames_per_second", "frame_interval_seconds", "frame_count")
    } == {
        "frames_per_second": 2.0,
        "frame_interval_seconds": 0.5,
        "frame_count": 25,
    }
    assert evidence["sampling"]["motion_bursts"]["burst_count"] == 0
    assert len(uploads) == 25
    assert all(upload["extra_args"] == {"ContentType": "image/jpeg"} for upload in uploads)
    assert uploads[0]["key"] == "cme-evidence/case_with_unsafe_chars/step_1/frames/frame_0001.jpg"
    assert len(evidence["review_frames"]) == 20
    assert evidence["review_frames"][0]["timestamp_seconds"] == 12.0
    assert evidence["review_frames"][-1]["timestamp_seconds"] == 24.0
    assert len(manifests) == 1
    manifest = json.loads(manifests[0]["Body"])
    assert manifest["sampling"]["frame_count"] == 25
    assert manifest["frames"][1]["timestamp_seconds"] == 12.5
    assert manifest["model_review"]["selection"] == "uniformly_spaced"


def test_evidence_frame_extraction_adds_motion_burst_focus_crops(processor, monkeypatch):
    uploads = []
    manifests = []

    class _S3:
        def download_file(self, _bucket, _key, target):
            Path(target).write_bytes(b"segment")

        def upload_file(self, source, bucket, key, ExtraArgs=None):
            uploads.append({
                "source": Path(source).name,
                "bucket": bucket,
                "key": key,
                "extra_args": ExtraArgs,
            })

        def put_object(self, **kwargs):
            manifests.append(kwargs)

    def _result():
        class _Result:
            returncode = 0

        return _Result()

    def _write_frames(pattern, count):
        pattern.parent.mkdir(parents=True, exist_ok=True)
        for index in range(count):
            (pattern.parent / f"frame_{index + 1:04d}.jpg").write_bytes(b"jpeg")

    def _run(command, **_kwargs):
        if '-filter_complex' in command:
            for output in (value for value in command if str(value).endswith('.jpg')):
                _write_frames(Path(output), 24)
            return _result()

        if '-f' in command and command[command.index('-f') + 1] == 'null':
            filter_value = command[command.index('-vf') + 1]
            metadata_path = Path(filter_value.rsplit('file=', 1)[1])
            metadata_path.write_text(
                'frame:0 pts:0 pts_time:0\n'
                'lavfi.signalstats.YDIF=0\n'
                'frame:20 pts:20 pts_time:10\n'
                'lavfi.signalstats.YDIF=4.2\n'
                'frame:40 pts:40 pts_time:20\n'
                'lavfi.signalstats.YDIF=0.1\n',
                encoding='utf-8',
            )
            return _result()

        _write_frames(Path(command[-1]), 25)
        return _result()

    monkeypatch.setattr(processor, "s3_client", _S3())
    monkeypatch.setattr(processor.CMEVideoProcessor, "_ffmpeg_path", lambda _self: "/opt/bin/ffmpeg")
    monkeypatch.setattr(processor.subprocess, "run", _run)

    evidence = processor.CMEVideoProcessor("bucket").extract_evidence_frames(
        segment_s3_key="cme-segments/case/segment.mp4",
        session_id="case",
        declared_step_id="step_1",
        window_start_seconds=12.0,
    )

    assert len(uploads) == 25 + (24 * 4)
    assert all(upload["extra_args"] == {"ContentType": "image/jpeg"} for upload in uploads)
    assert len(evidence["review_frames"]) == 20
    review_frame_ids = {frame["frame_id"] for frame in evidence["review_frames"]}
    assert "burst_01_frame_0013" in review_frame_ids
    assert "burst_01_frame_0013_left_interaction_zone" in review_frame_ids
    assert "burst_01_frame_0013_center_exam_zone" in review_frame_ids
    assert "burst_01_frame_0013_right_interaction_zone" in review_frame_ids

    manifest = json.loads(manifests[0]["Body"])
    assert manifest["schema_version"] == "1.1"
    assert manifest["sampling"]["motion_bursts"]["burst_count"] == 1
    assert manifest["model_review"]["selection"] == "baseline_uniform_and_motion_focused"
    assert manifest["model_review"]["motion_focus_frame_count"] == 4
    burst = manifest["motion_bursts"][0]
    assert burst["trigger_timestamp_seconds"] == 22.0
    assert burst["start_timestamp_seconds"] == 20.5
    assert burst["frames_per_second"] == 8.0
    assert len(burst["frames"]) == 24
    assert len(burst["focus_crops"]) == 72
    assert all(
        crop["crop_note"].startswith("Coordinate-based interaction crop")
        for crop in burst["focus_crops"]
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

        def extract_evidence_frames(self, **_kwargs):
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


def test_handler_missing_fields_does_not_echo_event(processor):
    result = processor.handler(
        {
            "session_id": "cme_test",
            "authorization": "Bearer secret-token",
        },
        None,
    )

    assert result["statusCode"] == 400
    assert "event" not in result
    assert "traceback" not in result
    assert "secret-token" not in str(result)


def test_handler_exception_does_not_return_traceback(processor, monkeypatch):
    def _raise(**_kwargs):
        raise RuntimeError("vision service unavailable")

    monkeypatch.setattr(processor, "process_video_for_cme_test", _raise)

    result = processor.handler(
        {
            "session_id": "cme_test",
            "declared_test": {"label": "manual_muscle_testing", "timestamp": 42.0},
            "video_s3_key": "input.mp4",
        },
        None,
    )

    assert result["statusCode"] == 500
    assert result["error"] == "vision service unavailable"
    assert "traceback" not in result
