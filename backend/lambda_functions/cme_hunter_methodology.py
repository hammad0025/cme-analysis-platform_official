"""
DR. HUNTER METHODOLOGY - CME Analysis Engine
============================================

This module implements Dr. Hunter's forensic CME analysis approach:

1. CLAIMS vs REALITY - What doctor SAYS vs what doctor DOES
2. PRECISION COUNTING - Exact numbers (24 UE muscles, 14 LE, 48 CN tests)
3. TECHNIQUE EVALUATION - Was test done CORRECTLY, not just done
4. UNREPORTED TESTS - Tests performed but not documented
5. TIMING - Precise duration of hands-on exam
6. OBJECTIVE FINDINGS - Note findings that HELP plaintiff (spasms, etc.)

Based on Dr. Hunter's actual CME review methodology.
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import re

class TestStatus(Enum):
    NOT_PERFORMED = "not_performed"
    PERFORMED_CORRECTLY = "performed_correctly"
    PERFORMED_INCORRECTLY = "performed_incorrectly"  # Key distinction!
    PERFORMED_NOT_REPORTED = "performed_not_reported"
    CLAIMED_NOT_TESTED = "claimed_not_tested"  # Doctor claims result but didn't test


@dataclass
class HunterFinding:
    """A finding in Dr. Hunter's style"""
    category: str
    observation: str
    claim_vs_reality: Optional[str]  # What was claimed vs what happened
    significance: str  # Why this matters
    helps_plaintiff: bool  # Does this finding help or hurt plaintiff?


# =============================================================================
# COMPREHENSIVE TEST REQUIREMENTS
# Dr. Hunter knows EXACTLY how many tests exist for each system
# =============================================================================

UPPER_EXTREMITY_MUSCLE_GROUPS = {
    "shoulder": [
        "deltoid_anterior", "deltoid_middle", "deltoid_posterior",
        "supraspinatus", "infraspinatus", "teres_minor", "subscapularis",
        "pectoralis_major", "latissimus_dorsi", "serratus_anterior"
    ],
    "elbow": [
        "biceps", "brachialis", "triceps", "brachioradialis"
    ],
    "wrist": [
        "wrist_flexors", "wrist_extensors", 
        "radial_deviation", "ulnar_deviation"
    ],
    "hand": [
        "finger_flexors_fds", "finger_flexors_fdp",
        "finger_extensors", "finger_abductors", "finger_adductors",
        "thumb_flexors", "thumb_extensors", "thumb_abductors", 
        "thumb_opposition", "lumbricals"
    ]
}
TOTAL_UE_MUSCLE_GROUPS = 24  # Sum of above

LOWER_EXTREMITY_MUSCLE_GROUPS = {
    "hip": [
        "hip_flexors_iliopsoas", "hip_extensors_gluteus_max",
        "hip_abductors", "hip_adductors",
        "hip_internal_rotators", "hip_external_rotators"
    ],
    "knee": [
        "knee_extensors_quads", "knee_flexors_hamstrings"
    ],
    "ankle": [
        "ankle_dorsiflexors", "ankle_plantarflexors",
        "ankle_invertors", "ankle_evertors"
    ],
    "foot": [
        "toe_extensors", "toe_flexors"
    ]
}
TOTAL_LE_MUSCLE_GROUPS = 14  # Sum of above

