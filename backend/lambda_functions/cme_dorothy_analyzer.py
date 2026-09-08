"""
CME DOROTHY ANALYZER - Full Requirements Implementation
=======================================================

Based on Dorothy Clay Sims requirements (Feb 4 & Feb 11, 2026):

CORE ANALYSIS:
1. Claim vs Reality (MOST IMPORTANT) - what report claims vs what happened
2. Doctor Behavior - rude, not observing, interruptions
3. Patient Observations - crying, confusion, distress
4. Exam Timing - length of physical exam
5. Cranial Nerves - which were/weren't assessed
6. Mental Status - MOCA vs Folstein, actual vs reported score
7. Range of Motion - actual measurements, was goniometer used
8. Body Part Breakdown - analysis by body region
9. Dr. Hunter References - how it should have been done
10. Top 10-20 Egregious Behaviors - at beginning of report

OUTPUT:
- Saves project by patient name
- Includes redlined report for verification
- Breaks down by body part
- Includes references for lawyer
- Verifies entire video was watched (no missing segments)
"""

import json
import subprocess
import tempfile
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib

from .vision_client import VisionClient, make_vision_client, resolve_provider


class CranialNerve(Enum):
    CN_I = "Olfactory (smell)"
    CN_II = "Optic (vision)"
    CN_III = "Oculomotor (eye movement)"
    CN_IV = "Trochlear (eye movement)"
    CN_V = "Trigeminal (facial sensation)"
    CN_VI = "Abducens (eye movement)"
    CN_VII = "Facial (facial movement)"
    CN_VIII = "Vestibulocochlear (hearing/balance)"
    CN_IX = "Glossopharyngeal (throat)"
    CN_X = "Vagus (throat/voice)"
    CN_XI = "Accessory (shoulder/neck)"
    CN_XII = "Hypoglossal (tongue)"


class MentalStatusTest(Enum):
    MOCA = "Montreal Cognitive Assessment"
    FOLSTEIN = "Folstein Mini-Mental State Examination (MMSE)"
    UNKNOWN = "Unknown/Other"


@dataclass
class CranialNerveAssessment:
    """Assessment of a single cranial nerve."""
    nerve: str
    tested: bool = False
    technique_proper: bool = False
    timestamp_sec: Optional[float] = None
    notes: str = ""
    reference: str = ""  # Dr. Hunter reference


@dataclass
class MentalStatusAssessment:
    """Mental status test assessment."""
    test_type: str = "unknown"  # moca, folstein, unknown
    test_identified: bool = False
    questions_observed: List[str] = field(default_factory=list)
    actual_score_observed: Optional[int] = None
    reported_score: Optional[int] = None
    score_discrepancy: bool = False
    notes: str = ""


@dataclass
class ROMAssessment:
    """Range of motion assessment for a joint."""
    joint: str
    tested: bool = False
    goniometer_used: bool = False
    observed_rom: Optional[str] = None  # e.g., "45 degrees flexion"
    reported_rom: Optional[str] = None
    limited: bool = False
    discrepancy: bool = False
    timestamp_sec: Optional[float] = None


@dataclass
class BodyPartAnalysis:
    """Analysis broken down by body part."""
    body_part: str
    tests_performed: List[str] = field(default_factory=list)
    tests_claimed_but_not_seen: List[str] = field(default_factory=list)
    technique_issues: List[str] = field(default_factory=list)
    findings_discrepancies: List[str] = field(default_factory=list)
    time_spent_sec: float = 0
    notes: str = ""


@dataclass
class PatientObservation:
    """Patient emotional/confusion observation."""
    timestamp_sec: float
    observation_type: str  # "crying", "confusion", "distress", "pain"
    description: str
    doctor_response: str  # how doctor responded (or didn't)
    frame_id: str = ""


@dataclass
class Interruption:
    """Record of an interruption during exam."""
    timestamp_sec: float
    description: str
    who_interrupted: str  # "phone", "staff", "other"
    duration_sec: Optional[float] = None
    doctor_response: str = ""


@dataclass
class EgregiousBehavior:
    """A significant egregious behavior for top 10-20 list."""
    rank: int
    category: str
    description: str
    timestamp_sec: float
    evidence: str
    severity: str  # "critical", "high", "medium"
    reference: str = ""  # Dr. Hunter reference for proper technique


@dataclass
class ClaimVsReality:
    """Comparison of report claim to video evidence."""
    category: str
    report_claim: str
    video_observation: str
    discrepancy_type: str  # "not_performed", "incomplete", "misrepresented", "technique_error"
    severity: str
    timestamp_sec: Optional[float] = None
    body_part: str = ""
    reference: str = ""  # Dr. Hunter reference


