"""
CME VIDEO ANALYZER - Comprehensive Visual Analysis Engine
=========================================================

Analyzes CME examination videos frame-by-frame to detect:
1. Patient attire (gown vs regular clothes)
2. Tests performed and technique
3. Testing through clothing violations
4. Equipment usage (reflex hammer, goniometer, etc.)
5. Exam timing and completeness
6. Comparison against report claims

Works with any CME video - generalized for all cases.
"""

import subprocess
import base64
import json
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from enum import Enum
import tempfile


class TestType(Enum):
    STRENGTH = "strength"
    SENSORY = "sensory"
    REFLEX = "reflex"
    ROM = "rom"
    GAIT = "gait"
    COORDINATION = "coordination"
    CRANIAL_NERVE = "cranial_nerve"
    PALPATION = "palpation"
    ROMBERG = "romberg"
    INSPECTION = "inspection"
    UNKNOWN = "unknown"


class TechniqueIssue(Enum):
    THROUGH_CLOTHING = "testing_through_clothing"
    NO_GONIOMETER = "no_goniometer_for_rom"
    NO_TAPE_MEASURE = "no_tape_for_bulk"
    IMPROPER_ROMBERG = "improper_romberg_technique"
    NO_REFLEX_HAMMER = "no_reflex_hammer_visible"
    PATIENT_NOT_IN_GOWN = "patient_not_in_gown"
    INCOMPLETE_DERMATOME = "incomplete_dermatome_coverage"
    NO_BABINSKI = "babinski_not_tested"


@dataclass
class FrameAnalysis:
    """Analysis of a single video frame."""
    frame_number: int
    timestamp_sec: float
    video_file: str
    test_type: Optional[TestType] = None
    body_region: str = ""
    patient_attire: str = ""  # "gown", "regular_clothes", "partial"
    technique_issues: List[TechniqueIssue] = field(default_factory=list)
    equipment_visible: List[str] = field(default_factory=list)
    notes: str = ""
    raw_analysis: str = ""


@dataclass
class VideoAnalysisResult:
    """Complete analysis of CME video(s)."""
    total_frames_analyzed: int = 0
    total_exam_duration_sec: float = 0
    hands_on_exam_duration_sec: float = 0
    
    # Patient attire
    patient_wore_gown: bool = False
    attire_description: str = ""
    
    # Tests observed
    tests_observed: Dict[str, List[dict]] = field(default_factory=dict)
    
    # Technique issues
    technique_issues: List[dict] = field(default_factory=list)
    
    # Equipment
    equipment_observed: List[str] = field(default_factory=list)
    equipment_missing: List[str] = field(default_factory=list)
    
    # Frame analyses
    frame_analyses: List[dict] = field(default_factory=list)
    
    # Claim comparisons
    claim_vs_reality: List[dict] = field(default_factory=list)


