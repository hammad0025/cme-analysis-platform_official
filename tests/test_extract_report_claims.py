"""Tests for scripts/extract_report_claims.py (heuristic extraction, offline)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from extract_report_claims import extract_claims_heuristic, normalize_report_text  # noqa: E402

OSBORNE_SNIPPET = """
Physical examination:
General: Appearance: Appears stated age.
Spinal examination:
Cervical: Ranges of motion are normal aside from mild limitations in sidebending bilaterally.
There is a well healed surgical incision.
Lumbar: [Not examined given the nature of the presenting complaints.]
Neurologic examination:
Mental status: Awake, alert and oriented x 3. Follows complex commands briskly.
Cranial nerves: III-XII are grossly normal.
Motor: 5/5 strength throughout.
Sensory: Normal joint position and pinprick throughout the upper and lower extremities.
Rhomberg's testing is negative.
Deep tendon reflexes: 0/4 throughout.
No long tract signs.
Cerebellum: Normal.
Gait: Normal. Normal tandem gait.
Medical record review:
"""


def test_normalize_report_text_collapses_whitespace():
    assert normalize_report_text("Motor:\t5/5\tstrength") == "Motor: 5/5 strength"


def test_heuristic_extracts_exact_neurologic_quotes():
    claims = extract_claims_heuristic(normalize_report_text(OSBORNE_SNIPPET))
    assert "cranial_nerves" in claims
    assert "III-XII are grossly normal" in claims["cranial_nerves"]
    assert claims.get("strength", "").startswith("5/5 strength throughout")
    assert "0/4 throughout" in claims.get("reflexes", "")
    assert claims.get("romberg", "").lower().startswith("rhomberg")
    assert "negative" in claims.get("romberg", "").lower()
    assert "sidebending bilaterally" in claims.get("rom", "")


def test_heuristic_writes_expected_keys_for_fixture(tmp_path: Path):
    claims = extract_claims_heuristic(normalize_report_text(OSBORNE_SNIPPET))
    out = tmp_path / "claims.json"
    out.write_text(json.dumps(claims, indent=2), encoding="utf-8")
    loaded = json.loads(out.read_text())
    assert loaded["mental_status"].startswith("Awake, alert")
    assert "gait" in loaded