@dataclass
class DorothyAnalysisResult:
    """Complete analysis result per Dorothy's requirements."""
    # Project identification
    project_id: str = ""
    patient_name: str = ""
    examiner_name: str = ""
    exam_date: str = ""
    analysis_date: str = ""
    
    # Video coverage verification
    total_video_duration_sec: float = 0
    frames_analyzed: int = 0
    video_coverage_percent: float = 0  # Should be ~100%
    segments_analyzed: List[Dict] = field(default_factory=list)
    
    # 1. TOP EGREGIOUS BEHAVIORS (First in report per Dorothy)
    top_egregious_behaviors: List[Dict] = field(default_factory=list)
    
    # 2. CLAIM VS REALITY (Most Important per Dorothy)
    claim_vs_reality: List[Dict] = field(default_factory=list)
    transcript_misrepresentations: List[Dict] = field(default_factory=list)
    
    # 3. DOCTOR BEHAVIOR
    was_doctor_rude: bool = False
    rudeness_instances: List[Dict] = field(default_factory=list)
    not_observing_patient: List[Dict] = field(default_factory=list)  # times doctor didn't watch patient
    interruptions: List[Dict] = field(default_factory=list)  # with timestamps
    interruption_count: int = 0
    
    # 4. PATIENT OBSERVATIONS
    patient_crying_instances: List[Dict] = field(default_factory=list)
    patient_confusion_instances: List[Dict] = field(default_factory=list)
    patient_distress_instances: List[Dict] = field(default_factory=list)
    
    # 5. TIMING
    exam_duration_actual_sec: float = 0
    exam_duration_claimed_min: float = 30
    
    # 6. CRANIAL NERVES
    cranial_nerve_assessment: Dict[str, Dict] = field(default_factory=dict)
    cranial_nerves_not_tested: List[str] = field(default_factory=list)
    cranial_nerves_improperly_tested: List[str] = field(default_factory=list)
    
    # 7. MENTAL STATUS
    mental_status: Dict = field(default_factory=dict)
    
    # 8. RANGE OF MOTION
    rom_assessments: List[Dict] = field(default_factory=list)
    
    # 9. BODY PART BREAKDOWN
    body_part_analysis: Dict[str, Dict] = field(default_factory=dict)
    
    # 10. DR. HUNTER REFERENCES
    references_cited: List[Dict] = field(default_factory=list)
    
    # Summary scores
    overall_exam_quality: float = 0
    professionalism_score: float = 0
    
    # Cost tracking
    total_cost_usd: float = 0


# Comprehensive frame analysis prompt for Dorothy's requirements
DOROTHY_FRAME_PROMPT = """Analyze this frame from a Compulsory Medical Examination (CME) video.

This is a DEFENSE medical examination. Identify everything that could help the plaintiff's case.

Return EXACT JSON:
{
    "timestamp_context": "beginning/middle/end of exam based on what you see",
    
    "patient_state": {
        "crying": true/false,
        "appears_confused": true/false,
        "in_visible_pain": true/false,
        "distressed": true/false,
        "trying_to_speak": true/false
    },
    
    "doctor_behavior": {
        "looking_at_patient": true/false,
        "observing_patient_during_test": true/false,
        "appears_rushed": true/false,
        "dismissive_gesture": true/false,
        "on_phone": true/false,
        "distracted": true/false,
        "rude_body_language": true/false
    },
    
    "interruption": {
        "occurring": true/false,
        "type": "phone/staff/other/none",
        "description": ""
    },
    
    "test_being_performed": {
        "type": "cranial_nerve/strength/sensory/reflex/rom/gait/coordination/romberg/mental_status/palpation/none",
        "specific_test": "name of specific test",
        "body_part": "neck/shoulder/arm/hand/back/hip/leg/foot/head/full_body",
        
        "cranial_nerve_if_applicable": {
            "nerve_number": 1-12 or null,
            "nerve_name": "e.g., CN VII Facial",
            "technique_proper": true/false,
            "technique_issue": "description if improper"
        },
        
        "mental_status_if_applicable": {
            "test_type": "moca/folstein/unknown",
            "question_being_asked": "description",
            "visible_score_elements": "any visible scoring"
        },
        
        "rom_if_applicable": {
            "joint": "which joint",
            "goniometer_visible": true/false,
            "estimated_rom": "e.g., 45 degrees",
            "appears_limited": true/false
        }
    },
    
    "technique_issues": ["list of problems observed"],
    
    "equipment_visible": ["reflex_hammer", "goniometer", "tuning_fork", "ophthalmoscope", "otoscope", etc.],
    
    "patient_attire": "gown/regular_clothes/partial",
    
    "egregious_behavior": {
        "present": true/false,
        "description": "description of egregious behavior if present",
        "category": "rudeness/inattention/rushing/improper_technique/ignoring_distress/none"
    },
    
    "notes": "any other observations"
}

CRANIAL NERVE TESTING TO IDENTIFY:
- CN I (Olfactory): Testing smell
- CN II (Optic): Vision test, fundoscopy
- CN III, IV, VI (Eye movement): Following finger, pupil reaction
- CN V (Trigeminal): Facial sensation, jaw
- CN VII (Facial): Smile, facial expressions
- CN VIII (Vestibulocochlear): Hearing, finger rub
- CN IX, X (Glossopharyngeal, Vagus): Say "ah", gag reflex
- CN XI (Accessory): Shoulder shrug, head turn against resistance
- CN XII (Hypoglossal): Stick out tongue

MENTAL STATUS TO IDENTIFY:
- MOCA: Draw clock, name animals, serial 7s, repeat words
- Folstein MMSE: Orientation questions, recall, "world" backwards

Return ONLY the JSON."""


