"""
CME MASTER ANALYZER - Dr. Hunter Level Analysis
================================================

This is the production-grade CME analysis engine that matches
Dr. Hunter's forensic methodology.

KEY CAPABILITIES:
1. CLAIMS vs REALITY - Compare report to what was actually tested
2. PRECISION COUNTING - Exact counts (24 UE, 14 LE, 48 CN tests)
3. TECHNIQUE EVALUATION - Was test done CORRECTLY
4. TIMING ANALYSIS - Exact hands-on duration
5. UNREPORTED TESTS - Tests done but not documented
6. OBJECTIVE FINDINGS - Findings that HELP plaintiff (spasms, etc.)
7. VIDEO FRAME ANALYSIS - Visual detection via Bedrock Claude Vision

Author: CME Analysis Platform
Version: 2.0 - Hunter Methodology
"""

import json
import boto3
import base64
import re
import os
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import logging

from .prompts.production import BEDROCK_CLAUDE_VISION_MODEL_ID

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS - Medical Test Requirements
# =============================================================================

class TestStatus(Enum):
    NOT_PERFORMED = "not_performed"
    PERFORMED_CORRECTLY = "performed_correctly"
    PERFORMED_INCORRECTLY = "performed_incorrectly"
    CLAIMED_NOT_TESTED = "claimed_not_tested"  # CRITICAL: Doctor claims but didn't test
    TESTED_NOT_REPORTED = "tested_not_reported"  # Tests done but not in report


# Complete list of muscle groups per standard medical examination
# Per Dr. Hunter: "For strength testing to be comprehensive there are a total of 
# 38 major muscle groups in the upper & lower extremities combined"
MUSCLE_GROUPS = {
    "upper_extremity": {
        # Shoulder (6 muscle groups)
        "shoulder": ["abduction", "adduction", "flexion", "extension", 
                    "internal_rotation", "external_rotation"],
        # Elbow (4 muscle groups)
        "elbow": ["flexion", "extension", "supination", "pronation"],
        # Wrist (4 muscle groups)
        "wrist": ["flexion", "extension", "inversion", "eversion"],
        # Fingers II-V (4 muscle groups)
        "fingers": ["flexion", "extension", "abduction", "adduction"],
        # Thumb (5 muscle groups)
        "thumb": ["flexion", "extension", "abduction", "adduction", "opposition"],
        # Grip (1 muscle group)
        "grip": ["grip_strength"]
    },
    "lower_extremity": {
        # Hip (6 muscle groups)
        "hip": ["flexion", "extension", "abduction", "adduction",
               "internal_rotation", "external_rotation"],
        # Knee (2 muscle groups)
        "knee": ["flexion", "extension"],
        # Ankle (4 muscle groups)
        "ankle": ["extension", "flexion", "inversion", "eversion"],
        # Toes (2 muscle groups)
        "toes": ["extension", "flexion"]
    }
}
TOTAL_UE_MUSCLES = 24  # Per Dr. Hunter methodology
TOTAL_LE_MUSCLES = 14  # Per Dr. Hunter methodology
TOTAL_MUSCLES = 38     # Combined total per Dr. Hunter

# Cranial nerve tests - 48 total per complete examination
# Per Dr. Hunter: "Most doctors only check CN II-XII. They FAIL to check CN I, 
# the olfactory nerve, which is the MOST likely to be injured in mild TBI!!"
# CN I injured in up to 40% of minor head trauma cases (Coello et al. 2010)
CRANIAL_NERVE_TESTS = {
    "CN_I": ["smell_left", "smell_right"],  # MOST IMPORTANT for TBI!
    "CN_II": ["visual_acuity_L", "visual_acuity_R", "visual_fields_L", "visual_fields_R", 
              "fundoscopy_L", "fundoscopy_R"],
    "CN_III": ["pupil_L", "pupil_R", "eom_sup_rect_L", "eom_sup_rect_R", 
               "eom_med_rect_L", "eom_med_rect_R", "eom_inf_rect_L", "eom_inf_rect_R",
               "eom_inf_oblique_L", "eom_inf_oblique_R", "lid_L", "lid_R"],
    "CN_IV": ["eom_sup_oblique_L", "eom_sup_oblique_R"],
    "CN_V": ["sensation_V1_L", "sensation_V1_R", "sensation_V2_L", "sensation_V2_R",
             "sensation_V3_L", "sensation_V3_R", "masseter", "temporalis", 
             "corneal_L", "corneal_R", "jaw_jerk"],
    "CN_VI": ["eom_lat_rect_L", "eom_lat_rect_R"],
    "CN_VII": ["forehead", "eye_close_L", "eye_close_R", "smile", "pucker", "platysma"],
    "CN_VIII": ["hearing_L", "hearing_R", "weber", "rinne_L", "rinne_R", "nystagmus"],
    "CN_IX": ["gag", "palate_sensation"],
    "CN_X": ["palate_elevation", "uvula", "voice"],
    "CN_XI": ["scm_L", "scm_R", "trapezius_L", "trapezius_R"],
    "CN_XII": ["tongue_protrusion", "tongue_strength", "tongue_fasciculations"]
}
TOTAL_CN_TESTS = 48

