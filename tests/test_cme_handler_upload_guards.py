import json
import logging
import os
import sys

from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "lambda_functions"))

import cme_handler  # noqa: E402


class _FakeTable:
    def __init__(self, item):
        self.item = item
        self.updates = []

    def get_item(self, **_kwargs):
        return {"Item": self.item}

    def update_item(self, **kwargs):
        self.updates.append(kwargs)
        return {}


class _FakeDynamo:
    def __init__(self, table):
        self.table = table

    def Table(self, _name):
        return self.table


class _FakeS3:
    def __init__(self, missing=False):
        self.missing = missing

    def generate_presigned_url(self, *_args, **_kwargs):
        return "https://example.invalid/presigned"

    def head_object(self, **_kwargs):
        if self.missing:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
        return {"ContentLength": 123}


def _body(response):
    return json.loads(response["body"])


def test_request_summary_does_not_log_auth_or_body(caplog):
    caplog.set_level(logging.INFO)
    event = {
        "httpMethod": "POST",
        "path": "/cme/sessions",
        "headers": {
            "Authorization": "Bearer secret-token",
            "Origin": "https://cme-analysis-platform-official.vercel.app",
        },
        "body": '{"patient_name":"Private Plaintiff"}',
        "requestContext": {"requestId": "req-1"},
    }

    cme_handler._log_request_summary(event)

    assert "secret-token" not in caplog.text
    assert "Private Plaintiff" not in caplog.text
    assert "/cme/sessions" in caplog.text


def test_upload_rejects_mpg_container(monkeypatch):
    table = _FakeTable({
        "session_id": "cme_test",
        "recording_allowed": {"video": True, "audio": True},
        "state": "FL",
    })
    monkeypatch.setattr(cme_handler, "dynamodb", _FakeDynamo(table))
    monkeypatch.setattr(cme_handler, "s3_client", _FakeS3())

    response = cme_handler.handle_upload_cme_recording({
        "session_id": "cme_test",
        "filename": "exam.mpg",
        "content_type": "video/mpeg",
        "file_size": 123,
    })

    assert response["statusCode"] == 415
    assert "convert the recording" in _body(response)["error"].lower()
    assert table.updates == []


def test_processing_refuses_to_start_when_presigned_upload_missing(monkeypatch):
    table = _FakeTable({
        "session_id": "cme_test",
        "recordings": [{
            "uri": "s3://cme-analysis-recordings-388846700527/cme-recordings/cme_test/missing.mp4",
            "s3_key": "cme-recordings/cme_test/missing.mp4",
            "filename": "missing.mp4",
            "recording_slot": 1,
        }],
    })
    monkeypatch.setattr(cme_handler, "dynamodb", _FakeDynamo(table))
    monkeypatch.setattr(cme_handler, "s3_client", _FakeS3(missing=True))

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("transcription should not start for a missing upload")

    monkeypatch.setattr(cme_handler, "start_transcription_job", fail_if_called)

    response = cme_handler.handle_start_cme_processing({"session_id": "cme_test"})

    assert response["statusCode"] == 409
    body = _body(response)
    assert body["missing_recordings"][0]["reason"] == "upload_not_found"


def test_processing_refuses_multi_recording_sessions(monkeypatch):
    table = _FakeTable({
        "session_id": "cme_test",
        "recordings": [
            {
                "uri": "s3://cme-analysis-recordings-388846700527/cme-recordings/cme_test/one.mp4",
                "s3_key": "cme-recordings/cme_test/one.mp4",
                "filename": "one.mp4",
                "recording_slot": 1,
            },
            {
                "uri": "s3://cme-analysis-recordings-388846700527/cme-recordings/cme_test/two.mp4",
                "s3_key": "cme-recordings/cme_test/two.mp4",
                "filename": "two.mp4",
                "recording_slot": 2,
            },
        ],
    })
    monkeypatch.setattr(cme_handler, "dynamodb", _FakeDynamo(table))
    monkeypatch.setattr(cme_handler, "s3_client", _FakeS3())

    response = cme_handler.handle_start_cme_processing({"session_id": "cme_test"})

    assert response["statusCode"] == 409
    assert "only one recording" in _body(response)["error"].lower()
