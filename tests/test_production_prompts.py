from backend.lambda_functions.prompts import production as p


def test_prompt_versions_bumped():
    for v in (
        p.TECHNIQUE_FRAME_PROMPT_VERSION,
        p.BEHAVIOR_VISUAL_PROMPT_VERSION,
        p.AUDIO_ANALYSIS_PROMPT_VERSION,
        p.BEHAVIOR_VERBAL_PROMPT_VERSION,
    ):
        assert v and "." in v


def test_technique_prompt_has_visibility_and_confidence():
    assert "visibility" in p.FRAME_ANALYSIS_PROMPT
    assert "confidence" in p.FRAME_ANALYSIS_PROMPT


def test_bedrock_model_id_format():
    assert p.BEDROCK_CLAUDE_VISION_MODEL_ID.startswith("anthropic.claude-")
