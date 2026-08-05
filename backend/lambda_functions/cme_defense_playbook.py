"""Dr. Hunter's defense-doctor playbook, distilled from his supplemental docs.

Source documents (parsed by scripts/parse_hunter_supplemental_docs.py into
hunter_supplemental_knowledge_base.json):
  - "defense doctor testing.docx"  -> STANDARD_OF_CARE_GAPS
  - "common defense opinions (1).docx" -> COMMON_DEFENSE_OPINIONS
  - "questions and references for the defense arguments ..." -> REBUTTAL_QUESTIONS

STANDARD_OF_CARE_GAPS feeds the claim verifier: for each exam domain it
pairs the boilerplate wording defense doctors put in reports with the
shortfalls Hunter typically observes on video and the full standard-of-care
requirement, so the verifier knows what a complete exam looks like when
judging supported vs partially_supported.

REBUTTAL_QUESTIONS carries Hunter's literature-cited "Do you deny that ..."
cross-examination questions for use in report generation.
"""
from typing import Any, Dict, List

# Keyed by the claim-id vocabulary used in _CLAIM_HUNTER_KB_KEYS.
STANDARD_OF_CARE_GAPS: Dict[str, Dict[str, str]] = {
    "sensory": {
        "typical_report_claim": "Sensation is intact in all upper and lower extremity dermatomes bilaterally.",
        "typical_shortfall": (
            "Doctor tests only light touch with fingertips, often through clothing, "
            "and skips dermatomes (commonly C4-C5 and L1-L3)."
        ),
        "standard_of_care": (
            "Test ALL dermatomes in all extremities and ALL modalities: light touch, "
            "pain, hot, cold, vibration, and proprioception — not light touch alone, "
            "never through clothing."
        ),
    },
    "motor_strength": {
        "typical_report_claim": "Strength is 5/5 in upper and lower extremities.",
        "typical_shortfall": (
            "Doctor tests only ~5 muscle groups per region on video."
        ),
        "standard_of_care": (
            "There are 24 upper-extremity and 14 lower-extremity muscle groups; a "
            "complete strength exam tests each. A 5/5-throughout report based on a "
            "handful of groups is not supported by a complete exam."
        ),
    },
    "reflexes": {
        "typical_report_claim": "Reflexes are 2-3 in the upper and lower extremities.",
        "typical_shortfall": "Report cites '2-3' as if normal.",
        "standard_of_care": (
            "Deep tendon reflexes are graded 0-4; grade 3 is ABNORMAL and consistent "
            "with brain or spinal cord injury. A reported '2-3' range includes an "
            "abnormal finding the report treats as normal."
        ),
    },
    "cervical_rom": {
        "typical_report_claim": "Cervical spine range of motion is normal.",
        "typical_shortfall": (
            "Doctor tests only flexion and extension, does not measure with any "
            "instrument, and cites no normal values for comparison."
        ),
        "standard_of_care": (
            "The cervical spine has 6 planes of motion; each must be measured "
            "(goniometer/inclinometer), with values recorded against cited norms — "
            "not visually estimated as 'normal'."
        ),
    },
    "lumbar_rom": {
        "typical_report_claim": "Lumbar spine range of motion is normal.",
        "typical_shortfall": (
            "Doctor tests only flexion and extension, does not measure with any "
            "instrument, and cites no normal values for comparison."
        ),
        "standard_of_care": (
            "The lumbar spine has 6 planes of motion; each must be measured "
            "(goniometer/inclinometer), with values recorded against cited norms — "
            "not visually estimated as 'normal'."
        ),
    },
    "atrophy": {
        "typical_report_claim": "There was no muscle atrophy in the upper or lower extremities.",
        "typical_shortfall": (
            "Patient remains in long sleeves / long pants; the doctor never inspects "
            "or measures the limbs."
        ),
        "standard_of_care": (
            "Atrophy assessment requires visual inspection of exposed limbs and "
            "circumference measurement; it cannot be performed through clothing."
        ),
    },
    "romberg": {
        "typical_report_claim": "Romberg test was negative.",
        "typical_shortfall": (
            "Doctor tests with feet apart, arms out in front, for ~10 seconds."
        ),
        "standard_of_care": (
            "Standard Romberg: eyes closed, feet TOGETHER, arms at the sides, held "
            "for a FULL 1 minute."
        ),
    },
    "cranial_nerves": {
        "typical_report_claim": "Cranial nerves II-XII were grossly normal.",
        "typical_shortfall": (
            "Doctor tests eye movements and shoulder shrug (~4 tests) and omits CN I "
            "(olfactory) entirely."
        ),
        "standard_of_care": (
            "A standard-of-care cranial nerve evaluation comprises 48 distinct tests "
            "including CN I."
        ),
    },
}