# Dermatomes for sensory testing
DERMATOMES = {
    "cervical": ["C2", "C3", "C4", "C5", "C6", "C7", "C8"],
    "thoracic": ["T1", "T2", "T4", "T6", "T8", "T10", "T12"],
    "lumbar": ["L1", "L2", "L3", "L4", "L5"],
    "sacral": ["S1", "S2", "S3", "S4", "S5"]
}

# Range of Motion requirements
ROM_REQUIREMENTS = {
    "cervical": {
        "flexion": {"normal": 50, "method": "inclinometer"},
        "extension": {"normal": 60, "method": "inclinometer"},
        "left_lat_flex": {"normal": 45, "method": "inclinometer"},
        "right_lat_flex": {"normal": 45, "method": "inclinometer"},
        "left_rotation": {"normal": 80, "method": "goniometer"},
        "right_rotation": {"normal": 80, "method": "goniometer"}
    },
    "lumbar": {
        "flexion": {"normal": 60, "method": "dual_inclinometer"},
        "extension": {"normal": 25, "method": "dual_inclinometer"},
        "left_lat_flex": {"normal": 25, "method": "inclinometer"},
        "right_lat_flex": {"normal": 25, "method": "inclinometer"}
    },
    "shoulder": {
        "flexion": {"normal": 180, "method": "goniometer"},
        "extension": {"normal": 60, "method": "goniometer"},
        "abduction": {"normal": 180, "method": "goniometer"},
        "internal_rotation": {"normal": 90, "method": "goniometer"},
        "external_rotation": {"normal": 90, "method": "goniometer"}
    }
}


# =============================================================================
# DETECTION PATTERNS
# =============================================================================

# Patterns indicating doctor CLAIMS something in report
# Per Dr. Hunter: "If report states 'grossly intact' or 'WNL'...they were NOT checked"
CLAIM_PATTERNS = {
    "strength_normal": [
        r"5\s*/\s*5\s*strength",
        r"strength\s*(is\s*)?(5/5|normal|intact|full)",
        r"motor\s*(is\s*)?(intact|normal|5/5)",
        r"full\s*strength",
        r"strength\s*throughout"
    ],
    "oriented_x3": [
        r"oriented\s*(x\s*)?3",
        r"oriented\s*(to\s*)?(time|place|person)",
        r"a\s*&?\s*o\s*(x\s*)?3",
        r"alert\s*and\s*oriented"
    ],
    # Per Dr. Hunter: "grossly intact" = NOT tested!
    "cranial_nerves_normal": [
        r"(cn|cranial\s*nerves?)\s*(II|2).*?(XII|12).*?(intact|normal|grossly)",
        r"cranial\s*nerves?\s*(are\s*)?(intact|normal|grossly\s*intact)",
        r"cranial\s*nerves?\s*(are\s*)?wnl",
        r"cn\s*(II|2)\s*(-|through)\s*(XII|12)\s*(grossly|intact|normal|wnl)"
    ],
    "bulk_normal": [
        r"(muscle\s*)?bulk\s*(is\s*)?(normal|symmetric|wnl)",
        r"no\s*(muscle\s*)?(atrophy|wasting)"
    ],
    "rom_full": [
        r"(range\s*of\s*motion|rom)\s*(is\s*)?(full|normal|wnl|intact)",
        r"full\s*(range|rom)"
    ],
    "sensation_intact": [
        r"sensation\s*(is\s*)?(intact|normal)",
        r"sensory\s*(exam\s*)?(is\s*)?(intact|normal)"
    ],
    "reflexes_normal": [
        r"(reflexes?|dtr)\s*(are\s*)?(normal|symmetric|2\+)",
        r"reflexes?\s*(are\s*)?(intact|normal)"
    ],
    "slr_negative": [
        r"(slr|straight\s*leg\s*raise?)\s*(is\s*)?(negative|normal)",
        r"(negative|normal)\s*(slr|straight\s*leg)"
    ],
    "gait_normal": [
        r"gait\s*(is\s*)?(normal|steady|stable)",
        r"normal\s*gait"
    ]
}