# Reference knowledge base (Dr. Hunter methodology)
DR_HUNTER_REFERENCES = {
    "cranial_nerves": {
        "standard": "All 12 cranial nerves should be individually tested and documented",
        "cn_i": "Olfactory nerve tested with aromatic substance (coffee, vanilla) each nostril separately",
        "cn_ii": "Optic nerve: visual acuity, visual fields, fundoscopic exam",
        "cn_iii_iv_vi": "Oculomotor/Trochlear/Abducens: extraocular movements in H pattern, pupillary response",
        "cn_v": "Trigeminal: sensation all 3 divisions (forehead, cheek, jaw), corneal reflex, jaw strength",
        "cn_vii": "Facial: raise eyebrows, close eyes tight, smile, puff cheeks",
        "cn_viii": "Vestibulocochlear: whisper test or finger rub each ear, Rinne/Weber if indicated",
        "cn_ix_x": "Glossopharyngeal/Vagus: palate elevation, gag reflex, voice quality",
        "cn_xi": "Accessory: shoulder shrug against resistance, turn head against resistance",
        "cn_xii": "Hypoglossal: tongue protrusion, movement side to side",
        "reference": "Dr. Hunter CME Training Videos; Standard Neurological Examination Protocol"
    },
    "mental_status": {
        "moca": "Montreal Cognitive Assessment - 30 points, tests: visuospatial, naming, memory, attention, language, abstraction, recall, orientation",
        "folstein": "MMSE - 30 points, tests: orientation (10), registration (3), attention (5), recall (3), language (9)",
        "standard": "Mental status exam should document: level of consciousness, orientation (person, place, time, situation), attention, memory (immediate, short-term, long-term), language, mood/affect",
        "reference": "Folstein MF et al. J Psychiatr Res 1975; Nasreddine ZS et al. JAGS 2005"
    },
    "rom": {
        "standard": "Range of motion should be measured with goniometer for objective documentation",
        "cervical": "Flexion 45°, Extension 45°, Lateral flexion 45° each side, Rotation 60° each side",
        "shoulder": "Flexion 180°, Extension 60°, Abduction 180°, Internal rotation 70°, External rotation 90°",
        "lumbar": "Flexion 90°, Extension 30°, Lateral flexion 25° each side",
        "reference": "AMA Guides to Evaluation of Permanent Impairment; Dr. Hunter ROM Assessment Protocol"
    },
    "sensory": {
        "standard": "Sensory exam must be performed on skin, not through clothing",
        "modalities": "Light touch, pinprick, temperature, vibration, proprioception",
        "dermatomes": "Should test key dermatomes: C5-T1 upper extremity, L2-S1 lower extremity",
        "reference": "Dr. Hunter Sensory Examination Protocol"
    },
    "romberg": {
        "standard": "Feet together, arms at sides, eyes closed for minimum 60 seconds",
        "technique": "Patient should not be holding onto anything, eyes must be closed full duration",
        "reference": "Dr. Hunter Balance Assessment Protocol"
    },
    "reflexes": {
        "standard": "DTRs graded 0-4+, should test: biceps (C5-6), triceps (C7-8), brachioradialis (C5-6), patellar (L3-4), Achilles (S1-2)",
        "technique": "Patient relaxed, consistent technique, compare sides",
        "reference": "Standard DTR Grading Scale; Dr. Hunter Reflex Assessment"
    }
}