# From "common defense opinions (1).docx" — boilerplate defense positions the
# report should recognize as opinions, not established facts.
COMMON_DEFENSE_OPINIONS: List[str] = [
    "The trauma was not significant enough to injure the spine.",
    "Symptoms were not reported immediately, so there was no injury.",
    "The injury was not diagnosed (or imaged) in the emergency room.",
    "The patient reports too much pain to be believed.",
    "The patient reports too little pain to be believed.",
    "The injury is limited to soft tissue (sprain/strain) only.",
    "Facet joints, discs, and ligaments cannot be injured without a fracture.",
    "A traumatic disc injury must show acute findings on MRI.",
    "Radiculopathy requires dermatomal sensory loss and visible nerve compression on MRI.",
    "Chemical radiculopathy has no support in the medical literature.",
    "Degenerative changes are always pre-existing and are always the cause of symptoms.",
    "Degenerative changes cannot be worsened or made symptomatic by trauma.",
    "Disc bulges/protrusions are always pre-existing and degenerative.",
    "Soft tissue injuries always resolve in 6-12 weeks; later symptoms mean malingering.",
    "Treatment or disability beyond 6-12 weeks is unrelated to the trauma.",
    "Post-traumatic surgery on disc protrusions is always unrelated to the trauma.",
    "Soft tissue spine injuries never cause permanent impairment.",
]