class CMEVideoAnalyzer:
    """
    Comprehensive CME video analyzer using vision AI.
    """
    
    # Standard tests that should be performed in a neurological CME
    EXPECTED_TESTS = {
        "strength": {
            "upper_extremity": ["shoulder", "elbow", "wrist", "grip", "finger_abduction"],
            "lower_extremity": ["hip", "knee", "ankle", "toe"]
        },
        "sensory": {
            "modalities": ["sharp_dull", "light_touch", "proprioception", "vibration"],
            "dermatomes_ue": ["C4", "C5", "C6", "C7", "C8", "T1"],
            "dermatomes_le": ["L2", "L3", "L4", "L5", "S1"]
        },
        "reflexes": {
            "upper": ["biceps", "triceps", "brachioradialis"],
            "lower": ["patellar", "achilles"],
            "pathological": ["babinski", "hoffman"]
        },
        "coordination": ["finger_to_nose", "heel_to_shin", "rapid_alternating"],
        "gait": ["normal", "tandem", "heel_walk", "toe_walk"],
        "romberg": ["feet_together", "eyes_closed", "60_seconds"],
        "cranial_nerves": ["CN_I", "CN_II", "CN_III", "CN_IV", "CN_V", "CN_VI", 
                          "CN_VII", "CN_VIII", "CN_IX", "CN_X", "CN_XI", "CN_XII"]
    }
    
    # Visual indicators for each test type
    TEST_VISUAL_INDICATORS = {
        TestType.STRENGTH: [
            "patient pushing against doctor",
            "patient pulling against resistance",
            "grip testing",
            "arm raised against resistance",
            "leg raised against resistance",
            "finger spread",
            "wrist extension"
        ],
        TestType.SENSORY: [
            "pin or sharp object",
            "cotton or soft object",
            "tuning fork",
            "doctor touching skin",
            "patient eyes closed during touch"
        ],
        TestType.REFLEX: [
            "reflex hammer",
            "hammer striking tendon",
            "arm positioned for reflex",
            "leg positioned for reflex"
        ],
        TestType.ROM: [
            "neck rotation",
            "neck flexion/extension",
            "shoulder movement",
            "goniometer visible",
            "inclinometer visible"
        ],
        TestType.GAIT: [
            "patient walking",
            "heel to toe walking",
            "patient standing",
            "walking in line"
        ],
        TestType.COORDINATION: [
            "finger to nose",
            "touching nose then finger",
            "rapid hand movements",
            "heel sliding on shin"
        ],
        TestType.ROMBERG: [
            "feet together standing",
            "eyes closed standing",
            "arms at sides or outstretched"
        ],
        TestType.PALPATION: [
            "doctor pressing on spine",
            "doctor feeling muscles",
            "palpating neck/back"
        ]
    }
    
    def __init__(self, use_local_vision: bool = True):
        """
        Initialize the video analyzer.
        
        Args:
            use_local_vision: If True, returns frames for external analysis.
                            If False, uses cloud vision API.
        """
        self.use_local_vision = use_local_vision
        self.result = VideoAnalysisResult()
        self.frames_dir = None
        
    def extract_frames(self, video_paths: List[str], output_dir: str = None,
                       fps: float = 0.2) -> List[Path]:
        """
        Extract frames from video files.
        
        Args:
            video_paths: List of video file paths
            output_dir: Directory to save frames (default: temp dir)
            fps: Frames per second to extract (0.2 = 1 frame every 5 seconds)
            
        Returns:
            List of frame file paths
        """
        if output_dir:
            self.frames_dir = Path(output_dir)
            self.frames_dir.mkdir(exist_ok=True)
        else:
            self.frames_dir = Path(tempfile.mkdtemp(prefix="cme_frames_"))
            
        all_frames = []
        
        for i, video_path in enumerate(video_paths):
            video_name = f"video{i+1}"
            
            # Get video duration
            result = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', video_path
            ], capture_output=True, text=True)
            
            try:
                duration = float(result.stdout.strip())
            except:
                duration = 0
                
            self.result.total_exam_duration_sec += duration
            
            # Extract frames
            output_pattern = str(self.frames_dir / f'{video_name}_frame_%04d.jpg')
            subprocess.run([
                'ffmpeg', '-i', video_path, '-vf', f'fps={fps}', '-q:v', '2',
                output_pattern, '-y'
            ], capture_output=True)
            
            # Collect frame paths
            frames = sorted(self.frames_dir.glob(f'{video_name}_frame_*.jpg'))
            all_frames.extend(frames)
            
        return all_frames
    
    def analyze_frame_content(self, frame_path: Path, frame_num: int, 
                             timestamp_sec: float) -> FrameAnalysis:
        """
        Analyze a single frame's content.
        
        This method should be called with vision AI results.
        For now, returns a template for manual/external analysis.
        """
        analysis = FrameAnalysis(
            frame_number=frame_num,
            timestamp_sec=timestamp_sec,
            video_file=frame_path.name
        )
        return analysis
    
    def process_vision_analysis(self, frame_path: str, vision_result: str) -> FrameAnalysis:
        """
        Process vision AI analysis result for a frame.
        
        Args:
            frame_path: Path to the frame
            vision_result: Text analysis from vision AI
            
        Returns:
            Structured FrameAnalysis
        """
        path = Path(frame_path)
        
        # Extract frame number and video from filename
        parts = path.stem.split('_')
        video_num = int(parts[0].replace('video', ''))
        frame_num = int(parts[-1])
        timestamp_sec = frame_num * 5  # Assuming 1 frame per 5 seconds
        
        analysis = FrameAnalysis(
            frame_number=frame_num,
            timestamp_sec=timestamp_sec,
            video_file=path.name,
            raw_analysis=vision_result
        )
        
        # Parse vision result for key indicators
        result_lower = vision_result.lower()
        
        # Detect patient attire
        if any(word in result_lower for word in ['gown', 'hospital gown', 'medical gown']):
            analysis.patient_attire = "gown"
        elif any(word in result_lower for word in ['shirt', 'pants', 'jeans', 'leggings', 
                                                    'regular clothes', 'street clothes',
                                                    'pink', 'blue shirt', 'long sleeve']):
            analysis.patient_attire = "regular_clothes"
            analysis.technique_issues.append(TechniqueIssue.PATIENT_NOT_IN_GOWN)
            
        # Detect test type
        if any(word in result_lower for word in ['strength', 'push', 'pull', 'resist', 
                                                  'grip', 'squeeze', 'as hard as']):
            analysis.test_type = TestType.STRENGTH
        elif any(word in result_lower for word in ['sharp', 'dull', 'pin', 'sensation',
                                                    'feel this', 'touch']):
            analysis.test_type = TestType.SENSORY
        elif any(word in result_lower for word in ['reflex', 'hammer', 'tap']):
            analysis.test_type = TestType.REFLEX
        elif any(word in result_lower for word in ['turn head', 'rotation', 'range of motion',
                                                    'look up', 'look down', 'bend']):
            analysis.test_type = TestType.ROM
        elif any(word in result_lower for word in ['walk', 'gait', 'heel to toe', 'tandem']):
            analysis.test_type = TestType.GAIT
        elif any(word in result_lower for word in ['finger to nose', 'touch nose', 
                                                    'coordination', 'rapid']):
            analysis.test_type = TestType.COORDINATION
        elif any(word in result_lower for word in ['romberg', 'feet together', 
                                                    'eyes closed', 'balance']):
            analysis.test_type = TestType.ROMBERG
        elif any(word in result_lower for word in ['palpat', 'press', 'feel', 'spasm']):
            analysis.test_type = TestType.PALPATION
            
        # Detect technique issues
        if any(phrase in result_lower for phrase in ['through clothing', 'through shirt',
                                                      'through pants', 'over clothes',
                                                      'not on skin', 'through fabric']):
            analysis.technique_issues.append(TechniqueIssue.THROUGH_CLOTHING)
            
        if analysis.test_type == TestType.ROM:
            if not any(word in result_lower for word in ['goniometer', 'inclinometer', 
                                                          'measuring device', 'degrees']):
                analysis.technique_issues.append(TechniqueIssue.NO_GONIOMETER)
                
        if analysis.test_type == TestType.ROMBERG:
            if 'arms outstretched' in result_lower or 'arms out' in result_lower:
                if 'feet together' not in result_lower:
                    analysis.technique_issues.append(TechniqueIssue.IMPROPER_ROMBERG)
                    
        # Detect equipment
        equipment_keywords = {
            'reflex hammer': 'reflex_hammer',
            'hammer': 'reflex_hammer',
            'goniometer': 'goniometer',
            'inclinometer': 'inclinometer',
            'tape measure': 'tape_measure',
            'pin': 'sensory_pin',
            'safety pin': 'sensory_pin',
            'tuning fork': 'tuning_fork',
            'cotton': 'cotton_swab'
        }
        
        for keyword, equipment in equipment_keywords.items():
            if keyword in result_lower:
                analysis.equipment_visible.append(equipment)
                
        # Detect body region
        body_regions = ['neck', 'shoulder', 'arm', 'elbow', 'wrist', 'hand', 'finger',
                       'back', 'spine', 'hip', 'thigh', 'knee', 'leg', 'ankle', 'foot']
        for region in body_regions:
            if region in result_lower:
                analysis.body_region = region
                break
                
        return analysis
    
    def compile_results(self, frame_analyses: List[FrameAnalysis],
                       report_claims: Dict[str, str] = None) -> VideoAnalysisResult:
        """
        Compile all frame analyses into a comprehensive result.
        
        Args:
            frame_analyses: List of analyzed frames
            report_claims: Dictionary of claims from the doctor's report
            
        Returns:
            Complete VideoAnalysisResult
        """
        self.result.total_frames_analyzed = len(frame_analyses)
        self.result.frame_analyses = [asdict(f) for f in frame_analyses]
        
        # Determine patient attire
        attire_counts = {"gown": 0, "regular_clothes": 0}
        for fa in frame_analyses:
            if fa.patient_attire in attire_counts:
                attire_counts[fa.patient_attire] += 1
                
        if attire_counts["regular_clothes"] > attire_counts["gown"]:
            self.result.patient_wore_gown = False
            self.result.attire_description = "Patient wore regular clothes (not examination gown)"
        else:
            self.result.patient_wore_gown = True
            self.result.attire_description = "Patient wore examination gown"
            
        # Compile tests observed
        for fa in frame_analyses:
            if fa.test_type:
                test_name = fa.test_type.value
                if test_name not in self.result.tests_observed:
                    self.result.tests_observed[test_name] = []
                self.result.tests_observed[test_name].append({
                    "timestamp": fa.timestamp_sec,
                    "body_region": fa.body_region,
                    "frame": fa.frame_number
                })
                
        # Compile technique issues
        issue_set = set()
        for fa in frame_analyses:
            for issue in fa.technique_issues:
                if issue.value not in issue_set:
                    issue_set.add(issue.value)
                    self.result.technique_issues.append({
                        "issue": issue.value,
                        "first_observed_at": fa.timestamp_sec,
                        "frame": fa.frame_number
                    })
                    
        # Compile equipment
        equipment_set = set()
        for fa in frame_analyses:
            for eq in fa.equipment_visible:
                equipment_set.add(eq)
        self.result.equipment_observed = list(equipment_set)
        
        # Determine missing equipment
        expected_equipment = ['reflex_hammer', 'goniometer', 'sensory_pin', 'tape_measure']
        self.result.equipment_missing = [
            eq for eq in expected_equipment 
            if eq not in self.result.equipment_observed
        ]
        
        # Calculate hands-on exam time (frames where testing is occurring)
        exam_frames = sum(1 for fa in frame_analyses if fa.test_type is not None)
        self.result.hands_on_exam_duration_sec = exam_frames * 5  # 5 sec per frame
        
        # Compare against report claims if provided
        if report_claims:
            self._compare_claims(report_claims)
            
        return self.result
    
    def _compare_claims(self, report_claims: Dict[str, str]):
        """Compare video observations against report claims."""
        
        # Check orientation claim
        if 'orientation' in report_claims:
            # Orientation cannot be verified by video alone
            self.result.claim_vs_reality.append({
                "claim": report_claims['orientation'],
                "observation": "Cannot verify from video - requires audio analysis",
                "issue": "UNVERIFIABLE"
            })
            
        # Check cranial nerve claim
        if 'cranial_nerves' in report_claims:
            cn_tests = self.result.tests_observed.get('cranial_nerve', [])
            if len(cn_tests) == 0:
                self.result.claim_vs_reality.append({
                    "claim": report_claims['cranial_nerves'],
                    "observation": "NO cranial nerve testing observed in video",
                    "issue": "CLAIM_NOT_SUPPORTED"
                })
                
        # Check strength claim
        if 'strength' in report_claims:
            strength_tests = self.result.tests_observed.get('strength', [])
            regions_tested = set(t['body_region'] for t in strength_tests if t['body_region'])
            if len(strength_tests) < 10:  # Expecting many strength tests for "5/5 throughout"
                self.result.claim_vs_reality.append({
                    "claim": report_claims['strength'],
                    "observation": f"Only {len(strength_tests)} strength tests observed, regions: {regions_tested}",
                    "issue": "INCOMPLETE_TESTING"
                })
                
        # Check reflex claim
        if 'reflexes' in report_claims:
            if 'reflex_hammer' not in self.result.equipment_observed:
                self.result.claim_vs_reality.append({
                    "claim": report_claims['reflexes'],
                    "observation": "No reflex hammer visible in video",
                    "issue": "EQUIPMENT_NOT_OBSERVED"
                })
                
        # Check ROM claim
        if 'rom' in report_claims:
            if 'goniometer' not in self.result.equipment_observed:
                self.result.claim_vs_reality.append({
                    "claim": report_claims['rom'],
                    "observation": "No goniometer/inclinometer visible - ROM not objectively measured",
                    "issue": "NO_OBJECTIVE_MEASUREMENT"
                })
                
        # Check Romberg claim
        if 'romberg' in report_claims:
            romberg_issues = [i for i in self.result.technique_issues 
                            if i['issue'] == 'improper_romberg_technique']
            if romberg_issues:
                self.result.claim_vs_reality.append({
                    "claim": report_claims['romberg'],
                    "observation": "Romberg test performed with non-standard technique",
                    "issue": "IMPROPER_TECHNIQUE"
                })
                
        # Check gown/attire
        if not self.result.patient_wore_gown:
            clothing_issues = [i for i in self.result.technique_issues
                             if i['issue'] == 'testing_through_clothing']
            if clothing_issues:
                self.result.claim_vs_reality.append({
                    "claim": "Sensory exam performed",
                    "observation": "Patient not in gown - sensory testing through clothing is not standard of care",
                    "issue": "TESTING_THROUGH_CLOTHING"
                })
    
    def generate_report(self) -> str:
        """Generate a human-readable analysis report."""
        
        lines = [
            "=" * 70,
            "CME VIDEO ANALYSIS REPORT",
            "=" * 70,
            "",
            f"Total Video Duration: {self.result.total_exam_duration_sec:.0f} seconds "
            f"({self.result.total_exam_duration_sec/60:.1f} minutes)",
            f"Estimated Hands-On Exam Time: {self.result.hands_on_exam_duration_sec:.0f} seconds "
            f"({self.result.hands_on_exam_duration_sec/60:.1f} minutes)",
            f"Frames Analyzed: {self.result.total_frames_analyzed}",
            "",
            "=" * 70,
            "PATIENT ATTIRE",
            "=" * 70,
            f"Wore Examination Gown: {'YES' if self.result.patient_wore_gown else 'NO'}",
            f"Description: {self.result.attire_description}",
            ""
        ]
        
        if not self.result.patient_wore_gown:
            lines.append("⚠️  ISSUE: Patient not in medical examination gown")
            lines.append("   This may affect quality of sensory examination")
            lines.append("")
            
        lines.extend([
            "=" * 70,
            "TESTS OBSERVED",
            "=" * 70
        ])
        
        for test_type, occurrences in self.result.tests_observed.items():
            regions = set(o['body_region'] for o in occurrences if o['body_region'])
            lines.append(f"  {test_type.upper()}: {len(occurrences)} instances")
            if regions:
                lines.append(f"    Regions: {', '.join(regions)}")
        lines.append("")
        
        lines.extend([
            "=" * 70,
            "EQUIPMENT OBSERVED",
            "=" * 70,
            f"  Visible: {', '.join(self.result.equipment_observed) or 'None detected'}",
            f"  Missing: {', '.join(self.result.equipment_missing) or 'None'}"
        ])
        lines.append("")
        
        if self.result.technique_issues:
            lines.extend([
                "=" * 70,
                "TECHNIQUE ISSUES DETECTED",
                "=" * 70
            ])
            for issue in self.result.technique_issues:
                lines.append(f"  🔴 {issue['issue'].replace('_', ' ').upper()}")
                lines.append(f"     First observed at: {issue['first_observed_at']:.0f} seconds")
            lines.append("")
            
        if self.result.claim_vs_reality:
            lines.extend([
                "=" * 70,
                "CLAIM VS REALITY",
                "=" * 70
            ])
            for cvr in self.result.claim_vs_reality:
                lines.append(f"  CLAIM: {cvr['claim']}")
                lines.append(f"  OBSERVED: {cvr['observation']}")
                lines.append(f"  ISSUE: {cvr['issue']}")
                lines.append("")
                
        return "\n".join(lines)


