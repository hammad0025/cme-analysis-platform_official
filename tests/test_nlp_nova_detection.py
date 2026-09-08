"""NLP model selection should avoid the blocked Anthropic Bedrock path by default."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "backend" / "lambda_functions" / "cme_nlp_processor.py"


@pytest.fixture()
def nlp_processor():
    boto3_stub = types.ModuleType("boto3")

    class _Client:
        def __getattr__(self, _name):
            def _call(*_args, **_kwargs):
                raise RuntimeError("AWS not available in tests")

            return _call

    boto3_stub.client = lambda *a, **k: _Client()
    saved = sys.modules.get("boto3")
    sys.modules["boto3"] = boto3_stub
    try:
        spec = importlib.util.spec_from_file_location(
            "cme_nlp_processor_undertest", MODULE_PATH
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is not None:
            sys.modules["boto3"] = saved
        else:
            del sys.modules["boto3"]
    return module


def test_enhanced_test_detection_uses_nova_converse(nlp_processor, monkeypatch):
    monkeypatch.setenv("CME_NLP_MODEL_ID", "amazon.nova-lite-v1:0")
    sent = {}

    class _Bedrock:
        def converse(self, **kwargs):
            sent.update(kwargs)
            return {
                "output": {
                    "message": {
                        "content": [{
                            "text": (
                                '[{"test_type":"manual_muscle_testing",'
                                '"declaration":"squeeze my hand",'
                                '"approximate_time":"middle"}]'
                            )
                        }]
                    }
                }
            }

    monkeypatch.setattr(nlp_processor, "bedrock_client", _Bedrock())

    tests = nlp_processor.enhanced_test_detection_with_ai(
        "Please squeeze my hand and push against me."
    )

    assert tests == [{
        "test_type": "manual_muscle_testing",
        "declaration": "squeeze my hand",
        "approximate_time": "middle",
    }]
    assert sent["modelId"] == "amazon.nova-lite-v1:0"
    assert sent["messages"][0]["content"][0]["text"].startswith(
        "You are analyzing a transcript"
    )


def test_markdown_wrapped_ai_json_array_parses(nlp_processor):
    parsed = nlp_processor._extract_json_array_from_model_text(
        '```json\n[{"test_type":"gait_observation","declaration":"walk across the room"}]\n```'
    )

    assert parsed == [{
        "test_type": "gait_observation",
        "declaration": "walk across the room",
    }]