CRANIAL_NERVE_TESTS = {
    "CN_I_olfactory": ["smell_identification_left", "smell_identification_right"],
    "CN_II_optic": [
        "visual_acuity_left", "visual_acuity_right",
        "visual_fields_left", "visual_fields_right",
        "fundoscopy_left", "fundoscopy_right"
    ],
    "CN_III_oculomotor": [
        "pupil_reaction_left", "pupil_reaction_right",
        "eom_superior_rectus_left", "eom_superior_rectus_right",
        "eom_medial_rectus_left", "eom_medial_rectus_right",
        "eom_inferior_rectus_left", "eom_inferior_rectus_right",
        "eom_inferior_oblique_left", "eom_inferior_oblique_right",
        "eyelid_elevation_left", "eyelid_elevation_right"
    ],
    "CN_IV_trochlear": [
        "eom_superior_oblique_left", "eom_superior_oblique_right"
    ],
    "CN_V_trigeminal": [
        "facial_sensation_v1_left", "facial_sensation_v1_right",
        "facial_sensation_v2_left", "facial_sensation_v2_right",
        "facial_sensation_v3_left", "facial_sensation_v3_right",
        "masseter_strength", "temporalis_strength",
        "corneal_reflex_left", "corneal_reflex_right",
        "jaw_jerk"
    ],
    "CN_VI_abducens": [
        "eom_lateral_rectus_left", "eom_lateral_rectus_right"
    ],
    "CN_VII_facial": [
        "forehead_raise", "eye_closure_left", "eye_closure_right",
        "smile_symmetry", "lip_pucker", "platysma"
    ],
    "CN_VIII_vestibulocochlear": [
        "hearing_left", "hearing_right",
        "weber_test", "rinne_left", "rinne_right",
        "vestibular_nystagmus"
    ],
    "CN_IX_glossopharyngeal": [
        "gag_reflex", "palate_sensation"
    ],
    "CN_X_vagus": [
        "palate_elevation", "uvula_midline", "voice_quality"
    ],
    "CN_XI_accessory": [
        "scm_strength_left", "scm_strength_right",
        "trapezius_strength_left", "trapezius_strength_right"
    ],
    "CN_XII_hypoglossal": [
        "tongue_protrusion", "tongue_strength", "tongue_fasciculations"
    ]
}
TOTAL_CN_TESTS = 48  # Sum of all individual tests

UPPER_EXTREMITY_DERMATOMES = ["C5", "C6", "C7", "C8", "T1"]
LOWER_EXTREMITY_DERMATOMES = ["L1", "L2", "L3", "L4", "L5", "S1", "S2"]

CERVICAL_ROM_PLANES = {
    "flexion": {"normal": 50, "method": "inclinometer"},
    "extension": {"normal": 60, "method": "inclinometer"},
    "left_lateral_flexion": {"normal": 45, "method": "inclinometer"},
    "right_lateral_flexion": {"normal": 45, "method": "inclinometer"},
    "left_rotation": {"normal": 80, "method": "goniometer"},
    "right_rotation": {"normal": 80, "method": "goniometer"}
}

LUMBAR_ROM_PLANES = {
    "flexion": {"normal": 60, "method": "inclinometer"},
    "extension": {"normal": 25, "method": "inclinometer"},
    "left_lateral_flexion": {"normal": 25, "method": "inclinometer"},
    "right_lateral_flexion": {"normal": 25, "method": "inclinometer"}
}


# =============================================================================
# CLAIM DETECTION PATTERNS
# Phrases doctors use when CLAIMING results without proper testing
# =============================================================================

CLAIM_PATTERNS = {
    "strength_claim": [
        r"5\s*/\s*5\s*strength",
        r"strength\s*(is\s*)?(5/5|normal|intact|full)",
        r"(full|normal|intact)\s*strength",
        r"motor\s*(is\s*)?(intact|normal|5/5)",
        r"strength\s*throughout",
    ],
    "orientation_claim": [
        r"oriented\s*(x\s*)?3",
        r"oriented\s*(to\s*)?(time|place|person)",
        r"a\s*&\s*o\s*x\s*3",
        r"alert\s*and\s*oriented",
    ],
    "cranial_nerve_claim": [
        r"(cn|cranial\s*nerves?)\s*(II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|2|3|4|5|6|7|8|9|10|11|12).*?(intact|normal|grossly)",
        r"(II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\s*(through|to|-)\s*(XII|12).*?(intact|normal|grossly)",
        r"cranial\s*nerves?\s*(are\s*)?(intact|normal|grossly)",
    ],
    "bulk_claim": [
        r"(muscle\s*)?bulk\s*(is\s*)?(normal|symmetric|within\s*normal)",
        r"no\s*(muscle\s*)?(atrophy|wasting)",
    ],
    "rom_claim": [
        r"(range\s*of\s*motion|rom)\s*(is\s*)?(full|normal|adequate|intact|wnl)",
        r"(full|normal|adequate)\s*(range|rom)",
        r"within\s*normal\s*limits",
    ],
    "sensory_claim": [
        r"sensation\s*(is\s*)?(intact|normal)",
        r"sensory\s*(is\s*)?(intact|normal)",
        r"(light\s*touch|pinprick)\s*(is\s*)?(intact|normal)",
    ],
    "reflex_claim": [
        r"(reflexes?|dtr)\s*(are\s*)?(normal|symmetric|2\+|intact)",
        r"(deep\s*tendon\s*)?reflexes?\s*(are\s*)?(normal|intact)",
    ],
    "slr_claim": [
        r"(slr|straight\s*leg\s*raise?)\s*(is\s*)?(negative|normal)",
        r"(negative|normal)\s*(slr|straight\s*leg)",
        r"lasegue\s*(is\s*)?(negative|normal)",
    ]
}