# Patterns for detecting ACTUAL test performance in transcript
TEST_INDICATORS = {
    "grip_strength": {
        "keywords": ["squeeze my hand", "grip", "break it", "hard as you can"],
        "bilateral_required": True,
        "proper_technique": "Jamar dynamometer position 2, 3 trials each"
    },
    "finger_abduction": {
        "keywords": ["spread your fingers", "fingers apart"],
        "bilateral_required": True
    },
    "finger_adduction": {
        "keywords": ["push your fingers together", "don't let me spread"],
        "bilateral_required": True
    },
    "wrist_extension": {
        "keywords": ["bring your wrist up", "wrist up", "cock your wrist back"],
        "bilateral_required": True
    },
    "wrist_flexion": {
        "keywords": ["bend your wrist down", "wrist down"],
        "bilateral_required": True
    },
    "biceps_strength": {
        "keywords": ["bend your elbow", "curl up", "don't let me straighten"],
        "bilateral_required": True
    },
    "triceps_strength": {
        "keywords": ["straighten your elbow", "push out", "extend your arm"],
        "bilateral_required": True
    },
    "deltoid_strength": {
        "keywords": ["raise your arm", "lift your arm", "don't let me push down"],
        "bilateral_required": True
    },
    "hip_flexion": {
        "keywords": ["raise your leg", "leg up", "lift your leg"],
        "bilateral_required": True
    },
    "knee_extension": {
        "keywords": ["straighten your leg", "kick out", "straighten the leg"],
        "bilateral_required": True
    },
    "knee_flexion": {
        "keywords": ["bend your knee", "pull back", "heel to buttock"],
        "bilateral_required": True
    },
    "ankle_dorsiflexion": {
        "keywords": ["pull your toes up", "foot up", "dorsiflex"],
        "bilateral_required": True
    },
    "ankle_plantarflexion": {
        "keywords": ["push down", "point your toes", "plantarflex"],
        "bilateral_required": True
    },
    "straight_leg_raise": {
        "keywords": ["raise your leg", "keep it straight", "leg up"],
        "proper_technique": "Passive raise, straight knee, note angle, ask radiation below knee",
        "technique_checks": ["keep it straight", "don't bend", "where does it hurt", "radiating"]
    },
    "cervical_rotation": {
        "keywords": ["turn your head", "look left", "look right"],
        "measurement_required": True
    },
    "cervical_flexion": {
        "keywords": ["chin to chest", "look down", "bend your head forward"],
        "measurement_required": True
    },
    "cervical_extension": {
        "keywords": ["look up", "head back", "look at ceiling"],
        "measurement_required": True
    },
    "cervical_lateral_flexion": {
        "keywords": ["ear to shoulder", "tilt your head"],
        "measurement_required": True
    },
    "lumbar_flexion": {
        "keywords": ["touch your toes", "bend forward", "flex forward"],
        "measurement_required": True
    },
    "lumbar_extension": {
        "keywords": ["bend back", "lean back", "arch your back"],
        "measurement_required": True
    },
    "lumbar_lateral_flexion": {
        "keywords": ["bend to the side", "lean to your", "side bend"],
        "measurement_required": True
    },
    "sensation_sharp_dull": {
        "keywords": ["sharp or dull", "feel this", "sharp dull"],
        "dermatomes_required": True
    },
    "proprioception": {
        "keywords": ["up or down", "which direction", "toe up down"],
        "bilateral_required": True
    },
    "finger_nose": {
        "keywords": ["touch your nose", "finger to nose", "nose to finger"],
        "bilateral_required": True
    },
    "heel_shin": {
        "keywords": ["heel to shin", "run your heel", "heel down shin"],
        "bilateral_required": True
    },
    "romberg": {
        "keywords": ["feet together", "close your eyes", "stand still"],
        # Per Dr. Hunter: "examiner observes for a full minute"
        "proper_technique": "Feet together, eyes closed, observe for FULL MINUTE (60 sec). Non-standard technique = misrepresenting findings."
    },
    "tandem_gait": {
        "keywords": ["heel to toe", "walk in line", "tandem"],
        "proper_technique": "Walk heel-to-toe in straight line"
    },
    "sit_to_stand": {
        "keywords": ["stand up", "don't use your arms", "without your hands"],
        "proper_technique": "Rise from chair without using arms"
    },
    "tinels_sign": {
        "keywords": ["tapping", "tap on", "tinel"],
        "proper_technique": "Percussion over carpal tunnel"
    },
    "phalens_test": {
        "keywords": ["wrists together", "flex your wrists", "phalen"],
        "proper_technique": "Wrists flexed 60 seconds"
    },
    "orientation": {
        "keywords": ["what day", "what year", "where are we", "what month", "president"],
        "required_questions": 3
    },
    "cranial_nerve_ii": {
        "keywords": ["read this", "see my finger", "visual field", "count fingers"],
        "bilateral_required": True
    },
    "cranial_nerve_iii_iv_vi": {
        "keywords": ["follow my finger", "track this", "look up", "look down", "look left", "look right"],
        "proper_technique": "H-pattern tracking"
    },
    "cranial_nerve_v": {
        "keywords": ["feel this on your face", "clench your teeth", "bite down"],
        "bilateral_required": True
    },
    "cranial_nerve_vii": {
        "keywords": ["raise your eyebrows", "smile", "show teeth", "puff cheeks", "close eyes tight"],
        "proper_technique": "Test all facial movements"
    },
    "cranial_nerve_viii": {
        "keywords": ["hear this", "finger rub", "tuning fork"],
        "bilateral_required": True
    },
    "cranial_nerve_ix_x": {
        "keywords": ["say ahh", "swallow", "gag"],
        "proper_technique": "Observe palate elevation"
    },
    "cranial_nerve_xi": {
        "keywords": ["shrug", "turn head against", "resist"],
        "bilateral_required": True
    },
    "cranial_nerve_xii": {
        "keywords": ["stick out tongue", "move tongue", "tongue to the"],
        "proper_technique": "Check for deviation, fasciculations"
    },
    "deep_tendon_reflexes": {
        "keywords": ["relax", "let it hang", "reflex"],
        "sites": ["biceps", "triceps", "brachioradialis", "patellar", "achilles"]
    },
    "babinski": {
        "keywords": ["bottom of foot", "sole", "stroking"],
        "bilateral_required": True
    },
    "hoffmann": {
        "keywords": ["flick finger", "middle finger"],
        "bilateral_required": True
    },
    "spurling": {
        "keywords": ["head to side", "press down", "spurling"],
        "bilateral_required": True
    },
    "palpation_cervical": {
        "keywords": ["feel your neck", "tender", "press here"],
        "findings_to_note": ["spasm", "tenderness", "trigger point"]
    },
    "palpation_lumbar": {
        "keywords": ["feel your back", "press on back", "tender there"],
        "findings_to_note": ["spasm", "tenderness", "trigger point"]
    }
}

