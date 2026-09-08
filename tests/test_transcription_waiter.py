"""Transcription waiter orchestration payload safety tests."""

import importlib.util
import sys
import types
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "backend" / "lambda_functions" / "transcription_waiter.py"


def import_waiter_with_boto3(state):
    boto3_stub = types.ModuleType("boto3")

    class _Transcribe:
        def get_medical_transcription_job(self, MedicalTranscriptionJobName):
            state["medical_job_name"] = MedicalTranscriptionJobName
            return {
                "MedicalTranscriptionJob": {
                    "TranscriptionJobStatus": "COMPLETED",
                    "Transcript": {
                        "TranscriptFileUri": (
                            "https://cme-analysis-recordings-388846700527"
                            ".s3.us-east-1.amazonaws.com/transcripts/job.json"
                        )
                    },
                }
            }

    class _S3:
        pass

    class _Table:
        def update_item(self, **kwargs):
            state["update_item"] = kwargs

    class _Dynamo:
        def Table(self, name):
            state["table_name"] = name
            return _Table()

    def client(service_name, *_args, **_kwargs):
        if service_name == "transcribe":
            return _Transcribe()
        if service_name == "s3":
            return _S3()
        raise AssertionError(f"Unexpected boto3 client: {service_name}")

    boto3_stub.client = client
    boto3_stub.resource = lambda *_args, **_kwargs: _Dynamo()

    saved = sys.modules.get("boto3")
    sys.modules["boto3"] = boto3_stub
    try:
        spec = importlib.util.spec_from_file_location(
            "transcription_waiter_undertest", MODULE_PATH
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is not None:
            sys.modules["boto3"] = saved
        else:
            del sys.modules["boto3"]
    return module


def test_completed_transcription_returns_uri_only(monkeypatch):
    state = {}
    waiter = import_waiter_with_boto3(state)
    monkeypatch.setattr(
        waiter,
        "download_transcript",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("waiter must not return transcript data")
        ),
    )

    result = waiter.handler(
        {
            "session_id": "cme_test",
            "transcription_job_name": "job-name",
        },
        None,
    )

    assert result == {
        "statusCode": 200,
        "session_id": "cme_test",
        "status": "COMPLETED",
        "transcript_uri": "s3://cme-analysis-recordings-388846700527/transcripts/job.json",
    }
    assert "transcript_data" not in result
    assert state["medical_job_name"] == "job-name"
    assert (
        state["update_item"]["ExpressionAttributeValues"][":uri"]
        == "s3://cme-analysis-recordings-388846700527/transcripts/job.json"
    )
