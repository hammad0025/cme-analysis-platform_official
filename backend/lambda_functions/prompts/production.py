"""
Centralized, versioned prompts for local and Lambda analysis paths.

Bump *_PROMPT_VERSION when changing wording or JSON schema so outputs stay auditable.
"""

# Anthropic Bedrock model id (vision / messages API on Bedrock)
BEDROCK_CLAUDE_VISION_MODEL_ID = "anthropic.claude-sonnet-4-20250514-v1:0"

TECHNIQUE_FRAME_PROMPT_VERSION = "1.1.0"
BEHAVIOR_VISUAL_PROMPT_VERSION = "1.1.0"
AUDIO_ANALYSIS_PROMPT_VERSION = "1.1.0"
BEHAVIOR_VERBAL_PROMPT_VERSION = "1.1.0"

FRAME_ANALYSIS_PROMPT = """Analyze this frame from a Compulsory Medical Examination (CME) video for a legal case.

This is a DEFENSE medical examination where the doctor was hired by the defendant's insurance company. Look for issues that could help the plaintiff's case.

CRITICAL TAGGING RULES (legal evidence quality):
- If the frame shows ONLY a building exterior, parking lot, hallway with no active exam, waiting room, or establishing shot with NO patient visible: set test_type to "none", body_region to "none", and establishing_shot to true. Describe the scene in notes (e.g. "Exterior of medical building; no patient or examination visible").
- Do NOT tag test_type as rom, strength, sensory, reflex, gait, palpation, or cranial_nerve unless BOTH the patient AND examiner interaction for that test are clearly visible on camera.
- conversation is ONLY for doctor-patient dialogue with both parties visible; if only a waiting patient or empty room, use test_type "none".
- Never infer ROM/strength/sensory from street clothes, hallway transitions, or incidental movement.

Provide analysis in this EXACT JSON format:
{
    "patient_attire": "gown" or "regular_clothes" or "partial",
    "attire_details": "description of clothing",
    "patient_visible_distress": true/false,
    "patient_trying_to_speak": true/false,

    "visibility": "full" or "partial" or "obscured" or "unknown",
    "occlusion_notes": "what is hard to see (angle, blur, crop), or empty string if fully clear",
    "confidence": 0.0 to 1.0,

    "establishing_shot": true/false,
    "test_type": "strength/sensory/reflex/rom/gait/coordination/romberg/palpation/cranial_nerve/conversation/none",
    "test_details": "specific description",
    "body_region": "neck/shoulder/arm/hand/back/hip/leg/foot/face/full_body/none",

    "technique_issues": ["list of technique problems observed"],
    "equipment_visible": ["reflex_hammer", "goniometer", "sensory_pin", "tape_measure", etc.],

    "doctor_facing_patient": true/false,
    "doctor_making_eye_contact": true/false,
    "doctor_appears_rushed": true/false,
    "doctor_dismissive_gesture": true/false,
    "doctor_on_phone_or_distracted": true/false,

    "notes": "any other observations about professionalism, attention, or behavior"
}

TECHNIQUE ISSUES to look for:
- "testing_through_clothing" - sensory done over clothes
- "no_goniometer" - ROM without measurement device
- "improper_romberg" - wrong position or too brief
- "patient_not_in_gown" - wearing street clothes
- "rushed_examination" - moving too quickly
- "incomplete_test" - not finishing a test properly

BEHAVIOR to note:
- Is doctor paying attention to patient?
- Does doctor appear rushed or dismissive?
- Is doctor facing the patient during exam?
- Any signs of distraction (phone, looking away)?
- Patient appearing to want to say something but being cut off?

Use low confidence (below 0.5) when the frame is blurry, dark, or the relevant body region is off-camera.

Return ONLY the JSON object."""

