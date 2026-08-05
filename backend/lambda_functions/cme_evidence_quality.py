"""
Single source of truth for video frame evidence quality gates.

Prevents B-roll, establishing shots, and loosely-tagged ambient frames from
being cited as deposition evidence for physical-exam claims.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional

# --- Exported constants (regression tests may import these) ---

BROLL_NOTE_PHRASES = (
    "exterior",
    "building",
    "establishing shot",
    "no medical examination",
    "no examination activity",
    "no patient",
    "waiting area",
    "waiting room",
    "transitional footage",
    "empty hallway",
    "empty medical facility",
    "hallway rather than",
    "conducted in hallway",
)

NON_EXAM_NOTE_PHRASES = (
    "no examination",
    "no medical examination",
    "no patient",
    "not visible",
    "cannot assess",
    "cannot analyze",
    "no examination activity",
)

NON_EXAM_TEST_TYPES = frozenset({"none", "conversation", ""})
NON_EXAM_BODY_REGIONS = frozenset({"none", "unknown", ""})

WORD_BOUNDARY_KEYWORDS = frozenset({"rom", "motion", "arm", "leg", "toe", "heel", "add", "long", "sign"})

REFLEX_KEYS = ("reflex", "dtrs", "deep tendon", "hammer")
GAIT_KEYS = ("gait", "walk", "tandem", "romberg", "heel", "toe")
CRANIAL_KEYS = ("cranial", "eye movement", "tongue", "smile", "symmetry", "pupil", "facial")
CRANIAL_EXAM_MARKERS = (
    "cranial nerve",
    "cranial examination",
    "head/cranial",
    "eye movement",
    "extraocular",
    "pupil",
    "pupillary",
    "facial nerve",
    "smile test",
)
GAIT_ONLY_MARKERS = (
    "gait assessment",
    "during gait",
    "observing walking",
    "walking in hallway",
    "walking alongside",
    "walking behind",
    "walking ahead",
    "heel walk",
    "toe walk",
    "tandem gait",
    "gait pattern",
)
PATHOLOGICAL_KEYS = (
    "hoffmann",
    "babinski",
    "plantar response",
    "plantar reflex",
    "pathological reflex",
    "long tract",
    "clonus",
    "pathologic",
)
STRENGTH_POSITIVE_MARKERS = (
    "performing",
    "resistance",
    "push against",
    "manual muscle",
    "mmt",
    "5/5",
    "breakaway",
    "isometric",
    "muscle testing",
    "strength testing",
    "resistance testing",
)
# Administrative / transcription noise: never usable as evidence text.
ADMIN_NOISE_RE = re.compile(
    r"\b(?:"
    r"name\s+(?:was\s+)?(?:recorded|spelled|misspelled|mispronounced|stated)"
    r"|misspell\w*|spelling|mispronunc\w*|pronunciation"
    r"|transcription\s+(?:error|artifact|issue|quality)"
    r"|transcript\s+(?:error|artifact)"
    r"|audio\s+quality|recording\s+quality"
    r"|recorded\s+improperly"
    r"|paperwork|scheduling|check[- ]?in|consent\s+form"
    r"|small\s+talk|greeting"
    r")\b",
    re.I,
)

ATTIRE_COMPLAINT_RE = re.compile(
    r"\b(street\s*clothes?|scrubs|gown|clothed|clothing|attire|thoroughness|"
    r"fully clothed|regular clothes|medical gown|examination gown)\b",
    re.I,
)
TEST_VERB_MARKERS = (
    "performing",
    "resistance",
    "reflex hammer",
    "reflex test",
    "manual muscle",
    "mmt",
    "muscle test",
    "strength test",
    "hoffmann",
    "babinski",
    "palpat",
    "goniometer",
    "flexion",
    "extension",
    "cranial",
    "pupil",
    "eye movement",
    "plantar",
)
WEAK_TEST_MENTIONS = (
    "compromise accuracy of strength testing",
    "compromise thoroughness",
    "could impact thoroughness",
    "could limit thoroughness",
    "could affect thoroughness",
    "problematic for complete examination",
    "problematic for comp",
)
ROM_KEYS = (
    "range of motion",
    "rom",
    "cervical",
    "lumbar",
    "flexion",
    "extension",
    "rotation",
    "abduction",
    "adduction",
    "goniometer",
    "inclinometer",
)
STRENGTH_KEYS = ("strength", "motor", "5/5", "manual muscle", "mmt", "resistance")
STRENGTH_SIGNAL_KEYS = (
    "resistance",
    "resist",
    "push",
    "pull",
    "break",
    "breakaway",
    "manual muscle",
    "mmt",
    "5/5",
    "grip",
    "deltoid",
    "biceps",
    "triceps",
    "quadriceps",
    "hamstring",
    "muscle test",
    "muscle testing",
    "strength test",
    "strength testing",
    "strength",
    "isometric",
    "contract",
)
ATTIRE_ONLY_PHRASES = (
    "street clothes",
    "street cloth",
    "medical gown",
    "examination gown",
    "proper gown",
    "blue scrubs",
    "wearing scrubs",
    "doctor wearing",
    "regular clothes",
    "fully clothed",
    "full street",
    "not in gown",
    "without gown",
    "through clothing",
    "through cloth",
    "rather than medical gown",
)
CLAIM_TEXT_STOPWORDS = frozenset(
    {
        "throughout",
        "documented",
        "examination",
        "negative",
        "positive",
        "normal",
        "limits",
        "testing",
        "report",
        "patient",
        "doctor",
    }
)
CLUSTER_GAP_SEC = 45.0
MIN_SEPARATE_CLUSTER_GAP_SEC = 120.0
MAX_EVIDENCE_FRAMES = 4
SENSORY_KEYS = ("sensory", "sensation", "light touch", "pinprick", "dermatome")
COORDINATION_KEYS = ("finger-to-nose", "finger to nose", "coordination", "ftn")
MENTAL_KEYS = ("mental status", "alert", "oriented", "mmse", "cognitive")
TIME_KEYS = ("exam_time", "duration", "minute", "minutes")

ROM_CLAIM_HINTS = ("rom", "range_of_motion", "cervical", "lumbar", "thoracic")
ROM_FRAME_TEST_TYPES = (
    "rom",
    "cervical_rom",
    "lumbar_rom",
    "neck_rom",
    "range_of_motion",
    "thoracic_rom",
)
ROM_BODY_REGIONS = (
    "neck",
    "cervical",
    "cervical_spine",
    "lumbar",
    "lumbar_spine",
    "thoracic",
    "thoracic_spine",
)
ROM_NOTE_HINTS = (
    "flexion",
    "extension",
    "rotation",
    "goniometer",
    "inclinometer",
    "neck",
    "cervical",
    "sidebend",
    "side bend",
    "sidebending",
)

PHYSICAL_EXAM_CLAIM_HINTS = (
    "reflex",
    "gait",
    "romberg",
    "cranial",
    "rom",
    "strength",
    "motor",
    "sensory",
    "coordination",
    "palpation",
    "straight_leg",
    "slr",
    "spurl",
    "faber",
    "neer",
    "lachman",
    "mcmurray",
    "babinski",
    "hoffmann",
    "long_tract",
    "pathological",
    "phalens",
    "tinel",
)

# KB visual indicators (minimal import from exam knowledge base)
try:
    from .cme_exam_knowledge_base import EXAMINATION_KNOWLEDGE_BASE

    _CERVICAL_ROM_KB = EXAMINATION_KNOWLEDGE_BASE.get("cervical_rom") or {}
    CERVICAL_ROM_VISUAL_INDICATORS = tuple(_CERVICAL_ROM_KB.get("visual_indicators") or ())
except ImportError:
    CERVICAL_ROM_VISUAL_INDICATORS = ()


def _fa_field(fa: Any, name: str, default: str = "") -> str:
    if isinstance(fa, dict):
        return str(fa.get(name, default) or default)
    return str(getattr(fa, name, default) or default)


def _fa_confidence(fa: Any) -> float:
    try:
        if isinstance(fa, dict):
            return float(fa.get("confidence") or 0.0)
        return float(getattr(fa, "confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def notes_indicate_broll(notes: str) -> bool:
    """True when frame notes describe B-roll / non-exam footage."""
    n = (notes or "").lower()
    return any(p in n for p in BROLL_NOTE_PHRASES)


_EXAMINER_VISIBLE_MARKERS = (
    "doctor in",
    "doctor wearing",
    "doctor is",
    "doctor appears",
    "examiner",
    "alongside",
    "walking behind",
    "walking ahead of",
    "positioned close",
    "hands on",
    "reflex hammer",
    "goniometer",
)


def _examiner_visible_in_frame(fa: Any) -> bool:
    notes = _fa_field(fa, "notes").lower()
    if "doctor not visible" not in notes:
        return True
    return any(m in notes for m in _EXAMINER_VISIBLE_MARKERS)


def _matches(haystack: str, keywords: Iterable[str]) -> bool:
    h = (haystack or "").lower()
    if not h:
        return False
    for k in keywords:
        k = (k or "").strip().lower()
        if not k:
            continue
        if " " in k:
            if k in h:
                return True
            continue
        if k in WORD_BOUNDARY_KEYWORDS or len(k) <= 3:
            if re.search(rf"\b{re.escape(k)}\b", h):
                return True
        elif k in h:
            return True
    return False


def expand_claim_keywords(claim_id: str, claim_text: str) -> List[str]:
    """Keywords for matching frames/observations to a claim (prompt budget helper)."""
    cid = (claim_id or "").lower()
    text = (claim_text or "").lower()
    bag: List[str] = [cid] if cid else []

    families = {
        "reflexes": REFLEX_KEYS,
        "reflex": REFLEX_KEYS,
        "gait": GAIT_KEYS,
        "romberg": GAIT_KEYS,
        "cranial_nerves": CRANIAL_KEYS,
        "cranial nerve": CRANIAL_KEYS,
        "rom": ROM_KEYS,
        "range_of_motion": ROM_KEYS,
        "strength": STRENGTH_KEYS,
        "motor_strength": STRENGTH_KEYS,
        "sensory": SENSORY_KEYS,
        "sensation": SENSORY_KEYS,
        "coordination": COORDINATION_KEYS,
        "mental_status": MENTAL_KEYS,
        "exam_time": TIME_KEYS,
        "long_tract": PATHOLOGICAL_KEYS,
        "long_tract_signs": PATHOLOGICAL_KEYS,
        "hoffmann": PATHOLOGICAL_KEYS,
        "babinski": PATHOLOGICAL_KEYS,
        "pathological": PATHOLOGICAL_KEYS,
    }
    for key, words in families.items():
        if key in cid or key.replace("_", " ") in cid:
            bag.extend(words)

    if any(x in cid for x in ("long_tract", "hoffmann", "babinski", "pathological")):
        bag.extend(PATHOLOGICAL_KEYS)

    for tok in re.split(r"[^a-z0-9]+", text):
        if len(tok) >= 4 and tok.isalpha() and tok not in CLAIM_TEXT_STOPWORDS:
            bag.append(tok)

    seen = set()
    out: List[str] = []
    for w in bag:
        w = (w or "").strip().lower()
        if w and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _frame_is_ambient_non_exam(fa: Any) -> bool:
    tt = _fa_field(fa, "test_type").strip().lower()
    br = _fa_field(fa, "body_region").strip().lower()
    return tt in NON_EXAM_TEST_TYPES and br in NON_EXAM_BODY_REGIONS


def _frame_has_exam_content(fa: Any) -> bool:
    tt = _fa_field(fa, "test_type").strip().lower()
    br = _fa_field(fa, "body_region").strip().lower()
    if tt and tt not in NON_EXAM_TEST_TYPES:
        return True
    if br and br not in NON_EXAM_BODY_REGIONS:
        return True
    notes = _fa_field(fa, "notes").lower()
    if not notes or notes_indicate_broll(notes):
        return False
    if any(n in notes for n in NON_EXAM_NOTE_PHRASES):
        return False
    exam_markers = (
        " test",
        "testing",
        " palpat",
        "reflex",
        "strength",
        "sensory",
        " pinprick",
        "goniometer",
        "hammer",
        " gait",
        " walking",
        " rom ",
        "range of motion",
    )
    padded = f" {notes} "
    return any(m in padded for m in exam_markers) or _matches(notes, ("flexion", "extension", "rotation"))


def is_physical_exam_claim(claim_id: str, claim_text: str) -> bool:
    cid = (claim_id or "").lower()
    if any(x in cid for x in ("exam_time", "duration", "mental_status", "history")):
        return False
    return any(h in cid for h in PHYSICAL_EXAM_CLAIM_HINTS)


def is_rom_claim(claim_id: str, claim_text: str) -> bool:
    cid = (claim_id or "").lower()
    text = (claim_text or "").lower()
    return any(h in cid or h.replace("_", " ") in cid for h in ROM_CLAIM_HINTS) or (
        "range of motion" in text
    )


def is_non_exam_frame(frame_analysis: Any) -> bool:
    """True for B-roll, establishing shots, waiting room, or ambient non-exam frames."""
    notes = _fa_field(frame_analysis, "notes")
    if notes_indicate_broll(notes):
        return True
    if not _examiner_visible_in_frame(frame_analysis):
        return True

    establishing = _fa_field(frame_analysis, "establishing_shot").strip().lower()
    if establishing in ("true", "1", "yes"):
        return True

    tt = _fa_field(frame_analysis, "test_type").strip().lower()
    br = _fa_field(frame_analysis, "body_region").strip().lower()

    if tt in ("none", "conversation", "") and br in NON_EXAM_BODY_REGIONS:
        if not _frame_has_exam_content(frame_analysis):
            return True

    if _frame_is_ambient_non_exam(frame_analysis) and not _frame_has_exam_content(frame_analysis):
        return True

    visibility = _fa_field(frame_analysis, "visibility").strip().lower()
    if visibility == "obscured" and _fa_confidence(frame_analysis) < 0.25:
        if not _frame_has_exam_content(frame_analysis):
            return True

    return False


def _frame_matches_rom_requirement(fa: Any, claim_id: str = "") -> bool:
    tt = _fa_field(fa, "test_type").lower()
    br = _fa_field(fa, "body_region").lower()
    notes = _fa_field(fa, "notes")
    cid = (claim_id or "").lower()

    if "cervical" in cid or cid.endswith("_neck") or cid == "neck_rom":
        if any(x in br for x in ("neck", "cervical", "cervical_spine")):
            return True
        if any(x in tt for x in ("cervical_rom", "neck_rom")):
            return True
        return _matches(notes, ROM_NOTE_HINTS)

    if "lumbar" in cid:
        lumbar_regions = ("lumbar", "lumbar_spine")
        lumbar_notes = ("lumbar", "flexion", "extension", "goniometer", "inclinometer")
        if any(x in br for x in lumbar_regions):
            return True
        if "lumbar_rom" in tt:
            return True
        return _matches(notes, lumbar_notes)

    if any(x in tt for x in ROM_FRAME_TEST_TYPES):
        return True
    if any(x in br for x in ROM_BODY_REGIONS):
        return True
    return _matches(notes, ROM_NOTE_HINTS)


def _frame_is_pure_gait_frame(fa: Any) -> bool:
    tt = _fa_field(fa, "test_type").strip().lower()
    notes = _fa_field(fa, "notes").lower()
    if tt in ("gait", "romberg"):
        return True
    if any(m in notes for m in GAIT_ONLY_MARKERS):
        return True
    if _matches(notes, ("gait", "walking", "hallway")) and "hallway" in notes:
        return True
    return False


def _frame_has_cranial_exam_signal(fa: Any) -> bool:
    tt = _fa_field(fa, "test_type").strip().lower()
    if "cranial" in tt:
        return True
    if _frame_is_pure_gait_frame(fa):
        return False
    combined = _frame_combined_exam_text(fa)
    strict_markers = (
        "cranial nerve",
        "cranial examination",
        "head/cranial",
        "eye movement",
        "extraocular",
        "pupil",
        "pupillary",
        "facial nerve",
        "smile test",
        "cn ii",
        "cn iii",
    )
    if _matches(combined, strict_markers):
        return True
    if any(x in combined for x in ("hallway", "corridor", "gait assessment", "during gait")):
        return False
    return False


def _frame_has_pathological_signal(fa: Any) -> bool:
    tt = _fa_field(fa, "test_type").strip().lower()
    if any(x in tt for x in ("hoffmann", "babinski", "pathological", "reflex")):
        return True
    combined = _frame_combined_exam_text(fa)
    return _matches(combined, PATHOLOGICAL_KEYS) or _matches(combined, REFLEX_KEYS)


def _has_described_test_action(notes: str) -> bool:
    lower = (notes or "").lower().strip()
    if not lower:
        return False
    if any(w in lower for w in WEAK_TEST_MENTIONS):
        return False
    return any(v in lower for v in TEST_VERB_MARKERS)


def _notes_primarily_attire_complaint(notes: str) -> bool:
    """True when >60% of note text is attire/gown/thoroughness and no test verb."""
    text = (notes or "").strip()
    if not text:
        return False
    lower = text.lower()
    if not any(p in lower for p in ATTIRE_ONLY_PHRASES):
        return False
    attire_chars = sum(len(m.group()) for m in ATTIRE_COMPLAINT_RE.finditer(lower))
    ratio = attire_chars / max(len(lower), 1)
    return ratio > 0.6 and not _has_described_test_action(text)


def _notes_lacks_positive_exam_description(notes: str) -> bool:
    """Reject vague 'the testing' / attire-only notes for strength claims."""
    lower = (notes or "").lower().strip()
    if not lower:
        return True
    if any(w in lower for w in WEAK_TEST_MENTIONS):
        strong = (
            "performing",
            "resistance testing",
            "manual muscle",
            "push against",
            "breakaway",
            "isometric",
        )
        if not any(p in lower for p in strong):
            return True
    if _notes_primarily_attire_complaint(lower) or _notes_are_attire_only(lower):
        return True
    if any(p in lower for p in STRENGTH_POSITIVE_MARKERS):
        return False
    if "the testing" in lower or "the maneuver" in lower or "focused on the examination" in lower:
        return True
    return False


def _truncate_at_sentence_boundary(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    chunk = text[:max_chars]
    for sep in (". ", "! ", "? "):
        idx = chunk.rfind(sep)
        if idx > max(40, max_chars // 3):
            return chunk[: idx + 1].strip()
    sp = chunk.rfind(" ")
    if sp > max(40, max_chars // 3):
        return chunk[:sp].strip() + "."
    return chunk.strip()


def _strip_attire_boilerplate_prefix(notes: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", (notes or "").strip())
    kept: List[str] = []
    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue
        if _notes_primarily_attire_complaint(s) and not _has_described_test_action(s):
            continue
        if _notes_are_attire_only(s):
            continue
        kept.append(s)
    return " ".join(kept).strip()


def clean_evidence_note_for_display(notes: str, *, max_sentences: int = 2) -> str:
    """Full sentences for UI; strip attire boilerplate; no mid-word chop."""
    cleaned = _strip_attire_boilerplate_prefix(notes)
    if not cleaned:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    picked = [s.strip() for s in sentences if s.strip()][:max_sentences]
    return " ".join(picked).strip()

def _frame_matches_reflex_requirement(fa: Any) -> bool:
    tt = _fa_field(fa, "test_type").lower()
    notes = _fa_field(fa, "notes").lower()
    equipment = _fa_field(fa, "equipment_visible").lower()
    if "reflex" in tt:
        return True
    if _matches(notes, REFLEX_KEYS):
        return True
    if "reflex_hammer" in equipment or "hammer" in equipment:
        return True
    return False


def _frame_matches_pathological_requirement(fa: Any) -> bool:
    if _frame_is_pure_gait_frame(fa) and not _frame_has_pathological_signal(fa):
        return False
    return _frame_has_pathological_signal(fa)


def _frame_matches_gait_requirement(fa: Any) -> bool:
    tt = _fa_field(fa, "test_type").lower()
    notes = _fa_field(fa, "notes").lower()
    if tt in ("gait", "romberg"):
        return True
    return _matches(notes, GAIT_KEYS)


def _frame_combined_exam_text(fa: Any) -> str:
    notes = _fa_field(fa, "notes")
    details = _fa_field(fa, "test_details")
    return f"{notes} {details}".strip().lower()


def _frame_has_strength_signal(fa: Any) -> bool:
    combined = _frame_combined_exam_text(fa)
    if not combined:
        return False
    return _matches(combined, STRENGTH_SIGNAL_KEYS) or _matches(combined, ("5/5", "mmt"))


def _frame_has_arm_shoulder_mmt_signal(fa: Any) -> bool:
    combined = _frame_combined_exam_text(fa)
    return any(
        x in combined
        for x in (
            "arm/shoulder",
            "shoulder",
            "arm strength",
            "manual muscle",
            "upper extremit",
            "deltoid",
            "biceps",
        )
    )


def _notes_are_attire_only(notes: str) -> bool:
    """True when notes focus on clothing/gown/scrubs without describing the exam maneuver."""
    lower = (notes or "").lower().strip()
    if not lower:
        return False
    if not any(p in lower for p in ATTIRE_ONLY_PHRASES):
        return False
    if _matches(lower, STRENGTH_SIGNAL_KEYS):
        return False
    exam_action = (
        "resistance",
        "push",
        "pull",
        "break",
        "manual muscle",
        "mmt",
        "muscle test",
        "strength test",
        "reflex",
        "palpat",
        "goniometer",
        "rom ",
        "range of motion",
        "flexion",
        "extension",
        "hammer",
        "pinprick",
        "gait",
        "walking",
    )
    return not any(m in lower for m in exam_action)


def _frame_matches_strength_requirement(fa: Any) -> bool:
    tt = _fa_field(fa, "test_type").lower()
    notes = _fa_field(fa, "notes")
    details = _fa_field(fa, "test_details").lower()

    if tt in NON_EXAM_TEST_TYPES:
        return False
    if not _frame_has_strength_signal(fa):
        return False
    if _notes_are_attire_only(notes) or _notes_primarily_attire_complaint(notes):
        return False

    details_positive = bool(details) and (
        _matches(details, STRENGTH_SIGNAL_KEYS)
        or any(p in details for p in STRENGTH_POSITIVE_MARKERS)
    )
    if _notes_lacks_positive_exam_description(notes) and not details_positive:
        return False
    if _notes_lacks_positive_exam_description(notes) and details_positive:
        if not _frame_has_arm_shoulder_mmt_signal(fa):
            return False

    if "strength" in tt or "motor" in tt:
        return True
    return _matches(notes, STRENGTH_KEYS)


def _frame_matches_sensory_requirement(fa: Any) -> bool:
    tt = _fa_field(fa, "test_type").lower()
    notes = _fa_field(fa, "notes").lower()
    if "sensory" in tt:
        return True
    return _matches(notes, SENSORY_KEYS)


def _frame_matches_coordination_requirement(fa: Any) -> bool:
    tt = _fa_field(fa, "test_type").lower()
    notes = _fa_field(fa, "notes").lower()
    if "coordination" in tt:
        return True
    return _matches(notes, COORDINATION_KEYS)


def _frame_matches_cranial_requirement(fa: Any) -> bool:
    if _frame_is_pure_gait_frame(fa) and not _frame_has_cranial_exam_signal(fa):
        return False
    return _frame_has_cranial_exam_signal(fa)


def frame_supports_claim(
    frame: Any,
    claim_id: str,
    claim_text: str,
    *,
    physical_exam: Optional[bool] = None,
    rom_claim: Optional[bool] = None,
) -> bool:
    """Claim-specific visual requirements (ROM region, reflex hammer, etc.)."""
    if physical_exam is None:
        physical_exam = is_physical_exam_claim(claim_id, claim_text)
    if rom_claim is None:
        rom_claim = is_rom_claim(claim_id, claim_text)

    if not physical_exam:
        return True

    cid = (claim_id or "").lower()

    if rom_claim and not _frame_matches_rom_requirement(frame, claim_id):
        return False

    if "reflex" in cid and not _frame_matches_reflex_requirement(frame):
        return False
    if any(x in cid for x in ("hoffmann", "babinski", "long_tract", "pathological")):
        if not _frame_matches_pathological_requirement(frame):
            return False
    if "gait" in cid or "romberg" in cid:
        if not _frame_matches_gait_requirement(frame):
            return False
    if "strength" in cid or "motor" in cid:
        if not _frame_matches_strength_requirement(frame):
            return False
    if "sensory" in cid or "sensation" in cid:
        if not _frame_matches_sensory_requirement(frame):
            return False
    if "coordination" in cid or "cerebellar" in cid:
        if not _frame_matches_coordination_requirement(frame):
            return False
    if "cranial" in cid:
        if not _frame_matches_cranial_requirement(frame):
            return False

    return True


def frame_passes_quality_gates(
    frame: Any,
    claim_id: str,
    claim_text: str,
    *,
    physical_exam: Optional[bool] = None,
    rom_claim: Optional[bool] = None,
) -> bool:
    """Both non-exam and claim-specific gates."""
    if is_non_exam_frame(frame):
        return False
    return frame_supports_claim(
        frame,
        claim_id,
        claim_text,
        physical_exam=physical_exam,
        rom_claim=rom_claim,
    )


def filter_frames_for_claim(
    frames: List[Any],
    claim_id: str,
    claim_text: str,
    *,
    max_frames: Optional[int] = None,
) -> List[Any]:
    """Keyword match + quality gates; chronological order."""
    keywords = expand_claim_keywords(claim_id, claim_text)
    if not keywords:
        return []

    physical_exam = is_physical_exam_claim(claim_id, claim_text)
    rom_claim = is_rom_claim(claim_id, claim_text)

    matches: List[Any] = []
    for fa in frames or []:
        keyword_hit = (
            _matches(_fa_field(fa, "test_type"), keywords)
            or _matches(_fa_field(fa, "body_region"), keywords)
            or _matches(_fa_field(fa, "notes"), keywords)
        )
        if not keyword_hit:
            continue
        if not frame_passes_quality_gates(
            fa, claim_id, claim_text, physical_exam=physical_exam, rom_claim=rom_claim
        ):
            continue
        matches.append(fa)

    def _ts(fa: Any) -> float:
        try:
            if isinstance(fa, dict):
                return float(fa.get("timestamp_sec") or 0.0)
            return float(getattr(fa, "timestamp_sec", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    matches.sort(key=_ts)
    if max_frames is not None:
        return select_evidence_frames_for_claim(
            matches, claim_id, claim_text, max_frames=max_frames
        )
    return matches


def _score_evidence_frame(
    fa: Any,
    claim_id: str,
    claim_text: str,
    *,
    physical_exam: Optional[bool] = None,
    rom_claim: Optional[bool] = None,
) -> float:
    if physical_exam is None:
        physical_exam = is_physical_exam_claim(claim_id, claim_text)
    if rom_claim is None:
        rom_claim = is_rom_claim(claim_id, claim_text)

    score = _fa_confidence(fa)
    cid = (claim_id or "").lower()
    if "strength" in cid or "motor" in cid:
        score = min(score, 0.75)
    if frame_supports_claim(
        fa, claim_id, claim_text, physical_exam=physical_exam, rom_claim=rom_claim
    ):
        score += 0.35
    desc = evidence_description_for_frame(fa, claim_id)
    if desc:
        score += 0.25
    if ("strength" in cid or "motor" in cid) and _frame_has_strength_signal(fa):
        score += 0.2
    if ("strength" in cid or "motor" in cid) and _frame_has_arm_shoulder_mmt_signal(fa):
        score += 0.15
    return score


def _cluster_frames_by_timestamp(frames: List[Any], *, gap_sec: float = CLUSTER_GAP_SEC) -> List[List[Any]]:
    if not frames:
        return []

    def _ts(fa: Any) -> float:
        try:
            if isinstance(fa, dict):
                return float(fa.get("timestamp_sec") or 0.0)
            return float(getattr(fa, "timestamp_sec", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    ordered = sorted(frames, key=_ts)
    clusters: List[List[Any]] = [[ordered[0]]]
    for fa in ordered[1:]:
        if _ts(fa) - _ts(clusters[-1][-1]) <= gap_sec:
            clusters[-1].append(fa)
        else:
            clusters.append([fa])
    return clusters


def select_evidence_frames_for_claim(
    frames: List[Any],
    claim_id: str,
    claim_text: str,
    *,
    max_frames: int = MAX_EVIDENCE_FRAMES,
) -> List[Any]:
    """Pick 2–4 representative frames, clustering nearby timestamps."""
    if not frames:
        return []

    physical_exam = is_physical_exam_claim(claim_id, claim_text)
    rom_claim = is_rom_claim(claim_id, claim_text)
    max_frames = max(1, int(max_frames or MAX_EVIDENCE_FRAMES))

    def _score(fa: Any) -> float:
        return _score_evidence_frame(
            fa, claim_id, claim_text, physical_exam=physical_exam, rom_claim=rom_claim
        )

    clusters = _cluster_frames_by_timestamp(frames)
    if not clusters:
        return []

    def _ts(fa: Any) -> float:
        try:
            if isinstance(fa, dict):
                return float(fa.get("timestamp_sec") or 0.0)
            return float(getattr(fa, "timestamp_sec", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _cluster_score(cluster: List[Any]) -> float:
        scores = [_score(fa) for fa in cluster]
        if not scores:
            return 0.0
        return max(scores) + 0.03 * min(len(cluster), 5)

    ranked = sorted(
        clusters,
        key=lambda c: (
            -_cluster_score(c),
            -sum(_frame_has_arm_shoulder_mmt_signal(fa) for fa in c),
            _ts(c[0]),
        ),
    )
    selected: List[Any] = []
    selected_ts: List[float] = []

    cid = (claim_id or "").lower()
    min_cluster_gap = (
        300.0 if ("strength" in cid or "motor" in cid) else MIN_SEPARATE_CLUSTER_GAP_SEC
    )

    for idx, cluster in enumerate(ranked):
        if idx > 0 and selected_ts:
            gap = _ts(cluster[0]) - max(selected_ts)
            if gap < min_cluster_gap:
                continue
        if idx == 0:
            per_cluster = min(max_frames, len(cluster))
        else:
            per_cluster = max(1, max_frames // 2)
        for fa in sorted(cluster, key=_score, reverse=True)[:per_cluster]:
            if len(selected) >= max_frames:
                break
            selected.append(fa)
            selected_ts.append(_ts(fa))
        if len(selected) >= max_frames:
            break

    selected.sort(key=_ts)
    return selected[:max_frames]


def _fmt_frame_line(fa: Any) -> str:
    g = (lambda k, d="": fa.get(k, d) if isinstance(fa, dict) else getattr(fa, k, d))
    fid = str(g("frame_id", "") or "")
    ts = float(g("timestamp_sec", 0.0) or 0.0)
    tt = str(g("test_type", "") or "")
    br = str(g("body_region", "") or "")
    vis = str(g("visibility", "") or "")
    occ = str(g("occlusion_notes", "") or "")
    notes = str(g("notes", "") or "")
    try:
        conf = float(g("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    parts = [
        f"[{fid} @ {ts:.1f}s]",
        f"test={tt or 'none'}",
        f"body={br or 'none'}",
        f"vis={vis or 'unknown'}",
        f"conf={conf:.2f}",
    ]
    if occ:
        parts.append(f"occluded={occ[:60]}")
    line = " ".join(parts)
    if notes:
        display_note = clean_evidence_note_for_display(notes, max_sentences=2)
        if display_note:
            line += f" :: {display_note}"
    return line


def summarize_video_evidence(frames: List[Any], *, char_budget: int = 4000) -> str:
    """Format frame lines for prompts; never includes B-roll / non-exam frames."""
    seen_notes: set[str] = set()
    lines: List[str] = []
    for fa in frames or []:
        if is_non_exam_frame(fa):
            continue
        note = clean_evidence_note_for_display(_fa_field(fa, "notes"), max_sentences=2)
        if note and note in seen_notes:
            continue
        if note:
            seen_notes.add(note)
        lines.append(_fmt_frame_line(fa))
        if len(lines) >= 3:
            break

    if not lines:
        return (
            "(no frames matched this claim's keywords; the relevant body region / "
            "test was not sampled or not detected)"
        )
    summary = "\n".join(lines)
    if len(summary) > char_budget:
        summary = _truncate_at_sentence_boundary(summary, char_budget - 20)
        if not summary.endswith("[truncated]"):
            summary = summary.rstrip(".") + "\n... [truncated]"
    return summary


def cluster_evidence_timestamps(
    frames: List[Any],
    *,
    max_stamps: int = MAX_EVIDENCE_FRAMES,
    gap_sec: float = CLUSTER_GAP_SEC,
) -> List[float]:
    """Pick best-cluster display timestamps; dedupe by rounded second."""
    if not frames:
        return []

    def _ts(fa: Any) -> float:
        try:
            if isinstance(fa, dict):
                return float(fa.get("timestamp_sec") or 0.0)
            return float(getattr(fa, "timestamp_sec", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    clusters = _cluster_frames_by_timestamp(list(frames), gap_sec=gap_sec)
    if not clusters:
        return []

    def _cluster_score(cluster: List[Any]) -> float:
        return sum(_fa_confidence(fa) for fa in cluster) + 0.05 * len(cluster)

    ranked = sorted(clusters, key=_cluster_score, reverse=True)
    stamps: List[float] = []
    for cluster in ranked:
        rep = max(cluster, key=_fa_confidence)
        stamps.append(round(_ts(rep)))
        if len(stamps) >= max(1, int(max_stamps)):
            break

    unique = sorted(set(stamps))
    return unique[: max(1, int(max_stamps))]


def evidence_description_for_frame(fa: Any, claim_id: str = "") -> str:
    """Deposition-useful description; prefers maneuver text over attire boilerplate."""
    notes = str(_fa_field(fa, "notes") or "").strip()
    details = str(_fa_field(fa, "test_details") or "").strip()
    cid = (claim_id or "").lower()

    if ("strength" in cid or "motor" in cid) and _frame_has_strength_signal(fa):
        details_usable = bool(details) and (
            _matches(details, STRENGTH_SIGNAL_KEYS)
            or any(p in details.lower() for p in STRENGTH_POSITIVE_MARKERS)
        )
        if notes and not _notes_lacks_positive_exam_description(notes):
            cleaned = clean_evidence_note_for_display(notes, max_sentences=2)
            if cleaned:
                return cleaned
        if details_usable and not _notes_are_attire_only(details):
            if not _notes_lacks_positive_exam_description(notes) or _frame_has_arm_shoulder_mmt_signal(
                fa
            ):
                return clean_evidence_note_for_display(details, max_sentences=2)
        return ""

    cleaned_notes = clean_evidence_note_for_display(notes, max_sentences=2)
    if cleaned_notes and not _notes_are_attire_only(cleaned_notes):
        return cleaned_notes
    cleaned_details = clean_evidence_note_for_display(details, max_sentences=2)
    if cleaned_details and not _notes_are_attire_only(cleaned_details):
        return cleaned_details
    return cleaned_notes if cleaned_notes and not _notes_are_attire_only(cleaned_notes) else ""


def evidence_notes_are_usable(
    notes: str,
    claim_id: str = "",
    *,
    frame: Any = None,
) -> bool:
    """Filter verdict evidence notes / quotes shown in UI or offline scripts."""
    if frame is not None:
        cid = (claim_id or "").lower()
        if cid and is_physical_exam_claim(claim_id, ""):
            if not frame_passes_quality_gates(frame, claim_id, ""):
                return False
        desc = evidence_description_for_frame(frame, claim_id)
        if desc:
            return True
        notes = str(_fa_field(frame, "notes") or notes or "")

    text = (notes or "").strip()
    if not text:
        return False
    lower = text.lower()
    if notes_indicate_broll(lower):
        return False
    if ADMIN_NOISE_RE.search(lower):
        return False
    if "doctor not visible" in lower and not any(m in lower for m in _EXAMINER_VISIBLE_MARKERS):
        return False
    if _notes_are_attire_only(text) or _notes_primarily_attire_complaint(text):
        return False

    cid = (claim_id or "").lower()
    if cid:
        if "cranial" in cid:
            if _frame_is_pure_gait_frame({"notes": text, "test_type": ""}) and not _matches(
                lower, CRANIAL_EXAM_MARKERS
            ):
                return False
        if any(x in cid for x in ("hoffmann", "babinski", "long_tract", "pathological")):
            if _frame_is_pure_gait_frame({"notes": text, "test_type": ""}) and not _matches(
                lower, PATHOLOGICAL_KEYS
            ):
                return False
        if ("strength" in cid or "motor" in cid) and _notes_lacks_positive_exam_description(text):
            return False

    return True