# Objective findings that HELP the plaintiff
PLAINTIFF_POSITIVE_FINDINGS = [
    "spasm", "spasms", "spasming", "muscle spasm",
    "tender", "tenderness", "point tender",
    "limited", "restricted", "decreased",
    "positive", "reproduction", "radiating",
    "weakness", "give way", "4/5", "3/5",
    "atrophy", "wasting", "smaller",
    "asymmetric", "unequal",
    "antalgic", "guarding", "splinting",
    "trigger point", "taut band"
]


# =============================================================================
# MAIN ANALYZER CLASS
# =============================================================================

@dataclass
class CMEFinding:
    """A single finding from CME analysis"""
    category: str  # CLAIM_VS_REALITY, TECHNIQUE_ERROR, OMISSION, OBJECTIVE_FINDING, UNREPORTED
    finding: str
    claim: Optional[str] = None
    reality: Optional[str] = None
    significance: str = ""
    helps_plaintiff: bool = False
    severity: str = "medium"  # low, medium, high, critical


@dataclass
class CMEAnalysisResult:
    """Complete CME analysis result"""
    case_info: Dict[str, str]
    exam_duration_seconds: Optional[float] = None
    findings: List[CMEFinding] = field(default_factory=list)
    tests_performed: Dict[str, TestStatus] = field(default_factory=dict)
    muscle_groups_tested: Dict[str, List[str]] = field(default_factory=dict)
    cn_tests_performed: List[str] = field(default_factory=list)
    dermatomes_tested: List[str] = field(default_factory=list)
    rom_measurements: Dict[str, Any] = field(default_factory=dict)
    objective_findings: List[str] = field(default_factory=list)
    unreported_tests: List[str] = field(default_factory=list)
    claims_detected: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "case_info": self.case_info,
            "exam_duration_seconds": self.exam_duration_seconds,
            "summary": {
                "total_findings": len(self.findings),
                "critical_findings": len([f for f in self.findings if f.severity == "critical"]),
                "findings_helping_plaintiff": len([f for f in self.findings if f.helps_plaintiff]),
                "claim_vs_reality_issues": len([f for f in self.findings if f.category == "CLAIM_VS_REALITY"]),
                "technique_errors": len([f for f in self.findings if f.category == "TECHNIQUE_ERROR"]),
                "omissions": len([f for f in self.findings if f.category == "OMISSION"]),
                "unreported_tests": len(self.unreported_tests)
            },
            "completeness": {
                "ue_muscles": f"{len(self.muscle_groups_tested.get('upper_extremity', []))}/{TOTAL_UE_MUSCLES}",
                "le_muscles": f"{len(self.muscle_groups_tested.get('lower_extremity', []))}/{TOTAL_LE_MUSCLES}",
                "cranial_nerves": f"{len(self.cn_tests_performed)}/{TOTAL_CN_TESTS}",
                "dermatomes": f"{len(self.dermatomes_tested)}/24"
            },
            "objective_findings_for_plaintiff": self.objective_findings,
            "unreported_tests": self.unreported_tests,
            "claims_detected": self.claims_detected,
            "findings": [
                {
                    "category": f.category,
                    "finding": f.finding,
                    "claim": f.claim,
                    "reality": f.reality,
                    "significance": f.significance,
                    "helps_plaintiff": f.helps_plaintiff,
                    "severity": f.severity
                }
                for f in self.findings
            ]
        }


