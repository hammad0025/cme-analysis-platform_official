import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "lambda_functions"))

from cme_handler import _safe_storage_filename


def test_safe_storage_filename_preserves_mp4_extension():
    long_name = "CME - Defendant BI - Dr. Osborne  3.9.21 (video).mp4"
    result = _safe_storage_filename(long_name, max_len=80)
    assert result.endswith(".mp4"), result
    assert len(result) <= 80


def test_safe_storage_filename_no_extension():
    assert _safe_storage_filename("a" * 100, max_len=20) == "a" * 20


def test_safe_storage_filename_short_unchanged():
    assert _safe_storage_filename("short.pdf") == "short.pdf"