# From "questions and references ..." — Hunter's literature-cited leading
# questions, grouped by the defense argument they rebut. Sources are the
# author names Hunter cites in the document.
REBUTTAL_QUESTIONS: Dict[str, List[Dict[str, str]]] = {
    "tbi_diagnosis": [
        {
            "question": (
                "Do you deny that diagnosis of a mild TBI is based on a clinical "
                "interview, collateral interviews, and record review?"
            ),
            "source": "Ruff",
        },
        {
            "question": (
                "Do you deny that there was a 70% prevalence of mTBI in patients "
                "involved in motor vehicle collisions, but an acute-care diagnosis "
                "was made in only 39% of cases?"
            ),
            "source": "Peixoto",
        },
        {
            "question": (
                "Do you deny that DTI is a sensitive technique for imaging white "
                "matter damage in traumatic brain injury, and that these changes "
                "reflect axonal damage?"
            ),
            "source": "Kinnunen",
        },
        {
            "question": (
                "Do you deny that ANS abnormalities caused by TBI with a negative "
                "MRI scan can account for symptoms of concussion/mild TBI?"
            ),
            "source": "Pertab; Esterov",
        },
    ],
    "radiculopathy": [
        {
            "question": (
                "Do you deny that radiculopathy pain is mediated by inflammation "
                "more than by nerve root compression?"
            ),
            "source": "Hsu",
        },
        {
            "question": (
                "Do you deny that radiculopathy may arise in the absence of "
                "compression due to rupture of the annulus fibrosus with release of "
                "inflammatory mediators tracking along the nerve root sheath?"
            ),
            "source": "Hsu",
        },
        {
            "question": (
                "Do you deny that an EMG shows only damage to the motor nerve "
                "connection to muscle and cannot detect nerve root involvement that "
                "is only sensory?"
            ),
            "source": "Li",
        },
        {
            "question": (
                "Do you deny that patients with cervical radiculopathy may present "
                "with arm pain, sensory deficits, neck pain, paresthesia, reflex "
                "deficits, motor deficits, scapular pain, anterior chest pain, or "
                "any combination of these?"
            ),
            "source": "Kelly",
        },
    ],
    "prognosis": [
        {
            "question": (
                "Do you deny that one-half of patients with a single mild TBI have "
                "long-term cognitive impairment?"
            ),
            "source": "McInnes",
        },
        {
            "question": (
                "Do you deny that there is no human medical literature supporting "
                "the hypothesis that soft tissue injuries heal in 6 weeks, and that "
                "the six-week reference comes from a study of rabbits?"
            ),
            "source": "Hefti",
        },
        {
            "question": (
                "Do you deny that a literature review finds no epidemiologic or "
                "scientific basis for the claims that acute whiplash injuries do "
                "not lead to chronic pain, or that collisions without vehicle "
                "damage are unlikely to cause injury?"
            ),
            "source": "Freeman",
        },
    ],
    "causation": [
        {
            "question": (
                "Do you deny that 90% of whiplash injuries occur at speeds less "
                "than 14 mph, that significant vehicle damage requires 8.7 mph, and "
                "that crash tests as low as 2.5 mph are sufficient to cause "
                "symptoms?"
            ),
            "source": "Moheimani",
        },
        {
            "question": (
                "Do you deny that it is not possible to date the exact occurrence "
                "of a disc herniation unless a previous study is available for "
                "comparison?"
            ),
            "source": "Herzog",
        },
        {
            "question": (
                "Do you deny that when chronic degenerative changes are present, a "
                "disc herniation may represent an acute process superimposed on a "
                "chronic degenerative state?"
            ),
            "source": "Herzog",
        },
        {
            "question": (
                "Do you deny that in a patient with symptoms caused by trauma who "
                "lacks physical exam findings, 'lack of evidence' is not synonymous "
                "with 'evidence against'?"
            ),
            "source": "Walton",
        },
        {
            "question": (
                "Do you deny that whiplash symptom onset may be delayed up to "
                "several days after an injury?"
            ),
            "source": "Poorbaugh; Mayo Clinic",
        },
    ],
}


def standard_of_care_context_for_claim(claim_id: str, claim_text: str) -> List[str]:
    """Playbook lines for the claim verifier prompt, or [] if no domain matches."""
    cid = (claim_id or "").strip().lower()
    text = (claim_text or "").lower()

    gap = STANDARD_OF_CARE_GAPS.get(cid)
    if gap is None:
        for key, candidate in STANDARD_OF_CARE_GAPS.items():
            if key in cid:
                gap = candidate
                break
    if gap is None:
        if "sensation" in text or "dermatome" in text:
            gap = STANDARD_OF_CARE_GAPS["sensory"]
        elif "strength" in text and "grip" not in cid:
            gap = STANDARD_OF_CARE_GAPS["motor_strength"]
        elif "reflex" in text:
            gap = STANDARD_OF_CARE_GAPS["reflexes"]
        elif "atrophy" in text or "muscle bulk" in text:
            gap = STANDARD_OF_CARE_GAPS["atrophy"]
        elif "romberg" in text or "rhomberg" in text:
            gap = STANDARD_OF_CARE_GAPS["romberg"]
        elif "cranial nerve" in text:
            gap = STANDARD_OF_CARE_GAPS["cranial_nerves"]
    if gap is None:
        return []
    return [
        f"Standard of care: {gap['standard_of_care']}",
        f"Typical shortfall to check on video: {gap['typical_shortfall']}",
    ]


def rebuttal_questions_for_topic(topic: str) -> List[Dict[str, str]]:
    """Literature-cited cross-exam questions for a defense-argument topic."""
    return list(REBUTTAL_QUESTIONS.get((topic or "").strip().lower(), []))
