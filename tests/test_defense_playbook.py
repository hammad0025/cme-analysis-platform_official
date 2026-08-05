from backend.lambda_functions.cme_ama_rom_criteria import ama_rom_context_for_claim
from backend.lambda_functions.cme_claim_verifier import (
    hunter_methodology_context_for_claim,
)
from backend.lambda_functions.cme_defense_playbook import (
    REBUTTAL_QUESTIONS,
    STANDARD_OF_CARE_GAPS,
    rebuttal_questions_for_topic,
    standard_of_care_context_for_claim,
)


def test_standard_of_care_matches_claim_id():
    lines = standard_of_care_context_for_claim("motor_strength", "Strength is 5/5")
    assert any("24 upper-extremity" in line for line in lines)
    assert any("Typical shortfall" in line for line in lines)


def test_standard_of_care_falls_back_to_claim_text():
    lines = standard_of_care_context_for_claim(
        "exam_finding_7", "Romberg test was negative"
    )
    assert any("full 1 minute" in line.lower() for line in lines)


def test_standard_of_care_no_match_returns_empty():
    assert standard_of_care_context_for_claim("gait", "Patient walked normally") == []


def test_all_gap_entries_are_complete():
    for key, gap in STANDARD_OF_CARE_GAPS.items():
        for field in ("typical_report_claim", "typical_shortfall", "standard_of_care"):
            assert gap[field].strip(), f"{key}.{field} empty"


def test_rebuttal_questions_carry_sources():
    for topic, questions in REBUTTAL_QUESTIONS.items():
        assert questions, f"{topic} empty"
        for q in questions:
            assert q["question"].strip() and q["source"].strip()
    assert rebuttal_questions_for_topic("causation")
    assert rebuttal_questions_for_topic("unknown-topic") == []


def test_ama_rom_context_for_rom_claims():
    lines = ama_rom_context_for_claim("cervical_rom", "Cervical ROM is normal")
    assert any("two-inclinometer" in line for line in lines)
    assert any("calvarium" in line for line in lines)
    assert ama_rom_context_for_claim("grip_strength", "Grip strength 5/5") == []


def test_ama_rom_context_from_claim_text():
    lines = ama_rom_context_for_claim(
        "exam_finding_3", "Lumbar spine range of motion within normal limits"
    )
    assert any("T12" in line for line in lines)


def test_verifier_context_includes_playbook_and_ama():
    ctx = hunter_methodology_context_for_claim(
        "cervical_rom", "Cervical range of motion is normal in all planes."
    )
    assert "HUNTER / EXAM STANDARDS" in ctx
    assert "6 planes of motion" in ctx
    assert "AMA Guides" in ctx


def test_verifier_context_playbook_only_domains():
    ctx = hunter_methodology_context_for_claim(
        "cranial_nerves", "Cranial nerves II-XII grossly intact."
    )
    assert "48 distinct tests" in ctx