# Convenience function for quick analysis
def analyze_cme_videos(video_paths: List[str], 
                       report_claims: Dict[str, str] = None,
                       frames_dir: str = None) -> Tuple[VideoAnalysisResult, List[Path]]:
    """
    Quick function to analyze CME videos.
    
    Args:
        video_paths: List of video file paths
        report_claims: Optional dictionary of claims from doctor's report
        frames_dir: Optional directory to save frames
        
    Returns:
        Tuple of (VideoAnalysisResult, list of frame paths for manual analysis)
    """
    analyzer = CMEVideoAnalyzer()
    frames = analyzer.extract_frames(video_paths, frames_dir)
    
    # Return frames for external vision analysis
    return analyzer, frames


# Frame analysis prompt for vision AI
FRAME_ANALYSIS_PROMPT = """Analyze this frame from a Compulsory Medical Examination (CME) video.

Report the following in a structured way:

1. PATIENT ATTIRE:
   - Is patient wearing a medical examination gown OR regular clothes?
   - If regular clothes, describe (shirt color, pants, etc.)

2. EXAMINATION BEING PERFORMED:
   - What specific test is being done? (strength, sensory, reflex, ROM, gait, coordination, palpation, Romberg, etc.)
   - What body region is being examined?

3. TECHNIQUE OBSERVATIONS:
   - Is testing being done on BARE SKIN or THROUGH CLOTHING?
   - For ROM: Is a goniometer or inclinometer visible?
   - For reflexes: Is a reflex hammer visible?
   - For Romberg: Are feet together? Arms at sides or outstretched? Eyes open or closed?

4. EQUIPMENT VISIBLE:
   - Reflex hammer?
   - Goniometer/inclinometer?
   - Pin or sharp object?
   - Tape measure?
   - Tuning fork?

5. BODY PARTS VISIBLE:
   - What body parts are being examined?

Be specific and factual. Only report what you can clearly observe."""