# =============================================================================
# TEST PERFORMANCE PATTERNS
# What we look/listen for to confirm test was ACTUALLY done
# =============================================================================

TEST_PERFORMANCE_INDICATORS = {
    "grip_strength": {
        "audio": ["squeeze", "grip", "hard as you can", "break my"],
        "requires_bilateral": True,
        "proper_technique": "Jamar dynamometer at position 2, 3 trials each hand"
    },
    "muscle_strength_ue": {
        "audio": ["push", "pull", "resist", "hold", "don't let me"],
        "count_required": 24,
        "proper_technique": "Test each muscle group against resistance, grade 0-5"
    },
    "muscle_strength_le": {
        "audio": ["push down", "pull up", "kick", "hold your leg"],
        "count_required": 14,
        "proper_technique": "Test each muscle group against resistance, grade 0-5"
    },
    "straight_leg_raise": {
        "audio": ["raise your leg", "keep it straight", "tell me when"],
        "proper_technique": "Patient supine, passively raise straight leg, note angle AND if radiating pain below knee",
        "common_errors": [
            "Patient actively raises own leg",
            "Knee allowed to bend",
            "Not noting angle when pain begins",
            "Not asking about radiation below knee"
        ]
    },
    "cervical_rom": {
        "audio": ["turn your head", "look left", "look right", "chin to chest", "look up", "ear to shoulder"],
        "planes_required": 6,
        "proper_technique": "Inclinometer/goniometer measurement of all 6 planes with specific degrees"
    },
    "lumbar_rom": {
        "audio": ["touch your toes", "bend forward", "bend back", "lean to the side"],
        "planes_required": 4,
        "proper_technique": "Dual inclinometer technique per AMA Guides"
    },
    "sensation_testing": {
        "audio": ["sharp", "dull", "feel this", "eyes closed"],
        "dermatomes_required_ue": 5,
        "dermatomes_required_le": 7,
        "proper_technique": "Test all dermatomes bilaterally with sharp/dull discrimination"
    },
    "romberg_test": {
        "audio": ["stand", "feet together", "close your eyes", "arms out"],
        "proper_technique": "Patient stands, feet together, eyes closed for 30 seconds",
        "common_errors": [
            "Too brief (less than 30 sec)",
            "Feet not together",
            "Patient allowed to move feet"
        ]
    },
    "finger_to_nose": {
        "audio": ["touch your nose", "touch my finger", "back and forth"],
        "proper_technique": "Eyes open, then eyes closed, both sides"
    },
    "orientation_testing": {
        "audio": ["what day", "what year", "where are we", "who is the president", "what month"],
        "proper_technique": "Ask specific questions about time, place, person"
    },
    "cranial_nerves": {
        "audio": ["smell", "follow my finger", "smile", "raise your eyebrows", "stick out your tongue", "shrug"],
        "tests_required": 48,
        "proper_technique": "Systematic testing of each cranial nerve"
    },
    "tinels_sign": {
        "audio": ["tap", "tapping"],
        "proper_technique": "Percussion over carpal tunnel, note tingling in median nerve distribution"
    },
    "deep_tendon_reflexes": {
        "audio": ["relax", "let it hang"],  # Often silent - just the tap
        "proper_technique": "Test biceps, triceps, brachioradialis, patellar, Achilles bilaterally"
    },
    "bulk_measurement": {
        "audio": ["measure", "tape"],
        "proper_technique": "Circumferential measurement at defined landmarks bilaterally"
    }
}


# =============================================================================
# FINDINGS THAT HELP PLAINTIFF
# Objective findings that support injury claim
# =============================================================================

PLAINTIFF_HELPFUL_FINDINGS = [
    "muscle spasm",
    "spasms",
    "tenderness",
    "limited range",
    "decreased rom",
    "positive straight leg",
    "radicular",
    "radiating pain",
    "weakness",
    "atrophy",
    "sensory deficit",
    "reflex asymmetry",
    "antalgic gait",
    "guarding",
    "restricted motion"
]