AUDIO_ANALYSIS_PROMPT_TEMPLATE = """Analyze this transcript segment from a Compulsory Medical Examination (CME) between a defense medical examiner (hired by insurance company) and the plaintiff (patient).

TRANSCRIPT:
{transcript}

Analyze for professionalism and behavior issues. Return EXACT JSON:
{{
    "segments": [
        {{
            "speaker": "doctor" or "patient",
            "text": "what they said",
            "tone": "professional/condescending/dismissive/empathetic/rushed/rude/neutral",
            "sentiment_score": -1.0 to 1.0,
            "issues": {{
                "interrupting": true/false,
                "dismissing_concern": true/false,
                "rude_comment": true/false,
                "showing_empathy": true/false,
                "rushing_patient": true/false,
                "ignoring_question": true/false,
                "inappropriate_comment": true/false
            }},
            "problematic_quote": "exact quote if problematic, else empty string",
            "notes": "explanation of any issues"
        }}
    ],
    "overall_tone": "professional/mixed/unprofessional",
    "empathy_score": 0-10,
    "professionalism_score": 0-10,
    "key_issues": ["list of main problems found"],
    "helpful_for_plaintiff": ["list of quotes/behaviors that help plaintiff's case"]
}}

LOOK FOR:
1. RUDENESS: Condescending remarks, dismissive language, inappropriate comments
2. RUSHING: "Let's move on", cutting patient off, not letting them finish
3. DISMISSIVENESS: Minimizing symptoms, "it's not that bad", ignoring concerns
4. LACK OF EMPATHY: No acknowledgment of pain, cold/clinical demeanor
5. INTERRUPTING: Talking over patient, not letting them explain
6. INAPPROPRIATE: Personal comments, jokes at patient's expense, unprofessional remarks

DO NOT FLAG (never report these as issues):
- Transcription artifacts, mis-transcribed words, or name spellings/pronunciations
- Administrative chatter: greetings, introductions, scheduling, paperwork, consent forms
- Ordinary clinical questions or neutral small talk

Be thorough - this analysis will be used in legal proceedings."""

VISUAL_BEHAVIOR_PROMPT = """Analyze this frame from a Compulsory Medical Examination (CME) video. Focus on the DOCTOR'S BEHAVIOR and PROFESSIONALISM.

This is a defense medical examination where the doctor was hired by the defendant's insurance company. Identify any behavior issues that could help the plaintiff's case.

Analyze and return EXACT JSON:
{
    "doctor_visible": true/false,
    "patient_visible": true/false,

    "visibility": "full" or "partial" or "obscured" or "unknown",
    "occlusion_notes": "what is hard to see, or empty string",
    "confidence": 0.0 to 1.0,

    "eye_contact": {
        "looking_at_patient": true/false,
        "looking_at_notes": true/false,
        "looking_at_phone": true/false,
        "looking_elsewhere": true/false,
        "distracted": true/false
    },

    "body_language": {
        "facing_patient": true/false,
        "turned_away": true/false,
        "leaning_in_engaged": true/false,
        "leaning_back_disengaged": true/false,
        "arms_crossed_defensive": true/false,
        "open_welcoming_posture": true/false
    },

    "pace_and_movement": {
        "appears_rushed": true/false,
        "hasty_movements": true/false,
        "thorough_careful": true/false,
        "impatient": true/false
    },

    "gestures": {
        "dismissive_gesture": true/false,
        "impatient_gesture": true/false,
        "reassuring_gesture": true/false,
        "waving_off": true/false
    },

    "patient_state": {
        "appears_distressed": true/false,
        "trying_to_speak": true/false,
        "in_visible_pain": true/false,
        "being_ignored": true/false
    },

    "doctor_response": {
        "acknowledging_patient": true/false,
        "ignoring_patient_cue": true/false,
        "responding_to_distress": true/false,
        "pushing_through_pain": true/false
    },

    "overall_impression": "engaged/distracted/rushed/dismissive/cold/professional/empathetic",
    "issues_observed": ["list of behavior issues"],
    "detailed_notes": "Detailed description of doctor's behavior in this frame"
}

BEHAVIOR RED FLAGS to watch for:
- Not looking at patient when they're speaking
- Looking at phone or distracted
- Turned away from patient
- Rushed, hasty movements
- Dismissive hand gestures (waving off)
- Patient showing pain but doctor continuing
- Patient trying to speak but not being acknowledged
- Arms crossed, closed body language
- Impatient body language

Use low confidence when faces or key body language is not visible.

Return ONLY the JSON object."""

