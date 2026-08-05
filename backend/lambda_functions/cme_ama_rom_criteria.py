"""AMA Guides spine range-of-motion measurement criteria.

Distilled from Dr. Hunter's AMA Guides reference excerpts (Section 15.8-15.11,
"Principles of Inclinometry and Spine Motion Measurement" and the
two-inclinometer technique pages), recovered by OCR from:
  - "AMA inclinometry.pdf"
  - "AMA range of motion neck.pdf"
  - "AMA range of motion lumbar.pdf"
  - "AMA range of motion more.pdf"

These are the measurement-standard facts the claim verifier needs when a
report asserts spine ROM values or "normal" ROM: what instrument, what
landmarks, and what reproducibility protocol the AMA Guides require. A
visual estimate with no inclinometer/goniometer on video cannot satisfy
this standard.
"""
from typing import Dict, List

# Requirements common to every spine region (AMA Guides 15.8b).
GENERAL_REQUIREMENTS: List[str] = [
    "An inclinometer is the preferred device for spine ROM; spinal motion is "
    "compound, so BOTH ends of the spine region must be measured "
    "simultaneously (two-inclinometer technique).",
    "The device must read in 2-degree increments or less, be stabilized on "
    "palpated bony landmarks, with the body part stabilized and the patient "
    "instructed and allowed warm-up exercises first.",
    "Each motion must be repeated at least three times; measurements are "
    "valid only when three consecutive readings fall within 5 degrees or 10% "
    "of their mean (whichever is greater). The rating uses the greatest angle "
    "of a valid set.",
]

REGION_CRITERIA: Dict[str, Dict[str, object]] = {
    "cervical": {
        "landmarks": "First inclinometer over the calvarium (eye-ear line as "
        "0 reference), second over the T1 spinous process; patient seated, "
        "head neutral, inclinometers zeroed.",
        "technique": "For each plane, subtract the T1 angle from the "
        "calvarium angle to obtain true cervical motion; left and right "
        "sides are measured and rated separately.",
        "planes": 6,
    },
    "lumbar": {
        "landmarks": "First inclinometer over the T12 spinous process, second "
        "over the sacrum at the midpoint of the posterior superior iliac "
        "spines; patient standing, knees extended, weight balanced.",
        "technique": "Subtract the sacral (hip) angle from the T12 angle to "
        "obtain true lumbar motion; straight-leg-raise comparison is used to "
        "validate lumbar flexion measurements. Three of six consecutive "
        "measurements must lie within 5 degrees or 10% of the mean.",
        "planes": 6,
    },
    "thoracic": {
        "landmarks": "Inclinometers over the T1 and T12 spinous processes.",
        "technique": "Two-inclinometer subtraction technique, same "
        "reproducibility protocol as the other regions.",
        "planes": 6,
    },
}

_CLAIM_REGION = {
    "cervical_rom": "cervical",
    "lumbar_rom": "lumbar",
    "thoracic_rom": "thoracic",
}


def ama_rom_context_for_claim(claim_id: str, claim_text: str) -> List[str]:
    """AMA measurement-standard lines for a ROM claim, or [] otherwise."""
    cid = (claim_id or "").strip().lower()
    text = (claim_text or "").lower()

    region = _CLAIM_REGION.get(cid)
    if region is None:
        for key, value in _CLAIM_REGION.items():
            if key in cid:
                region = value
                break
    if region is None and ("range of motion" in text or " rom " in f" {text} "):
        if "cervical" in text or "neck" in text:
            region = "cervical"
        elif "lumbar" in text or "lumbosacral" in text or "low back" in text:
            region = "lumbar"
        elif "thoracic" in text:
            region = "thoracic"
    if region is None:
        return []

    crit = REGION_CRITERIA[region]
    return [
        f"AMA Guides ({region} ROM): {GENERAL_REQUIREMENTS[0]}",
        f"AMA Guides landmarks: {crit['landmarks']}",
        f"AMA Guides protocol: {GENERAL_REQUIREMENTS[2]}",
        f"AMA Guides technique: {crit['technique']}",
        "If the video shows no inclinometer/goniometer, no landmark marking, "
        "and no repeated measurements, reported degree values or 'normal ROM' "
        "cannot meet this measurement standard.",
    ]