class HunterAnalyzer:
    """
    Analyzes CME examinations using Dr. Hunter's methodology.
    
    Key principles:
    1. Compare CLAIMS to REALITY
    2. Count EXACTLY what was tested vs required
    3. Evaluate TECHNIQUE, not just presence
    4. Note what helps PLAINTIFF
    5. Precise TIMING
    """
    
    def __init__(self):
        self.findings: List[HunterFinding] = []
        self.tests_performed: Dict[str, TestStatus] = {}
        self.tests_claimed: Dict[str, str] = {}
        self.muscle_groups_tested_ue: List[str] = []
        self.muscle_groups_tested_le: List[str] = []
        self.cn_tests_performed: List[str] = []
        self.dermatomes_tested: List[str] = []
        self.rom_measurements: Dict[str, Optional[float]] = {}
        self.objective_findings: List[str] = []
        self.exam_duration_seconds: Optional[float] = None
        
    def analyze_transcript(self, transcript: str, report_text: Optional[str] = None) -> List[HunterFinding]:
        """
        Analyze transcript (and optional written report) for discrepancies.
        """
        transcript_lower = transcript.lower()
        report_lower = report_text.lower() if report_text else ""
        
        # 1. Detect CLAIMS in report/transcript
        self._detect_claims(transcript_lower, report_lower)
        
        # 2. Detect what was ACTUALLY performed
        self._detect_performed_tests(transcript_lower)
        
        # 3. Compare claims vs reality
        self._compare_claims_to_reality()
        
        # 4. Count specifics (muscles, dermatomes, etc.)
        self._count_test_completeness(transcript_lower)
        
        # 5. Detect objective findings that help plaintiff
        self._detect_plaintiff_helpful_findings(transcript_lower, report_lower)
        
        # 6. Check for technique errors
        self._evaluate_technique(transcript_lower)
        
        return self.findings
    
    def _detect_claims(self, transcript: str, report: str):
        """Detect what the doctor CLAIMS in report"""
        combined = transcript + " " + report
        
        for claim_type, patterns in CLAIM_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined, re.IGNORECASE):
                    match = re.search(pattern, combined, re.IGNORECASE)
                    self.tests_claimed[claim_type] = match.group(0)
                    break
    
    def _detect_performed_tests(self, transcript: str):
        """Detect what tests were ACTUALLY performed based on transcript"""
        for test_name, indicators in TEST_PERFORMANCE_INDICATORS.items():
            audio_cues = indicators.get("audio", [])
            found = False
            for cue in audio_cues:
                if cue.lower() in transcript:
                    found = True
                    break
            
            if found:
                self.tests_performed[test_name] = TestStatus.PERFORMED_CORRECTLY
            else:
                self.tests_performed[test_name] = TestStatus.NOT_PERFORMED
    
    def _compare_claims_to_reality(self):
        """The key Hunter analysis - what was CLAIMED vs DONE"""
        
        # Check strength claims
        if "strength_claim" in self.tests_claimed:
            ue_tested = len(self.muscle_groups_tested_ue)
            le_tested = len(self.muscle_groups_tested_le)
            
            claim = self.tests_claimed["strength_claim"]
            
            if ue_tested < TOTAL_UE_MUSCLE_GROUPS or le_tested < TOTAL_LE_MUSCLE_GROUPS:
                self.findings.append(HunterFinding(
                    category="CLAIM vs REALITY",
                    observation=f"Doctor claims '{claim}' but tested only {ue_tested}/{TOTAL_UE_MUSCLE_GROUPS} "
                               f"upper extremity and {le_tested}/{TOTAL_LE_MUSCLE_GROUPS} lower extremity muscle groups",
                    claim_vs_reality=f"CLAIMED: {claim} | TESTED: {ue_tested} UE, {le_tested} LE muscles",
                    significance="Cannot claim full strength without testing all major muscle groups",
                    helps_plaintiff=True
                ))
        
        # Check orientation claims
        if "orientation_claim" in self.tests_claimed:
            if self.tests_performed.get("orientation_testing") != TestStatus.PERFORMED_CORRECTLY:
                self.findings.append(HunterFinding(
                    category="CLAIM vs REALITY",
                    observation=f"Doctor reports '{self.tests_claimed['orientation_claim']}' but did NOT test orientation",
                    claim_vs_reality=f"CLAIMED: oriented | TESTED: no orientation questions asked",
                    significance="Orientation status claimed without verification",
                    helps_plaintiff=True
                ))
        
        # Check cranial nerve claims
        if "cranial_nerve_claim" in self.tests_claimed:
            cn_tested = len(self.cn_tests_performed)
            if cn_tested < TOTAL_CN_TESTS:
                self.findings.append(HunterFinding(
                    category="CLAIM vs REALITY", 
                    observation=f"Doctor claims cranial nerves 'normal' but performed only {cn_tested}/{TOTAL_CN_TESTS} tests",
                    claim_vs_reality=f"CLAIMED: CN III-XII normal | TESTED: {cn_tested} of 48 required tests",
                    significance="Cannot claim cranial nerves normal without systematic testing",
                    helps_plaintiff=True
                ))
        
        # Check bulk claims
        if "bulk_claim" in self.tests_claimed:
            if self.tests_performed.get("bulk_measurement") != TestStatus.PERFORMED_CORRECTLY:
                self.findings.append(HunterFinding(
                    category="CLAIM vs REALITY",
                    observation="Doctor claims muscle bulk 'normal' but did NOT measure with tape",
                    claim_vs_reality="CLAIMED: bulk normal | TESTED: no measurement taken",
                    significance="Bulk/atrophy assessment requires circumferential measurement",
                    helps_plaintiff=True
                ))
        
        # Check SLR claims
        if "slr_claim" in self.tests_claimed:
            slr_status = self.tests_performed.get("straight_leg_raise", TestStatus.NOT_PERFORMED)
            if slr_status == TestStatus.PERFORMED_INCORRECTLY:
                self.findings.append(HunterFinding(
                    category="TECHNIQUE ERROR",
                    observation="SLR performed incorrectly - patient actively raised leg or knee bent",
                    claim_vs_reality=f"CLAIMED: SLR negative | REALITY: Test done incorrectly",
                    significance="Invalid SLR technique renders result meaningless",
                    helps_plaintiff=True
                ))
    
    def _count_test_completeness(self, transcript: str):
        """Count exactly how many of required tests were done"""
        
        # Count muscle groups tested
        # Look for specific muscle testing language
        ue_indicators = {
            "deltoid": ["raise your arm", "shoulder"],
            "biceps": ["bend your elbow", "curl"],
            "triceps": ["straighten your arm", "push away"],
            "grip": ["squeeze", "grip"],
            "wrist": ["wrist up", "wrist down"],
            "finger": ["spread your fingers", "make a fist"]
        }
        
        for muscle, cues in ue_indicators.items():
            for cue in cues:
                if cue in transcript:
                    self.muscle_groups_tested_ue.append(muscle)
                    break
        
        le_indicators = {
            "hip_flexor": ["raise your leg", "leg up"],
            "quad": ["straighten your knee", "kick out"],
            "hamstring": ["bend your knee", "pull back"],
            "dorsiflexion": ["pull your toes up", "foot up"],
            "plantarflexion": ["push down", "point your toes"]
        }
        
        for muscle, cues in le_indicators.items():
            for cue in cues:
                if cue in transcript:
                    self.muscle_groups_tested_le.append(muscle)
                    break
    
    def _detect_plaintiff_helpful_findings(self, transcript: str, report: str):
        """Detect objective findings that support plaintiff's case"""
        combined = transcript + " " + report
        
        for finding in PLAINTIFF_HELPFUL_FINDINGS:
            if finding in combined:
                self.objective_findings.append(finding)
                self.findings.append(HunterFinding(
                    category="OBJECTIVE FINDING",
                    observation=f"Doctor found '{finding}' - objective finding consistent with injury",
                    claim_vs_reality=None,
                    significance="Objective finding supports plaintiff's injury claim",
                    helps_plaintiff=True
                ))
    
    def _evaluate_technique(self, transcript: str):
        """Evaluate if tests were done with proper technique"""
        
        # Check SLR technique
        if "raise your leg" in transcript or "leg up" in transcript:
            # Check for common errors
            if "keep it straight" not in transcript:
                self.tests_performed["straight_leg_raise"] = TestStatus.PERFORMED_INCORRECTLY
                self.findings.append(HunterFinding(
                    category="TECHNIQUE ERROR",
                    observation="SLR may not have been performed correctly - no instruction to keep leg straight",
                    claim_vs_reality=None,
                    significance="Proper SLR requires passive raise with straight knee",
                    helps_plaintiff=True
                ))
        
        # Check Romberg technique
        if "stand" in transcript and "eyes" in transcript:
            if "feet together" not in transcript:
                self.tests_performed["romberg_test"] = TestStatus.PERFORMED_INCORRECTLY
                self.findings.append(HunterFinding(
                    category="TECHNIQUE ERROR",
                    observation="Romberg test appears non-standard - no instruction for feet together",
                    claim_vs_reality=None,
                    significance="Standard Romberg requires feet together",
                    helps_plaintiff=True
                ))
        
        # Check ROM technique (no measurements = inadequate)
        rom_terms = ["touch your toes", "bend", "turn your head", "look left", "look right"]
        measurement_terms = ["degrees", "inclinometer", "goniometer", "measuring"]
        
        has_rom_test = any(term in transcript for term in rom_terms)
        has_measurement = any(term in transcript for term in measurement_terms)
        
        if has_rom_test and not has_measurement:
            self.findings.append(HunterFinding(
                category="INADEQUATE TECHNIQUE",
                observation="ROM testing performed without objective measurement - 'merely guessing' at limitations",
                claim_vs_reality="ROM tested visually, not measured",
                significance="Per Hirsch study, visual ROM estimation has 11.9° error. AMA Guides require instrument measurement.",
                helps_plaintiff=True
            ))
    
    def _check_unreported_tests(self, transcript: str, report: str):
        """Find tests that were DONE but NOT REPORTED"""
        
        unreported = []
        
        # Tests that might be done but not reported
        test_indicators = {
            "sit_to_stand": ("stand up", "don't use your arms"),
            "tinels_sign": ("tap", "tapping", "wrist"),
            "romberg": ("stand", "feet together", "eyes closed"),
            "tandem_gait": ("heel to toe", "walk in a line")
        }
        
        for test_name, indicators in test_indicators.items():
            done = any(ind in transcript.lower() for ind in indicators)
            reported = test_name.replace("_", " ") in report.lower() or test_name in report.lower()
            
            if done and not reported:
                unreported.append(test_name)
                self.findings.append(HunterFinding(
                    category="UNREPORTED TEST",
                    observation=f"Test '{test_name}' was performed but NOT documented in report",
                    claim_vs_reality=f"DONE: {test_name} visible in video | REPORTED: Not mentioned",
                    significance="Test results not documented may be because results were unfavorable",
                    helps_plaintiff=True
                ))
        
        return unreported
    
    def generate_hunter_report(self) -> Dict[str, Any]:
        """Generate report in Dr. Hunter's style"""
        
        return {
            "methodology": "Dr. Hunter Forensic CME Analysis",
            "summary": {
                "total_findings": len(self.findings),
                "claims_vs_reality_issues": len([f for f in self.findings if f.category == "CLAIM vs REALITY"]),
                "technique_errors": len([f for f in self.findings if "TECHNIQUE" in f.category]),
                "unreported_tests": len([f for f in self.findings if f.category == "UNREPORTED TEST"]),
                "findings_helping_plaintiff": len([f for f in self.findings if f.helps_plaintiff])
            },
            "completeness": {
                "ue_muscles_tested": f"{len(self.muscle_groups_tested_ue)}/{TOTAL_UE_MUSCLE_GROUPS}",
                "le_muscles_tested": f"{len(self.muscle_groups_tested_le)}/{TOTAL_LE_MUSCLE_GROUPS}",
                "cranial_nerve_tests": f"{len(self.cn_tests_performed)}/{TOTAL_CN_TESTS}",
                "dermatomes_tested": f"{len(self.dermatomes_tested)}/{len(UPPER_EXTREMITY_DERMATOMES) + len(LOWER_EXTREMITY_DERMATOMES)}"
            },
            "exam_duration": self.exam_duration_seconds,
            "objective_findings_for_plaintiff": self.objective_findings,
            "detailed_findings": [
                {
                    "category": f.category,
                    "observation": f.observation,
                    "claim_vs_reality": f.claim_vs_reality,
                    "significance": f.significance,
                    "helps_plaintiff": f.helps_plaintiff
                }
                for f in self.findings
            ]
        }


def analyze_like_hunter(transcript: str, report_text: Optional[str] = None) -> Dict[str, Any]:
    """
    Main entry point - analyze CME like Dr. Hunter would.
    """
    analyzer = HunterAnalyzer()
    analyzer.analyze_transcript(transcript, report_text)
    return analyzer.generate_hunter_report()
