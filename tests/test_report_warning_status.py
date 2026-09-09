import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "backend" / "lambda_functions" / "cme_report_generator.py"


@pytest.fixture()
def report_generator(monkeypatch):
    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = lambda *a, **k: object()
    boto3_stub.resource = lambda *a, **k: object()
    monkeypatch.setitem(sys.modules, "boto3", boto3_stub)

    spec = importlib.util.spec_from_file_location(
        "cme_report_generator_undertest", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_analysis_completion_summary_counts_missing_video_verdicts(report_generator):
    summary = report_generator._analysis_completion_summary(
        {
            "declared_steps": [
                {"declared_step_id": "step_1"},
                {"declared_step_id": "step_2"},
                {"declared_step_id": "step_3"},
            ],
            "step_actions": {
                "step_1": {"motion_present": "performed"},
                "step_2": {"motion_present": "analysis_unavailable"},
            },
        }
    )

    assert summary == {
        "analysis_status": "incomplete",
        "tests_unanalyzed": 2,
        "total_declared_tests": 3,
    }


def test_report_update_uses_warning_status_for_incomplete_analysis(
    report_generator, monkeypatch
):
    update = {}

    class _Table:
        def update_item(self, **kwargs):
            update.update(kwargs)

    class _Dynamo:
        def Table(self, _name):
            return _Table()

    monkeypatch.setattr(report_generator, "dynamodb", _Dynamo())

    report_generator._update_session_after_report(
        "cme_test",
        success=True,
        report_key="cme-reports/cme_test/report.html",
        analysis_status="incomplete",
        tests_unanalyzed=2,
        total_declared_tests=3,
    )

    values = update["ExpressionAttributeValues"]
    assert values[":status"] == "completed_with_warnings"
    assert values[":stage"] == "analysis_incomplete"
    assert values[":analysis_status"] == "incomplete"
    assert values[":tests_unanalyzed"] == 2
    assert values[":total_declared_tests"] == 3
    assert "2 of 3" in values[":analysis_warning"]


def test_session_data_only_uses_actions_owned_by_the_session(
    report_generator, monkeypatch
):
    action_queries = []

    class _Table:
        def __init__(self, name):
            self.name = name

        def get_item(self, **_kwargs):
            return {"Item": {"session_id": "case_one"}}

        def scan(self, **kwargs):
            if self.name == "cme-declared-steps":
                return {"Items": [{"declared_step_id": "step_one", "timestamp": 1}]}
            if self.name == "cme-observed-actions":
                action_queries.append(kwargs)
                return {
                    "Items": [
                        {
                            "session_id": "case_one",
                            "declared_step_id": "step_one",
                            "motion_present": "performed",
                        }
                    ]
                }
            return {"Items": []}

    class _Dynamo:
        def Table(self, name):
            return _Table(name)

    monkeypatch.setattr(report_generator, "dynamodb", _Dynamo())

    data = report_generator.CMEReportGenerator("bucket")._gather_session_data("case_one")

    assert data["step_actions"] == {
        "step_one": {
            "session_id": "case_one",
            "declared_step_id": "step_one",
            "motion_present": "performed",
        }
    }
    assert action_queries == [
        {
            "FilterExpression": "session_id = :sid",
            "ExpressionAttributeValues": {":sid": "case_one"},
        }
    ]