class CMEDorothyAnalyzer:
    """
    Complete CME analyzer implementing all of Dorothy's requirements.
    """
    
    COST_PER_FRAME = 0.005
    COST_PER_TRANSCRIPT_SEGMENT = 0.01
    
    ALL_CRANIAL_NERVES = [
        "CN I Olfactory", "CN II Optic", "CN III Oculomotor", "CN IV Trochlear",
        "CN V Trigeminal", "CN VI Abducens", "CN VII Facial", "CN VIII Vestibulocochlear",
        "CN IX Glossopharyngeal", "CN X Vagus", "CN XI Accessory", "CN XII Hypoglossal"
    ]
    
    BODY_PARTS = [
        "head/face", "neck/cervical", "shoulder", "upper_arm", "elbow", "forearm",
        "wrist", "hand", "thoracic", "lumbar", "hip", "thigh", "knee", "lower_leg",
        "ankle", "foot", "neurological"
    ]
    
    def __init__(self, api_key: str = None, vision_client: Optional[VisionClient] = None):
        provider = resolve_provider()
        self.api_key = api_key
        if vision_client is None:
            self.vision_client: VisionClient = make_vision_client(
                provider, api_key=self.api_key
            )
        else:
            self.vision_client = vision_client
        self.result = DorothyAnalysisResult()
        self.result.analysis_date = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Initialize cranial nerve tracking
        for cn in self.ALL_CRANIAL_NERVES:
            self.result.cranial_nerve_assessment[cn] = {
                "tested": False,
                "technique_proper": False,
                "timestamp_sec": None,
                "notes": ""
            }
        
        # Initialize body part tracking
        for bp in self.BODY_PARTS:
            self.result.body_part_analysis[bp] = {
                "tests_performed": [],
                "tests_claimed_not_seen": [],
                "technique_issues": [],
                "findings_discrepancies": [],
                "time_spent_sec": 0
            }
    
    def generate_project_id(self, patient_name: str) -> str:
        """Generate unique project ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        name_hash = hashlib.md5(patient_name.encode()).hexdigest()[:8]
        return f"{patient_name.replace(' ', '_')}_{timestamp}_{name_hash}"
    
    def extract_frames(self, video_paths: List[str], output_dir: str,
                      interval_sec: float = 3.0) -> Tuple[List[Path], float]:
        """Extract frames and track video coverage."""
        frames_dir = Path(output_dir) / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        
        all_frames = []
        total_duration = 0
        fps = 1 / interval_sec
        
        for i, video_path in enumerate(video_paths):
            print(f"Processing video {i+1}: {video_path}")
            
            # Get exact duration
            result = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', video_path
            ], capture_output=True, text=True)
            
            try:
                duration = float(result.stdout.strip())
                total_duration += duration
                print(f"  Duration: {duration:.1f}s ({duration/60:.1f} min)")
                
                self.result.segments_analyzed.append({
                    "video": video_path,
                    "duration_sec": duration,
                    "start_offset": total_duration - duration
                })
            except:
                print(f"  Warning: Could not get duration")
            
            # Extract frames
            output_pattern = str(frames_dir / f'video{i+1}_frame_%04d.jpg')
            subprocess.run([
                'ffmpeg', '-i', video_path, '-vf', f'fps={fps}', '-q:v', '2',
                output_pattern, '-y', '-loglevel', 'error'
            ])
            
            frames = sorted(frames_dir.glob(f'video{i+1}_frame_*.jpg'))
            print(f"  Extracted {len(frames)} frames")
            all_frames.extend(frames)
        
        self.result.total_video_duration_sec = total_duration
        expected_frames = total_duration / interval_sec
        self.result.video_coverage_percent = (len(all_frames) / expected_frames * 100) if expected_frames > 0 else 0
        
        print(f"\nVideo Coverage: {self.result.video_coverage_percent:.1f}%")
        if self.result.video_coverage_percent < 95:
            print("  ⚠️ WARNING: May have missed video segments!")
        
        return all_frames, total_duration
    
    def analyze_frame(self, frame_path: Path, timestamp_sec: float) -> Dict:
        """Analyze a single frame for all Dorothy requirements."""

        with open(frame_path, 'rb') as f:
            image_bytes = f.read()

        try:
            result = self.vision_client.analyze(
                image_bytes,
                DOROTHY_FRAME_PROMPT,
                max_tokens=2000,
                mime_type="image/jpeg",
            )
            raw = getattr(result, "text", "") or getattr(result, "raw_text", "") or ""
            self.result.total_cost_usd += self.COST_PER_FRAME
            
            # Parse JSON
            try:
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0]
                elif "```" in raw:
                    raw = raw.split("```")[1].split("```")[0]
                data = json.loads(raw.strip())
            except:
                data = {}
            
            data['timestamp_sec'] = timestamp_sec
            data['frame_id'] = frame_path.stem
            
            return data
            
        except Exception as e:
            print(f"Error analyzing frame {frame_path.name}: {e}")
            return {'timestamp_sec': timestamp_sec, 'frame_id': frame_path.stem}
    
    def analyze_transcript_for_misrepresentations(self, transcript: str, report_claims: Dict) -> List[Dict]:
        """Compare transcript to report claims for misrepresentations."""
        
        prompt = f"""Compare this CME examination transcript to the doctor's report claims.

TRANSCRIPT:
{transcript[:10000]}

REPORT CLAIMS:
{json.dumps(report_claims, indent=2)}

Identify any MISREPRESENTATIONS where what the report says differs from what was actually said.