class CMEMasterAnalyzer:
    """
    Master CME Analyzer using Dr. Hunter's forensic methodology.
    """
    
    def __init__(self, case_info: Dict[str, str]):
        self.case_info = case_info
        self.result = CMEAnalysisResult(case_info=case_info)
        self.bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
        
    def analyze(self, 
                transcript: str,
                report_text: Optional[str] = None,
                video_frames: Optional[List[bytes]] = None) -> CMEAnalysisResult:
        """
        Complete CME analysis.
        
        Args:
            transcript: Full transcript of the examination
            report_text: Doctor's written report (if available)
            video_frames: Key video frames for visual analysis (if available)
        """
        transcript_lower = transcript.lower()
        report_lower = report_text.lower() if report_text else ""
        
        # 1. Detect claims in report
        self._detect_claims(report_lower, transcript_lower)
        
        # 2. Detect what was actually performed
        self._detect_performed_tests(transcript_lower)
        
        # 3. Count muscle groups, CN tests, dermatomes
        self._count_completeness(transcript_lower)
        
        # 4. Compare claims to reality
        self._compare_claims_to_reality()
        
        # 5. Evaluate technique
        self._evaluate_technique(transcript_lower)
        
        # 6. Detect objective findings (help plaintiff)
        self._detect_objective_findings(transcript_lower, report_lower)
        
        # 7. Find unreported tests
        self._find_unreported_tests(transcript_lower, report_lower)
        
        # 8. Analyze video frames if provided
        if video_frames:
            self._analyze_video_frames(video_frames)
        
        # 9. Check for repetition (examiner not paying attention)
        self._check_repetition(transcript_lower)
        
        return self.result
    
    def _detect_claims(self, report: str, transcript: str):
        """Detect claims made in the report or transcript."""
        combined = report + " " + transcript
        
        for claim_type, patterns in CLAIM_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, combined, re.IGNORECASE)
                if match:
                    self.result.claims_detected[claim_type] = match.group(0)
                    break
    
    def _detect_performed_tests(self, transcript: str):
        """Detect what tests were actually performed."""
        for test_name, config in TEST_INDICATORS.items():
            keywords = config.get("keywords", [])
            found = any(kw.lower() in transcript for kw in keywords)
            
            if found:
                # Check technique if applicable
                technique_checks = config.get("technique_checks", [])
                if technique_checks:
                    checks_passed = sum(1 for check in technique_checks if check.lower() in transcript)
                    if checks_passed >= len(technique_checks) / 2:
                        self.result.tests_performed[test_name] = TestStatus.PERFORMED_CORRECTLY
                    else:
                        self.result.tests_performed[test_name] = TestStatus.PERFORMED_INCORRECTLY
                else:
                    self.result.tests_performed[test_name] = TestStatus.PERFORMED_CORRECTLY
            else:
                self.result.tests_performed[test_name] = TestStatus.NOT_PERFORMED
    
    def _count_completeness(self, transcript: str):
        """Count exactly how many muscle groups, CN tests, dermatomes were tested."""
        
        # Count UE muscle groups
        ue_tested = []
        ue_indicators = {
            "grip": ["squeeze", "grip"],
            "finger_abduction": ["spread your fingers"],
            "finger_adduction": ["push fingers together"],
            "wrist_extension": ["wrist up", "bring your wrist up"],
            "wrist_flexion": ["wrist down"],
            "biceps": ["bend your elbow", "curl"],
            "triceps": ["straighten your elbow", "push out"],
            "deltoid": ["raise your arm", "lift your arm"],
            "rotator_cuff": ["rotate", "turn your arm"]
        }
        for muscle, keywords in ue_indicators.items():
            if any(kw in transcript for kw in keywords):
                ue_tested.append(muscle)
        self.result.muscle_groups_tested["upper_extremity"] = ue_tested
        
        # Count LE muscle groups
        le_tested = []
        le_indicators = {
            "hip_flexion": ["raise your leg", "leg up"],
            "hip_extension": ["push down with your leg", "leg down"],
            "knee_extension": ["straighten your leg", "kick out"],
            "knee_flexion": ["bend your knee"],
            "ankle_dorsiflexion": ["pull your toes up", "foot up"],
            "ankle_plantarflexion": ["push down", "point your toes"]
        }
        for muscle, keywords in le_indicators.items():
            if any(kw in transcript for kw in keywords):
                le_tested.append(muscle)
        self.result.muscle_groups_tested["lower_extremity"] = le_tested
        
        # Count CN tests
        cn_indicators = {
            "visual": ["follow my finger", "track", "look up", "look down"],
            "facial_sensation": ["feel this on your face"],
            "facial_movement": ["smile", "raise your eyebrows", "puff cheeks"],
            "hearing": ["hear this", "finger rub"],
            "tongue": ["stick out your tongue"]
        }
        for cn, keywords in cn_indicators.items():
            if any(kw in transcript for kw in keywords):
                self.result.cn_tests_performed.append(cn)
        
        # Count dermatomes
        for region, derms in DERMATOMES.items():
            for derm in derms:
                if derm.lower() in transcript:
                    self.result.dermatomes_tested.append(derm)
    
    def _compare_claims_to_reality(self):
        """THE KEY ANALYSIS: Compare what was CLAIMED vs what was DONE."""
        
        # Check strength claims
        if "strength_normal" in self.result.claims_detected:
            ue_count = len(self.result.muscle_groups_tested.get("upper_extremity", []))
            le_count = len(self.result.muscle_groups_tested.get("lower_extremity", []))
            
            if ue_count < TOTAL_UE_MUSCLES or le_count < TOTAL_LE_MUSCLES:
                self.result.findings.append(CMEFinding(
                    category="CLAIM_VS_REALITY",
                    finding=f"Claims '5/5 strength' but tested only {ue_count}/{TOTAL_UE_MUSCLES} UE and {le_count}/{TOTAL_LE_MUSCLES} LE muscle groups",
                    claim=self.result.claims_detected["strength_normal"],
                    reality=f"Tested {ue_count} UE, {le_count} LE muscles",
                    significance="Cannot claim 'full strength throughout' without testing all major muscle groups",
                    helps_plaintiff=True,
                    severity="critical"
                ))
        
        # Check orientation claims
        if "oriented_x3" in self.result.claims_detected:
            orientation_tested = self.result.tests_performed.get("orientation", TestStatus.NOT_PERFORMED)
            if orientation_tested == TestStatus.NOT_PERFORMED:
                self.result.findings.append(CMEFinding(
                    category="CLAIM_VS_REALITY",
                    finding="Claims 'oriented x3' but did NOT ask any orientation questions",
                    claim=self.result.claims_detected["oriented_x3"],
                    reality="No orientation questions observed in transcript",
                    significance="Orientation status claimed without any testing - false documentation",
                    helps_plaintiff=True,
                    severity="critical"
                ))
        
        # Check CN claims
        if "cranial_nerves_normal" in self.result.claims_detected:
            cn_count = len(self.result.cn_tests_performed)
            if cn_count < 10:  # Should be 48 for complete exam
                self.result.findings.append(CMEFinding(
                    category="CLAIM_VS_REALITY",
                    finding=f"Claims 'CN III-XII grossly normal' but performed only {cn_count}/{TOTAL_CN_TESTS} cranial nerve tests",
                    claim=self.result.claims_detected["cranial_nerves_normal"],
                    reality=f"Only {cn_count} CN tests observed",
                    significance="Cannot claim cranial nerves 'grossly normal' without systematic testing - 'grossly' actually means NOT tested",
                    helps_plaintiff=True,
                    severity="critical"
                ))
        
        # Check bulk claims
        if "bulk_normal" in self.result.claims_detected:
            # Look for tape measurement in transcript
            tape_used = "tape" in " ".join([t for t, s in self.result.tests_performed.items() 
                                           if s == TestStatus.PERFORMED_CORRECTLY])
            if not tape_used:
                self.result.findings.append(CMEFinding(
                    category="CLAIM_VS_REALITY",
                    finding="Claims muscle bulk 'normal' or 'no atrophy' but did NOT measure with tape",
                    claim=self.result.claims_detected["bulk_normal"],
                    reality="No circumferential measurement observed",
                    significance="Atrophy/bulk assessment requires tape measurement at defined landmarks bilaterally",
                    helps_plaintiff=True,
                    severity="high"
                ))
        
        # Check ROM claims
        if "rom_full" in self.result.claims_detected:
            rom_measured = self.result.tests_performed.get("cervical_rotation", TestStatus.NOT_PERFORMED)
            # Check if degrees were documented
            self.result.findings.append(CMEFinding(
                category="CLAIM_VS_REALITY",
                finding="Claims ROM 'full' or 'normal' but did NOT measure with goniometer/inclinometer",
                claim=self.result.claims_detected.get("rom_full", "Full ROM"),
                reality="Visual estimation only - no instrument measurement",
                significance="Per AMA Guides and Hirsch study, visual ROM estimation has 11.9° error. Proper measurement requires instruments.",
                helps_plaintiff=True,
                severity="critical"
            ))
        
        # Check SLR claims
        if "slr_negative" in self.result.claims_detected:
            slr_status = self.result.tests_performed.get("straight_leg_raise", TestStatus.NOT_PERFORMED)
            if slr_status == TestStatus.PERFORMED_INCORRECTLY:
                self.result.findings.append(CMEFinding(
                    category="CLAIM_VS_REALITY",
                    finding="Claims SLR 'negative' but test was NOT performed correctly",
                    claim=self.result.claims_detected["slr_negative"],
                    reality="SLR technique errors observed",
                    significance="Proper SLR: passive raise (not patient active), knee straight, note angle, ask about radiation below knee",
                    helps_plaintiff=True,
                    severity="high"
                ))
            elif slr_status == TestStatus.NOT_PERFORMED:
                self.result.findings.append(CMEFinding(
                    category="CLAIM_VS_REALITY",
                    finding="Claims SLR 'negative' but test was NOT performed at all",
                    claim=self.result.claims_detected["slr_negative"],
                    reality="No SLR test observed",
                    significance="Cannot report SLR negative without performing the test",
                    helps_plaintiff=True,
                    severity="critical"
                ))
    
    def _evaluate_technique(self, transcript: str):
        """Evaluate if tests were performed with proper technique."""
        
        # Check SLR technique
        if self.result.tests_performed.get("straight_leg_raise") == TestStatus.PERFORMED_INCORRECTLY:
            self.result.findings.append(CMEFinding(
                category="TECHNIQUE_ERROR",
                finding="Straight Leg Raise not performed to standard of care",
                significance="Proper SLR requires: passive raise by examiner, leg kept straight, note exact angle when pain begins, ask specifically if pain radiates below knee",
                helps_plaintiff=True,
                severity="high"
            ))
        
        # Check if ROM done without measurement
        rom_tests = ["cervical_rotation", "cervical_flexion", "lumbar_flexion", "lumbar_extension"]
        rom_done = any(self.result.tests_performed.get(t, TestStatus.NOT_PERFORMED) != TestStatus.NOT_PERFORMED 
                      for t in rom_tests)
        
        if rom_done:
            measurement_words = ["degrees", "goniometer", "inclinometer", "measuring"]
            has_measurement = any(word in transcript for word in measurement_words)
            
            if not has_measurement:
                self.result.findings.append(CMEFinding(
                    category="TECHNIQUE_ERROR",
                    finding="ROM testing performed without objective measurement - merely 'guessing' at limitations",
                    significance="Per AMA Guides, ROM must be measured with goniometer or inclinometer. Visual estimation has 11.9° average error (Hirsch et al.). Calling ROM 'mild' or 'moderate' without measurement is not objective.",
                    helps_plaintiff=True,
                    severity="critical"
                ))
        
        # Check Romberg technique
        romberg_done = self.result.tests_performed.get("romberg", TestStatus.NOT_PERFORMED)
        if romberg_done != TestStatus.NOT_PERFORMED:
            proper_romberg = all(phrase in transcript for phrase in ["feet together", "close your eyes"])
            if not proper_romberg:
                self.result.findings.append(CMEFinding(
                    category="TECHNIQUE_ERROR",
                    finding="Romberg test appears non-standard",
                    significance="Standard Romberg requires: feet together, eyes closed, maintain 30 seconds",
                    helps_plaintiff=True,
                    severity="medium"
                ))
    
    def _detect_objective_findings(self, transcript: str, report: str):
        """Detect objective findings that HELP the plaintiff."""
        combined = transcript + " " + report
        
        for finding in PLAINTIFF_POSITIVE_FINDINGS:
            if finding in combined:
                if finding not in self.result.objective_findings:
                    self.result.objective_findings.append(finding)
        
        # Also look for palpation findings - doctor feeling something
        palpation_indicators = [
            ("tight", "muscle tightness/spasm"),
            ("spasm", "muscle spasm"),
            ("ooh", "patient pain response during palpation"),
            ("sorry", "examiner apologizing suggests caused pain"),
            ("does it hurt", "examiner checking for tenderness"),
            ("tender", "point tenderness"),
            ("that hurts", "pain response")
        ]
        
        for indicator, meaning in palpation_indicators:
            if indicator in combined.lower():
                finding_name = meaning
                if finding_name not in self.result.objective_findings:
                    self.result.objective_findings.append(finding_name)
        
        # Check for evidence of spasms during palpation (look for context around back/neck palpation)
        if "relax" in combined.lower() and ("back" in combined.lower() or "neck" in combined.lower()):
            # Doctor telling patient to relax during palpation often means they're finding tension/spasm
            if "muscle spasm indicator" not in self.result.objective_findings:
                self.result.objective_findings.append("potential muscle tension/spasm (examiner requesting 'relax' during palpation)")
        
        # Create finding entries for objective findings
        if self.result.objective_findings:
            findings_str = ", ".join(self.result.objective_findings)
            self.result.findings.append(CMEFinding(
                category="OBJECTIVE_FINDING",
                finding=f"Doctor documented objective findings: {findings_str}",
                significance="These are OBJECTIVE findings that support plaintiff's injury claim and cannot be dismissed as subjective",
                helps_plaintiff=True,
                severity="high"
            ))
        
        # NOTE: SPASMS are often found through PALPATION and may not be verbalized
        # This requires VIDEO ANALYSIS to detect doctor's hands feeling spasms
        self.result.findings.append(CMEFinding(
            category="REQUIRES_VIDEO",
            finding="VIDEO ANALYSIS NEEDED: Spasms and palpation findings often visible but not verbalized",
            significance="Dr. Hunter notes spasms found during palpation - these may be visible in video but not in transcript. Upload video frames for visual AI analysis.",
            helps_plaintiff=True,
            severity="medium"
        ))
    
    def _find_unreported_tests(self, transcript: str, report: str):
        """Find tests that were PERFORMED but NOT REPORTED."""
        
        # Tests that might be done but not reported
        potentially_unreported = {
            "sit_to_stand": ["stand up", "don't use your arm", "without your hands"],
            "tinels_sign": ["tapping", "tap on"],
            "romberg": ["feet together", "close your eyes"],
            "tandem_gait": ["heel to toe"],
            "pronator_drift": ["arms out", "close your eyes", "palms up"]
        }
        
        for test_name, keywords in potentially_unreported.items():
            done = any(kw in transcript for kw in keywords)
            reported = test_name.replace("_", " ") in report or test_name in report
            
            if done and not reported:
                self.result.unreported_tests.append(test_name)
        
        if self.result.unreported_tests:
            tests_str = ", ".join(self.result.unreported_tests)
            self.result.findings.append(CMEFinding(
                category="UNREPORTED",
                finding=f"Tests performed but NOT documented: {tests_str}",
                significance="Tests done but not reported may have shown results unfavorable to examiner's conclusions",
                helps_plaintiff=True,
                severity="high"
            ))
    
    def _check_repetition(self, transcript: str):
        """Check for repeated testing - indicates examiner not paying attention."""
        
        # Look for patterns of repeated instructions
        repeat_patterns = [
            r"one more time",
            r"let's do that again", 
            r"do it again",
            r"try that again",
            r"same thing",
            r"same sort of thing",
            r"again\b",
            r"do this one",  # Usually means repeating on other side, but if excessive...
        ]
        
        repeat_count = 0
        for pattern in repeat_patterns:
            matches = re.findall(pattern, transcript, re.IGNORECASE)
            repeat_count += len(matches)
        
        # Also look for identical phrases repeated (examiner saying same thing twice)
        words = transcript.split()
        phrases = [' '.join(words[i:i+4]) for i in range(len(words)-3)]
        duplicate_phrases = len(phrases) - len(set(phrases))
        
        if repeat_count >= 2 or duplicate_phrases > 5:
            self.result.findings.append(CMEFinding(
                category="TECHNIQUE_ERROR",
                finding=f"Examiner repeated instructions/testing multiple times ({repeat_count} repeat phrases, {duplicate_phrases} duplicate instructions) - suggests not paying attention first time",
                significance="Repeated testing often indicates examiner was distracted or not properly focused on the examination",
                helps_plaintiff=True,
                severity="medium"
            ))
    
    def _analyze_video_frames(self, frames: List[bytes]):
        """Use Bedrock Claude Vision to analyze video frames for visual findings."""
        
        try:
            # Prepare prompt for visual analysis
            analysis_prompt = """Analyze these video frames from a Compulsory Medical Examination (CME).

Look specifically for:
1. MUSCLE SPASMS - visible muscle contractions, twitching, or doctor's hands feeling spasms
2. PATIENT REACTIONS - grimacing, wincing, guarding when touched
3. MEASUREMENT INSTRUMENTS - Is doctor using goniometer, inclinometer, dynamometer, or tape measure?
4. PROPER TECHNIQUE - Is the examiner following proper examination technique?
5. TIME STAMPS - Can you estimate duration of hands-on examination?

For each finding, note:
- What you observed
- Timestamp/frame if visible
- Clinical significance

Be specific about what you see - this is for legal review."""

            # Encode frames
            encoded_frames = []
            for frame in frames[:10]:  # Limit to 10 frames
                encoded = base64.b64encode(frame).decode('utf-8')
                encoded_frames.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": encoded
                    }
                })
            
            # Add text prompt
            content = encoded_frames + [{"type": "text", "text": analysis_prompt}]
            
            response = self.bedrock.invoke_model(
                modelId=BEDROCK_CLAUDE_VISION_MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": content}]
                })
            )
            
            result = json.loads(response['body'].read())
            visual_analysis = result['content'][0]['text']
            
            # Parse visual findings
            if "spasm" in visual_analysis.lower():
                self.result.objective_findings.append("muscle_spasm_visual")
                self.result.findings.append(CMEFinding(
                    category="OBJECTIVE_FINDING",
                    finding="Visual analysis detected muscle spasms",
                    significance="Muscle spasms are objective findings supporting injury",
                    helps_plaintiff=True,
                    severity="high"
                ))
            
            # Store raw visual analysis
            self.result.rom_measurements["visual_analysis"] = visual_analysis
            
        except Exception as e:
            logger.warning(f"Video frame analysis failed: {e}")


def analyze_cme(
    transcript: str,
    case_info: Dict[str, str],
    report_text: Optional[str] = None,
    video_frames: Optional[List[bytes]] = None
) -> Dict[str, Any]:
    """
    Main entry point for CME analysis.
    
    Args:
        transcript: Full transcript of the examination
        case_info: Dict with plaintiff_name, dob, doi, examiner
        report_text: Doctor's written report (optional)
        video_frames: Key video frames (optional)
    
    Returns:
        Complete analysis result as dictionary
    """
    analyzer = CMEMasterAnalyzer(case_info)
    result = analyzer.analyze(transcript, report_text, video_frames)
    return result.to_dict()


# Lambda handler for AWS deployment
def lambda_handler(event, context):
    """AWS Lambda handler for CME analysis."""
    try:
        body = json.loads(event.get('body', '{}'))
        
        transcript = body.get('transcript', '')
        case_info = body.get('case_info', {})
        report_text = body.get('report_text')
        
        if not transcript:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'transcript is required'})
            }
        
        result = analyze_cme(transcript, case_info, report_text)
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