VERBAL_BEHAVIOR_PROMPT = """Analyze this transcript segment from a Compulsory Medical Examination (CME) between a defense medical examiner (hired by insurance company) and the plaintiff (patient).

TRANSCRIPT SEGMENT:
{transcript}

Analyze EVERY exchange for behavior and sentiment issues. Return EXACT JSON:
{{
    "exchanges": [
        {{
            "speaker": "doctor" or "patient",
            "text": "exact quote",
            "tone": "professional/empathetic/cold/dismissive/condescending/rude/sarcastic/rushed/impatient/neutral",

            "negative_behaviors": {{
                "interrupting": true/false,
                "cutting_off_patient": true/false,
                "ignoring_question": true/false,
                "dismissing_symptom": true/false,
                "minimizing_complaint": true/false,
                "rude_comment": true/false,
                "sarcastic": true/false,
                "condescending": true/false,
                "inappropriate_comment": true/false,
                "rushing_patient": true/false,
                "defensive": true/false,
                "impatient": true/false,
                "cold_clinical": true/false
            }},

            "positive_behaviors": {{
                "empathetic": true/false,
                "validating": true/false,
                "explaining": true/false,
                "asking_followup": true/false,
                "acknowledging_pain": true/false,
                "offering_comfort": true/false,
                "patient_focused": true/false,
                "thorough": true/false
            }},

            "is_problematic": true/false,
            "problem_explanation": "why this is problematic if applicable"
        }}
    ],

    "segment_summary": {{
        "overall_tone": "professional/mixed/unprofessional/hostile",
        "empathy_level": "high/medium/low/none",
        "professionalism_level": "high/medium/low/poor",
        "doctor_attitude": "caring/neutral/cold/dismissive/hostile"
    }},

    "problematic_quotes": [
        {{
            "quote": "exact quote",
            "speaker": "doctor",
            "problem": "what makes it problematic",
            "severity": "critical/high/medium/low"
        }}
    ],

    "key_issues": ["list of main behavior issues found"]
}}

WHAT TO FLAG:

CRITICAL ISSUES (clear rudeness/inappropriateness):
- Mocking the patient
- Personal attacks or insults
- Inappropriate jokes at patient's expense
- Yelling or raised voice
- Clearly hostile behavior
- Sexually inappropriate comments
- Racial/discriminatory remarks

HIGH SEVERITY (dismissiveness, not caring):
- "It's not that bad"
- "You should be over this by now"
- "I don't see why you're still complaining"
- Dismissing documented injuries
- Refusing to listen to symptoms
- "That shouldn't hurt"
- Cutting patient off repeatedly

MEDIUM SEVERITY (rushing, cold):
- "Let's move on"
- Not letting patient finish explaining
- Rushing through questions
- Cold/clinical tone with no warmth
- Not acknowledging pain when patient expresses it
- Being impatient with patient
- "We don't have time for that"

LOW SEVERITY (minor lapses):
- Not making small talk
- Formal but not rude
- Slightly impatient but not dismissive

NEVER FLAG (these are noise, not findings — do not mark them problematic):
- Transcription artifacts, garbled words, or how a name was spelled, recorded, or pronounced
- Administrative exchanges: greetings, introductions, scheduling, paperwork, consent forms
- Neutral clinical questions asked in an ordinary tone

ALSO NOTE POSITIVE BEHAVIORS:
- Taking time to explain
- Asking follow-up questions about symptoms
- Acknowledging the patient's pain
- Expressing concern
- Being thorough and patient
- Validating the patient's experience

Return ONLY the JSON object."""