Return JSON:
{{
    "misrepresentations": [
        {{
            "category": "category of misrepresentation",
            "report_says": "what the report claims",
            "transcript_shows": "what was actually said",
            "exact_quote": "exact quote from transcript",
            "severity": "critical/high/medium"
        }}
    ],
    "quotes_in_report_not_in_transcript": ["list of quotes attributed to patient but not in transcript"],
    "important_statements_omitted": ["patient statements that were omitted from report"]
}}
"""
        
        try:
            result = self.vision_client.text_analyze(prompt, max_tokens=2500)
            raw = getattr(result, "text", "") or getattr(result, "raw_text", "") or ""
            self.result.total_cost_usd += self.COST_PER_TRANSCRIPT_SEGMENT
            
            try:
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0]
                elif "```" in raw:
                    raw = raw.split("```")[1].split("```")[0]
                return json.loads(raw.strip())
            except:
                return {}
                
        except Exception as e:
            print(f"Error analyzing transcript: {e}")
            return {}
    
    def compile_results(self, frame_analyses: List[Dict], 
                       report_claims: Dict = None,
                       transcript: str = None):
        """Compile all frame analyses into Dorothy's required format."""
        
        self.result.frames_analyzed = len(frame_analyses)
        
        egregious_behaviors = []
        
        for analysis in frame_analyses:
            ts = analysis.get('timestamp_sec', 0)
            
            # Patient observations
            patient = analysis.get('patient_state', {})
            
            if patient.get('crying'):
                self.result.patient_crying_instances.append({
                    'timestamp_sec': ts,
                    'frame_id': analysis.get('frame_id'),
                    'description': 'Patient crying observed'
                })
            
            if patient.get('appears_confused'):
                self.result.patient_confusion_instances.append({
                    'timestamp_sec': ts,
                    'frame_id': analysis.get('frame_id'),
                    'description': 'Patient appeared confused'
                })
            
            if patient.get('distressed') or patient.get('in_visible_pain'):
                self.result.patient_distress_instances.append({
                    'timestamp_sec': ts,
                    'frame_id': analysis.get('frame_id'),
                    'description': 'Patient in distress/pain',
                    'doctor_response': 'ignored' if not analysis.get('doctor_behavior', {}).get('looking_at_patient') else 'acknowledged'
                })
            
            # Doctor behavior
            doctor = analysis.get('doctor_behavior', {})
            
            if not doctor.get('observing_patient_during_test', True):
                self.result.not_observing_patient.append({
                    'timestamp_sec': ts,
                    'description': 'Doctor not watching patient during test'
                })
            
            if doctor.get('rude_body_language'):
                self.result.rudeness_instances.append({
                    'timestamp_sec': ts,
                    'description': 'Rude body language observed'
                })
                self.result.was_doctor_rude = True
            
            # Interruptions
            interrupt = analysis.get('interruption', {})
            if interrupt.get('occurring'):
                self.result.interruptions.append({
                    'timestamp_sec': ts,
                    'type': interrupt.get('type', 'unknown'),
                    'description': interrupt.get('description', '')
                })
                self.result.interruption_count += 1
            
            # Cranial nerves
            test_info = analysis.get('test_being_performed', {})
            cn_info = test_info.get('cranial_nerve_if_applicable', {})
            
            if cn_info and cn_info.get('nerve_name'):
                nerve_name = cn_info.get('nerve_name', '')
                for cn in self.ALL_CRANIAL_NERVES:
                    if nerve_name in cn or cn in nerve_name:
                        self.result.cranial_nerve_assessment[cn]['tested'] = True
                        self.result.cranial_nerve_assessment[cn]['timestamp_sec'] = ts
                        self.result.cranial_nerve_assessment[cn]['technique_proper'] = cn_info.get('technique_proper', False)
                        if cn_info.get('technique_issue'):
                            self.result.cranial_nerve_assessment[cn]['notes'] = cn_info.get('technique_issue')
            
            # Mental status
            ms_info = test_info.get('mental_status_if_applicable', {})
            if ms_info and ms_info.get('test_type') != 'unknown':
                if not self.result.mental_status:
                    self.result.mental_status = {
                        'test_type': ms_info.get('test_type', 'unknown'),
                        'questions_observed': [],
                        'timestamps': []
                    }
                if ms_info.get('question_being_asked'):
                    self.result.mental_status['questions_observed'].append(ms_info.get('question_being_asked'))
                    self.result.mental_status['timestamps'].append(ts)
            
            # ROM
            rom_info = test_info.get('rom_if_applicable', {})
            if rom_info and rom_info.get('joint'):
                self.result.rom_assessments.append({
                    'joint': rom_info.get('joint'),
                    'goniometer_used': rom_info.get('goniometer_visible', False),
                    'observed_rom': rom_info.get('estimated_rom'),
                    'appears_limited': rom_info.get('appears_limited', False),
                    'timestamp_sec': ts
                })
            
            # Body part tracking
            body_part = test_info.get('body_part', '')
            if body_part:
                for bp in self.BODY_PARTS:
                    if body_part in bp or bp in body_part:
                        test_type = test_info.get('type', '')
                        specific = test_info.get('specific_test', '')
                        if specific:
                            self.result.body_part_analysis[bp]['tests_performed'].append(f"{test_type}: {specific}")
                        for issue in analysis.get('technique_issues', []):
                            self.result.body_part_analysis[bp]['technique_issues'].append(issue)
            
            # Egregious behaviors
            egregious = analysis.get('egregious_behavior', {})
            if egregious.get('present'):
                egregious_behaviors.append({
                    'timestamp_sec': ts,
                    'category': egregious.get('category', ''),
                    'description': egregious.get('description', ''),
                    'severity': 'high'
                })
        
        # Determine cranial nerves NOT tested
        for cn, assessment in self.result.cranial_nerve_assessment.items():
            if not assessment['tested']:
                self.result.cranial_nerves_not_tested.append(cn)
            elif not assessment['technique_proper']:
                self.result.cranial_nerves_improperly_tested.append(cn)
        
        # Sort and rank egregious behaviors
        egregious_behaviors.sort(key=lambda x: (
            0 if x['severity'] == 'critical' else 1 if x['severity'] == 'high' else 2,
            x['timestamp_sec']
        ))
        
        for i, eb in enumerate(egregious_behaviors[:20]):
            eb['rank'] = i + 1
            eb['reference'] = DR_HUNTER_REFERENCES.get(eb['category'], {}).get('standard', '')
            self.result.top_egregious_behaviors.append(eb)
        
        # Compare to report claims
        if report_claims:
            self._compare_claims(report_claims)
        
        # Analyze transcript for misrepresentations
        if transcript and report_claims:
            misrep_result = self.analyze_transcript_for_misrepresentations(transcript, report_claims)
            self.result.transcript_misrepresentations = misrep_result.get('misrepresentations', [])
        
        # Calculate exam duration (frames with actual testing)
        testing_frames = sum(1 for a in frame_analyses 
                           if a.get('test_being_performed', {}).get('type') not in ['none', ''])
        # Assume 3 sec per frame
        self.result.exam_duration_actual_sec = testing_frames * 3
        
        return self.result
    
    def _compare_claims(self, claims: Dict):
        """Compare video observations to report claims."""
        
        # Cranial nerves
        if 'cranial_nerves' in claims:
            if self.result.cranial_nerves_not_tested:
                self.result.claim_vs_reality.append({
                    'category': 'cranial_nerves',
                    'report_claim': claims['cranial_nerves'],
                    'video_observation': f"NOT TESTED: {', '.join(self.result.cranial_nerves_not_tested)}",
                    'discrepancy_type': 'not_performed',
                    'severity': 'critical',
                    'reference': DR_HUNTER_REFERENCES['cranial_nerves']['standard']
                })
        
        # ROM
        if 'rom' in claims:
            goniometer_used = any(r.get('goniometer_used') for r in self.result.rom_assessments)
            if not goniometer_used:
                self.result.claim_vs_reality.append({
                    'category': 'range_of_motion',
                    'report_claim': claims['rom'],
                    'video_observation': 'No goniometer used - ROM not objectively measured',
                    'discrepancy_type': 'technique_error',
                    'severity': 'high',
                    'reference': DR_HUNTER_REFERENCES['rom']['standard']
                })
        
        # Mental status
        if 'mental_status' in claims:
            if not self.result.mental_status or not self.result.mental_status.get('questions_observed'):
                self.result.claim_vs_reality.append({
                    'category': 'mental_status',
                    'report_claim': claims['mental_status'],
                    'video_observation': 'Mental status testing not clearly observed',
                    'discrepancy_type': 'not_performed',
                    'severity': 'high',
                    'reference': DR_HUNTER_REFERENCES['mental_status']['standard']
                })
        
        # Exam time
        if 'exam_time' in claims:
            claimed_min = float(claims['exam_time'].split()[0]) if claims['exam_time'][0].isdigit() else 30
            actual_min = self.result.total_video_duration_sec / 60
            if actual_min < claimed_min * 0.7:
                self.result.claim_vs_reality.append({
                    'category': 'exam_duration',
                    'report_claim': claims['exam_time'],
                    'video_observation': f'Video shows only {actual_min:.1f} minutes',
                    'discrepancy_type': 'misrepresented',
                    'severity': 'high'
                })
    
    def generate_report(self) -> str:
        """Generate comprehensive report per Dorothy's format."""
        r = self.result
        
        lines = [
            "=" * 80,
            "CME ANALYSIS REPORT",
            "=" * 80,
            f"Project ID: {r.project_id}",
            f"Patient: {r.patient_name}",
            f"Examiner: {r.examiner_name}",
            f"Exam Date: {r.exam_date}",
            f"Analysis Date: {r.analysis_date}",
            "",
            f"Video Coverage: {r.video_coverage_percent:.1f}%",
            f"Frames Analyzed: {r.frames_analyzed}",
            "",
        ]
        
        # 1. TOP EGREGIOUS BEHAVIORS (First per Dorothy)
        lines.extend([
            "=" * 80,
            "TOP EGREGIOUS BEHAVIORS",
            "=" * 80,
        ])
        
        for eb in r.top_egregious_behaviors[:20]:
            lines.append(f"\n{eb['rank']}. {eb['category'].upper()}")
            lines.append(f"   Time: {eb['timestamp_sec']:.0f}s ({eb['timestamp_sec']/60:.1f} min)")
            lines.append(f"   {eb['description']}")
            if eb.get('reference'):
                lines.append(f"   Reference: {eb['reference']}")
        
        # 2. CLAIM VS REALITY (Most Important per Dorothy)
        lines.extend([
            "",
            "=" * 80,
            "CLAIM VS REALITY (MOST IMPORTANT)",
            "=" * 80,
        ])
        
        for cvr in r.claim_vs_reality:
            lines.append(f"\n[{cvr['severity'].upper()}] {cvr['category'].upper()}")
            lines.append(f"   REPORT CLAIMS: {cvr['report_claim']}")
            lines.append(f"   VIDEO SHOWS: {cvr['video_observation']}")
            if cvr.get('reference'):
                lines.append(f"   Reference: {cvr['reference']}")
        
        # Transcript misrepresentations
        if r.transcript_misrepresentations:
            lines.extend([
                "",
                "=" * 80,
                "TRANSCRIPT MISREPRESENTATIONS",
                "=" * 80,
            ])
            for tm in r.transcript_misrepresentations:
                lines.append(f"\n[{tm['severity'].upper()}] {tm['category']}")
                lines.append(f"   Report says: {tm['report_says']}")
                lines.append(f"   Actually said: {tm['transcript_shows']}")
                if tm.get('exact_quote'):
                    lines.append(f"   Quote: \"{tm['exact_quote']}\"")
        
        # 3. DOCTOR BEHAVIOR
        lines.extend([
            "",
            "=" * 80,
            "DOCTOR BEHAVIOR",
            "=" * 80,
            f"Was Doctor Rude: {'YES' if r.was_doctor_rude else 'NO'}",
            f"Times Not Observing Patient: {len(r.not_observing_patient)}",
            f"Interruption Count: {r.interruption_count}",
        ])
        
        if r.interruptions:
            lines.append("\nINTERRUPTIONS (with timestamps):")
            for intr in r.interruptions:
                lines.append(f"  - {intr['timestamp_sec']:.0f}s: {intr['type']} - {intr['description']}")
        
        # 4. PATIENT OBSERVATIONS
        lines.extend([
            "",
            "=" * 80,
            "PATIENT OBSERVATIONS",
            "=" * 80,
            f"Patient Crying: {len(r.patient_crying_instances)} instances",
            f"Patient Confused: {len(r.patient_confusion_instances)} instances",
            f"Patient Distress: {len(r.patient_distress_instances)} instances",
        ])
        
        if r.patient_crying_instances:
            lines.append("\nCrying instances:")
            for pc in r.patient_crying_instances:
                lines.append(f"  - {pc['timestamp_sec']:.0f}s ({pc['timestamp_sec']/60:.1f} min)")
        
        if r.patient_confusion_instances:
            lines.append("\nConfusion instances:")
            for pc in r.patient_confusion_instances:
                lines.append(f"  - {pc['timestamp_sec']:.0f}s ({pc['timestamp_sec']/60:.1f} min)")
        
        # 5. TIMING
        lines.extend([
            "",
            "=" * 80,
            "EXAM TIMING",
            "=" * 80,
            f"Total Video Duration: {r.total_video_duration_sec:.0f}s ({r.total_video_duration_sec/60:.1f} min)",
            f"Actual Hands-On Exam: ~{r.exam_duration_actual_sec:.0f}s ({r.exam_duration_actual_sec/60:.1f} min)",
            f"Claimed Exam Time: {r.exam_duration_claimed_min} min",
        ])
        
        # 6. CRANIAL NERVES
        lines.extend([
            "",
            "=" * 80,
            "CRANIAL NERVE ASSESSMENT",
            "=" * 80,
        ])
        
        if r.cranial_nerves_not_tested:
            lines.append(f"\n⚠️ NOT TESTED:")
            for cn in r.cranial_nerves_not_tested:
                lines.append(f"  - {cn}")
        
        if r.cranial_nerves_improperly_tested:
            lines.append(f"\n⚠️ IMPROPERLY TESTED:")
            for cn in r.cranial_nerves_improperly_tested:
                lines.append(f"  - {cn}")
        
        lines.append(f"\nReference: {DR_HUNTER_REFERENCES['cranial_nerves']['standard']}")
        
        # 7. MENTAL STATUS
        if r.mental_status:
            lines.extend([
                "",
                "=" * 80,
                "MENTAL STATUS TESTING",
                "=" * 80,
                f"Test Type: {r.mental_status.get('test_type', 'Unknown').upper()}",
                f"Questions Observed: {len(r.mental_status.get('questions_observed', []))}",
            ])
            for q in r.mental_status.get('questions_observed', []):
                lines.append(f"  - {q}")
        
        # 8. RANGE OF MOTION
        lines.extend([
            "",
            "=" * 80,
            "RANGE OF MOTION",
            "=" * 80,
        ])
        
        goniometer_ever_used = any(rom.get('goniometer_used') for rom in r.rom_assessments)
        lines.append(f"Goniometer Used: {'YES' if goniometer_ever_used else 'NO ⚠️'}")
        
        for rom in r.rom_assessments:
            lines.append(f"\n{rom['joint'].upper()}")
            lines.append(f"  Observed ROM: {rom.get('observed_rom', 'Not measured')}")
            lines.append(f"  Limited: {'Yes' if rom.get('appears_limited') else 'No'}")
            lines.append(f"  Goniometer: {'Yes' if rom.get('goniometer_used') else 'No'}")
        
        if not goniometer_ever_used:
            lines.append(f"\nReference: {DR_HUNTER_REFERENCES['rom']['standard']}")
        
        # 9. BODY PART BREAKDOWN
        lines.extend([
            "",
            "=" * 80,
            "ANALYSIS BY BODY PART",
            "=" * 80,
        ])
        
        for bp, analysis in r.body_part_analysis.items():
            if analysis['tests_performed'] or analysis['technique_issues']:
                lines.append(f"\n{bp.upper()}")
                if analysis['tests_performed']:
                    lines.append(f"  Tests: {', '.join(set(analysis['tests_performed'][:5]))}")
                if analysis['technique_issues']:
                    lines.append(f"  Issues: {', '.join(set(analysis['technique_issues'][:3]))}")
        
        # Summary
        lines.extend([
            "",
            "=" * 80,
            "SUMMARY",
            "=" * 80,
            f"Total Issues Found: {len(r.claim_vs_reality) + len(r.top_egregious_behaviors)}",
            f"Analysis Cost: ${r.total_cost_usd:.2f}",
        ])
        
        return "\n".join(lines)
    
    def save_project(self, output_dir: str, redlined_report_path: str = None):
        """Save project by patient name with all data."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save JSON results
        with open(output_path / "analysis_results.json", 'w') as f:
            json.dump(asdict(self.result), f, indent=2, default=str)
        
        # Save text report
        report = self.generate_report()
        with open(output_path / "analysis_report.txt", 'w') as f:
            f.write(report)
        
        # Copy redlined report if provided
        if redlined_report_path and os.path.exists(redlined_report_path):
            import shutil
            shutil.copy(redlined_report_path, output_path / "redlined_report_original.pdf")
        
        # Save project manifest
        manifest = {
            "project_id": self.result.project_id,
            "patient_name": self.result.patient_name,
            "examiner_name": self.result.examiner_name,
            "analysis_date": self.result.analysis_date,
            "video_coverage_percent": self.result.video_coverage_percent,
            "redlined_report_included": redlined_report_path is not None
        }
        with open(output_path / "project_manifest.json", 'w') as f:
            json.dump(manifest, f, indent=2)
        
        print(f"\nProject saved to: {output_path}")
        print(f"Project ID: {self.result.project_id}")
        
        return output_path


def analyze_cme_dorothy(
    video_paths: List[str],
    patient_name: str,
    examiner_name: str = None,
    exam_date: str = None,
    report_claims: Dict = None,
    transcript: str = None,
    redlined_report_path: str = None,
    api_key: str = None,
    output_dir: str = None,
    frame_interval: float = 3.0
) -> DorothyAnalysisResult:
    """
    Run complete CME analysis per Dorothy's requirements.
    
    Args:
        video_paths: List of video file paths
        patient_name: Patient name (required for project saving)
        examiner_name: Examining doctor name
        exam_date: Date of examination
        report_claims: Dict of claims from doctor's report
        transcript: Full transcript text
        redlined_report_path: Path to redlined report for verification
        api_key: Provider API key
        output_dir: Output directory (will create patient-named subfolder)
        frame_interval: Seconds between frames (default 3 for better coverage)
        
    Returns:
        DorothyAnalysisResult
    """
    # Initialize
    analyzer = CMEDorothyAnalyzer(api_key=api_key)
    analyzer.result.patient_name = patient_name
    analyzer.result.examiner_name = examiner_name or ""
    analyzer.result.exam_date = exam_date or ""
    analyzer.result.project_id = analyzer.generate_project_id(patient_name)
    
    # Setup output directory
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="cme_dorothy_")
    
    project_dir = Path(output_dir) / analyzer.result.project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract and analyze frames
    print("\n" + "=" * 60)
    print("EXTRACTING VIDEO FRAMES")
    print("=" * 60)
    
    frames, duration = analyzer.extract_frames(video_paths, str(project_dir), frame_interval)
    
    print("\n" + "=" * 60)
    print("ANALYZING FRAMES")
    print("=" * 60)
    print(f"Analyzing {len(frames)} frames...")
    print(f"Estimated cost: ${len(frames) * 0.015:.2f}")
    
    frame_analyses = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for frame in frames:
            parts = frame.stem.split('_')
            frame_num = int(parts[-1])
            timestamp = (frame_num - 1) * frame_interval
            futures[executor.submit(analyzer.analyze_frame, frame, timestamp)] = frame
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            frame_analyses.append(future.result())
            if completed % 20 == 0 or completed == len(frames):
                print(f"  Progress: {completed}/{len(frames)}")
    
    frame_analyses.sort(key=lambda x: x.get('timestamp_sec', 0))
    
    # Compile results
    print("\n" + "=" * 60)
    print("COMPILING RESULTS")
    print("=" * 60)
    
    result = analyzer.compile_results(frame_analyses, report_claims, transcript)
    
    # Generate and print report
    report = analyzer.generate_report()
    print("\n" + report)
    
    # Save project
    analyzer.save_project(str(project_dir), redlined_report_path)
    
    return result
