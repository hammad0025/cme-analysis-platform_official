"""
CME BEHAVIOR ANALYZER - Deep Professionalism & Sentiment Analysis
================================================================

Specialized module for analyzing doctor behavior, sentiment, and professionalism.

VISUAL BEHAVIOR ANALYSIS:
- Eye contact with patient
- Body orientation (facing patient vs turned away)
- Rushed movements
- Dismissive gestures
- Attention level (distracted, looking at phone/notes)
- Response to patient distress
- Physical proximity appropriateness

AUDIO/VERBAL BEHAVIOR ANALYSIS:
- Tone of voice (condescending, dismissive, rude, empathetic)
- Interrupting patient
- Not letting patient finish speaking
- Ignoring patient's questions/concerns
- Minimizing symptoms
- Inappropriate comments
- Rushing patient
- Defensive behavior when questioned
- Sarcasm or mockery
- Cold/clinical vs warm/caring demeanor

EMPATHY INDICATORS:
- Acknowledging patient's pain
- Asking follow-up questions about symptoms
- Taking time to explain
- Responding to emotional cues
- Offering comfort or reassurance
- Validating patient concerns
"""

import base64
import json
import subprocess
import os
import threading
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, TYPE_CHECKING
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

from .cme_analysis_utils import (
    DEFAULT_SONNET_MODEL,
    add_analyze_result_cost,
)
from .prompts.production import (
    BEHAVIOR_VERBAL_PROMPT_VERSION,
    BEHAVIOR_VISUAL_PROMPT_VERSION,
    VERBAL_BEHAVIOR_PROMPT,
    VISUAL_BEHAVIOR_PROMPT,
)
from .vision_client import VisionClient, make_vision_client

if TYPE_CHECKING:
    from .cme_transcription import Transcript


class BehaviorSeverity(Enum):
    CRITICAL = "critical"  # Clear rudeness, mocking, inappropriate
    HIGH = "high"  # Dismissiveness, ignoring concerns
    MEDIUM = "medium"  # Rushing, inattention
    LOW = "low"  # Minor professionalism lapses


@dataclass
class VisualBehaviorObservation:
    """Observation from video frame."""
    timestamp_sec: float
    frame_id: str

    # Relative path under behavior/ pointing at the externalized raw model
    # output (raw/{frame_id}.txt) for provenance auditing. Optional so
    # older checkpoints without this field still rehydrate cleanly.
    raw_response: str = ""

    # Eye contact / attention
    doctor_looking_at_patient: bool = True
    doctor_looking_at_notes: bool = False
    doctor_looking_at_phone: bool = False
    doctor_looking_elsewhere: bool = False
    
    # Body orientation
    doctor_facing_patient: bool = True
    doctor_turned_away: bool = False
    doctor_leaning_in: bool = False  # Positive - engaged
    doctor_leaning_back: bool = False  # Could indicate disengagement
    
    # Movement/pace
    appears_rushed: bool = False
    hasty_movements: bool = False
    thorough_examination: bool = False
    
    # Gestures
    dismissive_gesture: bool = False
    impatient_gesture: bool = False
    reassuring_gesture: bool = False
    
    # Patient state
    patient_appears_distressed: bool = False
    patient_trying_to_speak: bool = False
    patient_in_pain: bool = False
    
    # Doctor response to patient
    acknowledging_patient: bool = True
    ignoring_patient_cue: bool = False
    
    notes: str = ""

    visibility: str = ""
    occlusion_notes: str = ""
    confidence: float = 0.0
    prompt_version: str = ""

    model_id: str = ""
    provider: str = ""


@dataclass
class VerbalBehaviorObservation:
    """Observation from transcript segment.

    `start_sec` / `end_sec` are `Optional[float]` because the legacy
    string-only transcript path has no real word-level timestamps to
    attach. In that path both fields are `None` (honest: no timing
    information). When a structured `Transcript` is provided via
    `transcript_obj`, the fields carry real segment boundaries pulled
    from the underlying `TranscriptWord` start/end values.
    """
    segment_id: str
    start_sec: Optional[float]
    end_sec: Optional[float]
    speaker: str
    text: str
    
    # Tone
    tone: str = "neutral"  # professional, empathetic, condescending, dismissive, rude, cold, rushed, sarcastic
    
    # Negative behaviors
    interrupting: bool = False
    cutting_off_patient: bool = False
    ignoring_question: bool = False
    dismissing_symptom: bool = False
    minimizing_complaint: bool = False
    rude_comment: bool = False
    sarcastic: bool = False
    condescending: bool = False
    inappropriate_comment: bool = False
    rushing_patient: bool = False
    defensive: bool = False
    impatient: bool = False
    
    # Positive behaviors
    empathetic: bool = False
    validating: bool = False
    explaining: bool = False
    asking_followup: bool = False
    acknowledging_pain: bool = False
    offering_comfort: bool = False
    patient_focused: bool = False
    
    problematic_quote: str = ""
    explanation: str = ""


@dataclass
class BehaviorIssue:
    """A significant behavior issue to report."""
    category: str
    description: str
    severity: BehaviorSeverity
    evidence: str
    timestamp_sec: Optional[float] = None
    quote: Optional[str] = None
    helps_plaintiff: bool = True


@dataclass
class BehaviorAnalysisResult:
    """Complete behavior analysis result."""
    case_id: str = ""
    plaintiff_name: str = ""
    examiner_name: str = ""
    
    # Visual observations
    visual_observations: List[Dict] = field(default_factory=list)
    
    # Verbal observations
    verbal_observations: List[Dict] = field(default_factory=list)
    
    # Issues found
    behavior_issues: List[Dict] = field(default_factory=list)
    
    # Scores
    eye_contact_score: float = 0.0  # % of time making eye contact
    attention_score: float = 0.0  # % of time focused on patient
    empathy_score: float = 0.0  # 0-10
    professionalism_score: float = 0.0  # 0-10
    overall_demeanor: str = ""  # professional, cold, dismissive, hostile, etc.
    
    # Counts
    interruption_count: int = 0
    dismissive_instances: int = 0
    rude_instances: int = 0
    empathetic_instances: int = 0
    
    # Key evidence
    problematic_quotes: List[Dict] = field(default_factory=list)
    worst_moments: List[Dict] = field(default_factory=list)
    
    # Cost
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    visual_prompt_version: str = ""
    verbal_prompt_version: str = ""

    # ASR provenance (populated when a structured Transcript is fed
    # through `analyze_cme_behavior(..., transcript_obj=...)`). Empty
    # strings when the legacy string transcript path is used or when no
    # transcript was supplied.
    transcription_backend: str = ""
    transcription_model: str = ""


class CMEBehaviorAnalyzer:
    """Specialized analyzer for doctor behavior and professionalism."""
    
    COST_PER_FRAME = 0.015
    COST_PER_TRANSCRIPT_SEGMENT = 0.01
    
    def __init__(
        self,
        api_key: str = None,
        model: str = None,
        vision_client: Optional[VisionClient] = None,
    ):
        """Initialize the behavior analyzer.

        Defaults to an Anthropic-backed VisionClient (preserving existing
        runtime behavior). Pass `vision_client` to plug in OpenAI / Gemini.
        """
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        self.model = model or DEFAULT_SONNET_MODEL

        if vision_client is None:
            if not self.api_key:
                raise ValueError("Anthropic API key required")
            self.vision_client: VisionClient = make_vision_client(
                "anthropic", api_key=self.api_key, model_id=self.model
            )
        else:
            self.vision_client = vision_client

        self.result = BehaviorAnalysisResult()
        self.result.visual_prompt_version = BEHAVIOR_VISUAL_PROMPT_VERSION
        self.result.verbal_prompt_version = BEHAVIOR_VERBAL_PROMPT_VERSION
        self._parallel_request_delay = 0.0
        # Set by analyze_cme_behavior to behavior/raw/. When set, per-frame
        # raw model output is externalized there and VisualBehaviorObservation
        # .raw_response holds the relative path instead of inline text.
        self._raw_output_dir: Optional[Path] = None
        
    def analyze_frame_behavior(self, frame_path: Path,
                               timestamp_sec: float) -> VisualBehaviorObservation:
        """Analyze behavior in a single frame via the configured VisionClient."""
        delay = getattr(self, "_parallel_request_delay", 0.0) or 0.0
        if delay > 0:
            time.sleep(delay)

        with open(frame_path, 'rb') as f:
            image_bytes = f.read()

        provider = getattr(self.vision_client, "provider", "")
        default_model_id = (
            getattr(self.vision_client, "default_model_id", "") or self.model
        )

        try:
            result = self.vision_client.analyze(
                image_bytes,
                VISUAL_BEHAVIOR_PROMPT,
                max_tokens=1500,
                mime_type="image/jpeg",
            )
            raw_full = result.text or ""
            add_analyze_result_cost(
                self.result, result, fallback_usd=self.COST_PER_FRAME
            )

            stripped = raw_full
            try:
                if "```json" in stripped:
                    stripped = stripped.split("```json")[1].split("```")[0]
                elif "```" in stripped:
                    stripped = stripped.split("```")[1].split("```")[0]
                data = json.loads(stripped.strip())
            except Exception:
                data = {}

            stored_raw = ""
            raw_dir = getattr(self, "_raw_output_dir", None)
            if raw_dir is not None:
                try:
                    Path(raw_dir).mkdir(parents=True, exist_ok=True)
                    (Path(raw_dir) / f"{frame_path.stem}.txt").write_text(
                        raw_full, encoding="utf-8"
                    )
                    stored_raw = f"raw/{frame_path.stem}.txt"
                except OSError:
                    stored_raw = ""

            eye = data.get('eye_contact', {})
            body = data.get('body_language', {})
            pace = data.get('pace_and_movement', {})
            gestures = data.get('gestures', {})
            patient = data.get('patient_state', {})
            response_data = data.get('doctor_response', {})
            try:
                conf = float(data.get("confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                conf = 0.0

            obs = VisualBehaviorObservation(
                timestamp_sec=timestamp_sec,
                frame_id=frame_path.stem,
                raw_response=stored_raw,
                doctor_looking_at_patient=eye.get('looking_at_patient', True),
                doctor_looking_at_notes=eye.get('looking_at_notes', False),
                doctor_looking_at_phone=eye.get('looking_at_phone', False),
                doctor_looking_elsewhere=eye.get('looking_elsewhere', False),
                doctor_facing_patient=body.get('facing_patient', True),
                doctor_turned_away=body.get('turned_away', False),
                doctor_leaning_in=body.get('leaning_in_engaged', False),
                doctor_leaning_back=body.get('leaning_back_disengaged', False),
                appears_rushed=pace.get('appears_rushed', False),
                hasty_movements=pace.get('hasty_movements', False),
                thorough_examination=pace.get('thorough_careful', False),
                dismissive_gesture=gestures.get('dismissive_gesture', False),
                impatient_gesture=gestures.get('impatient_gesture', False),
                reassuring_gesture=gestures.get('reassuring_gesture', False),
                patient_appears_distressed=patient.get('appears_distressed', False),
                patient_trying_to_speak=patient.get('trying_to_speak', False),
                patient_in_pain=patient.get('in_visible_pain', False),
                acknowledging_patient=response_data.get('acknowledging_patient', True),
                ignoring_patient_cue=response_data.get('ignoring_patient_cue', False),
                notes=data.get('detailed_notes', ''),
                visibility=str(data.get("visibility", "") or ""),
                occlusion_notes=str(data.get("occlusion_notes", "") or ""),
                confidence=conf,
                prompt_version=BEHAVIOR_VISUAL_PROMPT_VERSION,
                model_id=result.model_id or default_model_id,
                provider=result.provider or provider,
            )

            return obs

        except Exception as e:
            print(f"Error analyzing frame {frame_path.name}: {e}")
            return VisualBehaviorObservation(
                timestamp_sec=timestamp_sec,
                frame_id=frame_path.stem,
                prompt_version=BEHAVIOR_VISUAL_PROMPT_VERSION,
                model_id=default_model_id,
                provider=provider,
            )
    
    def analyze_transcript_behavior(
        self,
        transcript: Optional[str] = None,
        *,
        transcript_obj: Optional["Transcript"] = None,
    ) -> List[VerbalBehaviorObservation]:
        """Analyze transcript for verbal behavior issues.

        Two paths:

        - Structured (preferred): `transcript_obj` is a `Transcript` from
          `cme_transcription`. Chunks come from REAL `TranscriptSegment`
          boundaries: consecutive segments are grouped until ~400 words
          OR a 30s span boundary is reached, whichever comes first.
          Each chunk's `start_sec` / `end_sec` are pulled from the first
          and last `TranscriptWord` in the chunk so observations carry
          honest timing.

        - Legacy string (fallback): `transcript` is a plain string. The
          old word-count chunking is preserved, but observations carry
          `start_sec=None` / `end_sec=None` (honest: no timing info
          available). The synthetic `i * 0.5` placeholder from before
          A3 is intentionally gone -- faking timestamps is worse than
          declaring them unknown.

        Routes through VisionClient.text_analyze so the verbal-behavior
        pass can run under any supported provider.
        """
        if transcript_obj is None and not transcript:
            return []

        chunks = self._build_transcript_chunks(transcript_obj, transcript)
        observations: List[VerbalBehaviorObservation] = []

        for chunk_idx, chunk in enumerate(chunks):
            chunk_text = chunk["text"]
            chunk_start = chunk.get("start_sec")
            chunk_end = chunk.get("end_sec")

            try:
                prompt = VERBAL_BEHAVIOR_PROMPT.format(transcript=chunk_text)
                result = self.vision_client.text_analyze(prompt, max_tokens=2500)
                raw = getattr(result, "text", "") or getattr(result, "raw_text", "") or ""
                add_analyze_result_cost(
                    self.result, result, fallback_usd=self.COST_PER_TRANSCRIPT_SEGMENT
                )

                try:
                    if "```json" in raw:
                        raw = raw.split("```json")[1].split("```")[0]
                    elif "```" in raw:
                        raw = raw.split("```")[1].split("```")[0]
                    data = json.loads(raw.strip())
                except Exception:
                    data = {}

                for j, ex in enumerate(data.get('exchanges', [])):
                    neg = ex.get('negative_behaviors', {})
                    pos = ex.get('positive_behaviors', {})

                    obs = VerbalBehaviorObservation(
                        segment_id=f"seg_{chunk_idx}_{j}",
                        start_sec=chunk_start,
                        end_sec=chunk_end,
                        speaker=ex.get('speaker', ''),
                        text=ex.get('text', ''),
                        tone=ex.get('tone', 'neutral'),
                        interrupting=neg.get('interrupting', False),
                        cutting_off_patient=neg.get('cutting_off_patient', False),
                        ignoring_question=neg.get('ignoring_question', False),
                        dismissing_symptom=neg.get('dismissing_symptom', False),
                        minimizing_complaint=neg.get('minimizing_complaint', False),
                        rude_comment=neg.get('rude_comment', False),
                        sarcastic=neg.get('sarcastic', False),
                        condescending=neg.get('condescending', False),
                        inappropriate_comment=neg.get('inappropriate_comment', False),
                        rushing_patient=neg.get('rushing_patient', False),
                        defensive=neg.get('defensive', False),
                        impatient=neg.get('impatient', False),
                        empathetic=pos.get('empathetic', False),
                        validating=pos.get('validating', False),
                        explaining=pos.get('explaining', False),
                        asking_followup=pos.get('asking_followup', False),
                        acknowledging_pain=pos.get('acknowledging_pain', False),
                        offering_comfort=pos.get('offering_comfort', False),
                        patient_focused=pos.get('patient_focused', False),
                        problematic_quote=ex.get('text', '') if ex.get('is_problematic') else '',
                        explanation=ex.get('problem_explanation', '')
                    )
                    observations.append(obs)

                for pq in data.get('problematic_quotes', []):
                    self.result.problematic_quotes.append({
                        'quote': pq.get('quote', ''),
                        'problem': pq.get('problem', ''),
                        'severity': pq.get('severity', 'medium'),
                        'segment': chunk_idx,
                    })

            except Exception as e:
                print(f"Error analyzing transcript segment: {e}")

        return observations

    @staticmethod
    def _build_transcript_chunks(
        transcript_obj: Optional["Transcript"],
        transcript: Optional[str],
    ) -> List[Dict]:
        """Group transcript content into prompt-sized chunks.

        Returns a list of dicts: ``{text, start_sec, end_sec}``.
        `start_sec`/`end_sec` are `None` for the legacy string path
        (no timing info available) and floats for the structured path.

        Structured path: consecutive segments are concatenated until the
        running word count reaches ~400 OR the time span exceeds 30
        seconds, whichever comes first. Each chunk's start/end are
        taken from the first/last `TranscriptWord` in the contained
        segments (falling back to segment-level times if word-level is
        missing).
        """
        MAX_WORDS = 400
        MAX_SPAN_SEC = 30.0

        chunks: List[Dict] = []
        if transcript_obj is not None and getattr(transcript_obj, "segments", None):
            buf_text: List[str] = []
            buf_word_count = 0
            buf_start: Optional[float] = None
            buf_end: Optional[float] = None

            def _flush():
                if not buf_text:
                    return
                chunks.append(
                    {
                        "text": " ".join(t for t in buf_text if t).strip(),
                        "start_sec": buf_start,
                        "end_sec": buf_end,
                    }
                )

            for seg in transcript_obj.segments:
                seg_text = (seg.text or "").strip()
                if not seg_text:
                    continue
                seg_words = list(seg.words or [])
                if seg_words:
                    seg_start = float(seg_words[0].start_sec)
                    seg_end = float(seg_words[-1].end_sec)
                    seg_word_count = len(seg_words)
                else:
                    seg_start = float(seg.start_sec or 0.0)
                    seg_end = float(seg.end_sec or 0.0)
                    seg_word_count = len(seg_text.split())

                proposed_start = buf_start if buf_start is not None else seg_start
                proposed_span = seg_end - proposed_start
                proposed_word_count = buf_word_count + seg_word_count

                if buf_text and (
                    proposed_word_count > MAX_WORDS or proposed_span > MAX_SPAN_SEC
                ):
                    _flush()
                    buf_text = []
                    buf_word_count = 0
                    buf_start = None
                    buf_end = None

                if not buf_text:
                    buf_start = seg_start
                buf_end = seg_end
                buf_text.append(seg_text)
                buf_word_count += seg_word_count

            _flush()
            return chunks

        if transcript:
            words = transcript.split()
            chunk_size = 400
            for i in range(0, len(words), chunk_size):
                chunks.append(
                    {
                        "text": " ".join(words[i:i + chunk_size]),
                        "start_sec": None,
                        "end_sec": None,
                    }
                )
        return chunks
    
    def compile_behavior_results(self, 
                                visual_obs: List[VisualBehaviorObservation],
                                verbal_obs: List[VerbalBehaviorObservation] = None):
        """Compile all observations into final result."""
        
        # Store observations
        self.result.visual_observations = [asdict(o) for o in visual_obs]
        if verbal_obs:
            self.result.verbal_observations = [asdict(o) for o in verbal_obs]
        
        # Visual behavior scores
        total_frames = len(visual_obs)
        if total_frames > 0:
            eye_contact_frames = sum(1 for o in visual_obs if o.doctor_looking_at_patient)
            self.result.eye_contact_score = (eye_contact_frames / total_frames) * 100
            
            attention_frames = sum(1 for o in visual_obs 
                                  if o.doctor_facing_patient and not o.doctor_looking_at_phone)
            self.result.attention_score = (attention_frames / total_frames) * 100
        
        # Collect visual behavior issues
        issues = []
        
        # Not looking at patient
        not_looking = [o for o in visual_obs if not o.doctor_looking_at_patient]
        if len(not_looking) > 3:
            issues.append(BehaviorIssue(
                category="INATTENTION",
                description=f"Doctor not looking at patient in {len(not_looking)}/{total_frames} frames ({len(not_looking)/total_frames*100:.0f}%)",
                severity=BehaviorSeverity.MEDIUM if len(not_looking) < total_frames/3 else BehaviorSeverity.HIGH,
                evidence=f"Frames: {[o.timestamp_sec for o in not_looking[:5]]}"
            ))
        
        # Phone usage
        phone = [o for o in visual_obs if o.doctor_looking_at_phone]
        if phone:
            issues.append(BehaviorIssue(
                category="DISTRACTION",
                description=f"Doctor looking at phone during examination",
                severity=BehaviorSeverity.HIGH,
                evidence=f"At timestamps: {[o.timestamp_sec for o in phone]}"
            ))
        
        # Turned away
        turned = [o for o in visual_obs if o.doctor_turned_away]
        if len(turned) > 3:
            issues.append(BehaviorIssue(
                category="DISENGAGEMENT",
                description=f"Doctor turned away from patient in {len(turned)} frames",
                severity=BehaviorSeverity.MEDIUM,
                evidence=f"At timestamps: {[o.timestamp_sec for o in turned[:5]]}"
            ))
        
        # Rushing
        rushed = [o for o in visual_obs if o.appears_rushed or o.hasty_movements]
        if len(rushed) > 5:
            issues.append(BehaviorIssue(
                category="RUSHING",
                description=f"Doctor appeared rushed in {len(rushed)} frames",
                severity=BehaviorSeverity.MEDIUM,
                evidence=f"At timestamps: {[o.timestamp_sec for o in rushed[:5]]}"
            ))
        
        # Dismissive gestures
        dismissive = [o for o in visual_obs if o.dismissive_gesture or o.impatient_gesture]
        if dismissive:
            issues.append(BehaviorIssue(
                category="DISMISSIVENESS",
                description=f"Dismissive/impatient gestures observed",
                severity=BehaviorSeverity.HIGH,
                evidence=f"At timestamps: {[o.timestamp_sec for o in dismissive]}"
            ))
        
        # Ignoring patient distress
        ignored = [o for o in visual_obs if o.patient_appears_distressed and o.ignoring_patient_cue]
        if ignored:
            issues.append(BehaviorIssue(
                category="IGNORING_DISTRESS",
                description=f"Patient distress ignored in {len(ignored)} instances",
                severity=BehaviorSeverity.HIGH,
                evidence=f"At timestamps: {[o.timestamp_sec for o in ignored]}"
            ))
        
        # Verbal behavior issues
        if verbal_obs:
            # Count behaviors
            self.result.interruption_count = sum(1 for o in verbal_obs if o.interrupting or o.cutting_off_patient)
            self.result.dismissive_instances = sum(1 for o in verbal_obs 
                                                   if o.dismissing_symptom or o.minimizing_complaint)
            self.result.rude_instances = sum(1 for o in verbal_obs 
                                            if o.rude_comment or o.sarcastic or o.condescending)
            self.result.empathetic_instances = sum(1 for o in verbal_obs if o.empathetic or o.validating)
            
            # Add issues
            if self.result.interruption_count > 2:
                issues.append(BehaviorIssue(
                    category="INTERRUPTING",
                    description=f"Doctor interrupted patient {self.result.interruption_count} times",
                    severity=BehaviorSeverity.HIGH,
                    evidence="See transcript analysis"
                ))
            
            if self.result.rude_instances > 0:
                issues.append(BehaviorIssue(
                    category="RUDENESS",
                    description=f"{self.result.rude_instances} rude/condescending/sarcastic comments",
                    severity=BehaviorSeverity.CRITICAL,
                    evidence="See problematic quotes"
                ))
            
            if self.result.dismissive_instances > 0:
                issues.append(BehaviorIssue(
                    category="DISMISSING_SYMPTOMS",
                    description=f"Dismissed/minimized patient symptoms {self.result.dismissive_instances} times",
                    severity=BehaviorSeverity.HIGH,
                    evidence="See problematic quotes"
                ))
            
            # Calculate verbal empathy score
            total_verbal = len(verbal_obs)
            if total_verbal > 0:
                positive_count = sum(1 for o in verbal_obs 
                                    if o.empathetic or o.validating or o.acknowledging_pain)
                negative_count = (self.result.rude_instances + 
                                self.result.dismissive_instances + 
                                self.result.interruption_count)
                
                self.result.empathy_score = max(0, min(10, 
                    5 + (positive_count - negative_count) / total_verbal * 10))
                
                self.result.professionalism_score = max(0, min(10,
                    10 - (negative_count / total_verbal) * 20))
        
        # Store issues
        self.result.behavior_issues = [asdict(i) for i in issues]
        
        # Determine overall demeanor
        if self.result.rude_instances > 0:
            self.result.overall_demeanor = "hostile"
        elif self.result.dismissive_instances > 3:
            self.result.overall_demeanor = "dismissive"
        elif self.result.attention_score < 50:
            self.result.overall_demeanor = "distracted"
        elif rushed and len(rushed) > total_frames / 3:
            self.result.overall_demeanor = "rushed"
        elif self.result.empathetic_instances > 3:
            self.result.overall_demeanor = "professional"
        else:
            self.result.overall_demeanor = "cold/clinical"
        
        # Identify worst moments
        worst = []
        for pq in self.result.problematic_quotes:
            if pq.get('severity') in ['critical', 'high']:
                worst.append(pq)
        
        for issue in issues:
            if issue.severity in [BehaviorSeverity.CRITICAL, BehaviorSeverity.HIGH]:
                worst.append({
                    'category': issue.category,
                    'description': issue.description,
                    'severity': issue.severity.value
                })
        
        self.result.worst_moments = worst[:10]  # Top 10
        
        return self.result
    
    def generate_behavior_report(self) -> str:
        """Generate human-readable behavior analysis report."""
        r = self.result
        
        lines = [
            "=" * 80,
            "CME BEHAVIOR & PROFESSIONALISM ANALYSIS",
            "=" * 80,
            "",
            f"Plaintiff: {r.plaintiff_name}",
            f"Examiner: {r.examiner_name}",
            "",
            "=" * 80,
            "BEHAVIOR SCORES",
            "=" * 80,
            f"Eye Contact:       {r.eye_contact_score:.0f}% of time",
            f"Attention:         {r.attention_score:.0f}% focused on patient",
            f"Empathy Score:     {r.empathy_score:.1f}/10",
            f"Professionalism:   {r.professionalism_score:.1f}/10",
            f"Overall Demeanor:  {r.overall_demeanor.upper()}",
            "",
            "=" * 80,
            "BEHAVIOR COUNTS",
            "=" * 80,
            f"Interruptions:     {r.interruption_count}",
            f"Dismissive:        {r.dismissive_instances}",
            f"Rude/Condescending:{r.rude_instances}",
            f"Empathetic:        {r.empathetic_instances}",
        ]
        
        if r.behavior_issues:
            lines.extend([
                "",
                "=" * 80,
                "BEHAVIOR ISSUES IDENTIFIED",
                "=" * 80,
            ])
            for issue in r.behavior_issues:
                sev = issue.get('severity', {})
                if isinstance(sev, dict):
                    sev_val = sev.get('value', 'medium')
                else:
                    sev_val = sev
                    
                icon = "🔴" if sev_val == 'critical' else "🟡" if sev_val == 'high' else "⚪"
                lines.append(f"\n{icon} {issue.get('category', '')}")
                lines.append(f"   {issue.get('description', '')}")
                if issue.get('evidence'):
                    lines.append(f"   Evidence: {issue.get('evidence')}")
        
        if r.problematic_quotes:
            lines.extend([
                "",
                "=" * 80,
                "PROBLEMATIC QUOTES",
                "=" * 80,
            ])
            for pq in r.problematic_quotes[:10]:
                lines.append(f"\n\"{pq.get('quote', '')}\"")
                lines.append(f"   Issue: {pq.get('problem', '')}")
                lines.append(f"   Severity: {pq.get('severity', '')}")
        
        if r.worst_moments:
            lines.extend([
                "",
                "=" * 80,
                "WORST MOMENTS",
                "=" * 80,
            ])
            for wm in r.worst_moments[:5]:
                lines.append(f"  - {wm.get('category', wm.get('problem', ''))}: {wm.get('description', wm.get('quote', ''))}")
        
        lines.extend([
            "",
            "=" * 80,
            f"Analysis Cost: ${r.total_cost_usd:.2f}",
            "=" * 80,
        ])
        
        return "\n".join(lines)


def _load_behavior_checkpoint(path: Path) -> Dict[str, dict]:
    done: Dict[str, dict] = {}
    if not path or not path.exists():
        return done
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            fid = row.get("frame_id")
            if fid:
                done[fid] = row.get("observation") or row
        except json.JSONDecodeError:
            continue
    return done


def _observation_has_model_output(stub: dict) -> bool:
    """False for behavior-pass failure stubs (no real model output landed).

    Mirrors the equivalent check used by the comprehensive analyzer:
    treat as "needs re-run" any stub where `raw_response` is empty/
    whitespace AND `notes` is empty AND `confidence == 0.0`. Older
    checkpoints predating the raw_response field still rehydrate cleanly
    because they will have at least `notes` or a non-zero confidence
    populated when the model actually produced output."""
    if not isinstance(stub, dict):
        return False
    raw = str(stub.get("raw_response") or "").strip()
    notes = str(stub.get("notes") or "").strip()
    try:
        conf = float(stub.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    if raw:
        return True
    if notes:
        return True
    if conf > 0.0:
        return True
    return False


def _observation_from_checkpoint(d: dict, frame_path: Path, timestamp_sec: float) -> VisualBehaviorObservation:
    try:
        conf = float(d.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    return VisualBehaviorObservation(
        timestamp_sec=float(d.get("timestamp_sec", timestamp_sec)),
        frame_id=d.get("frame_id", frame_path.stem),
        raw_response=str(d.get("raw_response", "") or ""),
        doctor_looking_at_patient=bool(d.get("doctor_looking_at_patient", True)),
        doctor_looking_at_notes=bool(d.get("doctor_looking_at_notes", False)),
        doctor_looking_at_phone=bool(d.get("doctor_looking_at_phone", False)),
        doctor_looking_elsewhere=bool(d.get("doctor_looking_elsewhere", False)),
        doctor_facing_patient=bool(d.get("doctor_facing_patient", True)),
        doctor_turned_away=bool(d.get("doctor_turned_away", False)),
        doctor_leaning_in=bool(d.get("doctor_leaning_in", False)),
        doctor_leaning_back=bool(d.get("doctor_leaning_back", False)),
        appears_rushed=bool(d.get("appears_rushed", False)),
        hasty_movements=bool(d.get("hasty_movements", False)),
        thorough_examination=bool(d.get("thorough_examination", False)),
        dismissive_gesture=bool(d.get("dismissive_gesture", False)),
        impatient_gesture=bool(d.get("impatient_gesture", False)),
        reassuring_gesture=bool(d.get("reassuring_gesture", False)),
        patient_appears_distressed=bool(d.get("patient_appears_distressed", False)),
        patient_trying_to_speak=bool(d.get("patient_trying_to_speak", False)),
        patient_in_pain=bool(d.get("patient_in_pain", False)),
        acknowledging_patient=bool(d.get("acknowledging_patient", True)),
        ignoring_patient_cue=bool(d.get("ignoring_patient_cue", False)),
        notes=d.get("notes", ""),
        visibility=str(d.get("visibility", "") or ""),
        occlusion_notes=str(d.get("occlusion_notes", "") or ""),
        confidence=conf,
        prompt_version=str(d.get("prompt_version", BEHAVIOR_VISUAL_PROMPT_VERSION) or ""),
        model_id=str(d.get("model_id", "") or ""),
        provider=str(d.get("provider", "") or ""),
    )


def analyze_cme_behavior(
    video_paths: List[str] = None,
    frames_dir: str = None,
    transcript: str = None,
    plaintiff_name: str = None,
    examiner_name: str = None,
    api_key: str = None,
    frame_interval: float = 5.0,
    output_dir: str = None,
    max_workers: int = 5,
    request_delay_sec: float = 0.0,
    resume: bool = False,
    model: str = None,
    vision_client: Optional[VisionClient] = None,
    transcript_obj: Optional["Transcript"] = None,
) -> BehaviorAnalysisResult:
    """
    Run behavior analysis on CME video/transcript.
    
    Args:
        video_paths: List of video files (will extract frames)
        frames_dir: Or provide pre-extracted frames directory
        transcript: Transcript text for verbal analysis
        plaintiff_name: Plaintiff name
        examiner_name: Examiner name
        api_key: Anthropic API key
        frame_interval: Seconds between frames
        output_dir: Where to save results
        max_workers: Parallel vision API workers
        request_delay_sec: Delay before each frame API call
        resume: Use behavior_checkpoint.jsonl in output_dir
        model: Anthropic model id
        
    Returns:
        BehaviorAnalysisResult
    """
    import tempfile

    analyzer = CMEBehaviorAnalyzer(
        api_key=api_key, model=model, vision_client=vision_client
    )
    analyzer.result.plaintiff_name = plaintiff_name or ""
    analyzer.result.examiner_name = examiner_name or ""
    
    # Get frames
    if frames_dir:
        frames = sorted(Path(frames_dir).glob("*.jpg"))
    elif video_paths:
        # Extract frames
        work_dir = output_dir or tempfile.mkdtemp(prefix="cme_behavior_")
        frames_path = Path(work_dir) / "frames"
        frames_path.mkdir(parents=True, exist_ok=True)
        
        fps = 1 / frame_interval
        all_frames = []
        
        for i, video in enumerate(video_paths):
            print(f"Extracting frames from video {i+1}...")
            output_pattern = str(frames_path / f'video{i+1}_frame_%04d.jpg')
            subprocess.run([
                'ffmpeg', '-i', video, '-vf', f'fps={fps}', '-q:v', '2',
                output_pattern, '-y', '-loglevel', 'error'
            ])
            all_frames.extend(sorted(frames_path.glob(f'video{i+1}_frame_*.jpg')))
        
        frames = all_frames
    else:
        raise ValueError("Must provide either video_paths or frames_dir")
    
    output_path = Path(output_dir) if output_dir else None
    if output_path:
        output_path.mkdir(parents=True, exist_ok=True)
        # Externalize raw model output to behavior/raw/ so the provenance
        # bundle can cite frame_id -> raw file. Only enabled when an
        # output dir is available (transient runs skip this).
        raw_dir = output_path / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        analyzer._raw_output_dir = raw_dir
    checkpoint_path = (output_path / "behavior_checkpoint.jsonl") if output_path else None
    if checkpoint_path:
        if resume:
            print(f"Behavior resume; checkpoint: {checkpoint_path}")
        elif checkpoint_path.exists():
            checkpoint_path.unlink()

    loaded: Dict[str, dict] = {}
    if resume and checkpoint_path:
        loaded = _load_behavior_checkpoint(checkpoint_path)

    visual_observations: List[VisualBehaviorObservation] = []
    pending_tasks: List[tuple] = []
    retry_count = 0
    for frame in frames:
        parts = frame.stem.split('_')
        frame_num = int(parts[-1])
        timestamp = (frame_num - 1) * frame_interval
        if frame.stem in loaded:
            stub = loaded[frame.stem]
            if resume and not _observation_has_model_output(stub):
                pending_tasks.append((frame, timestamp))
                retry_count += 1
            else:
                visual_observations.append(_observation_from_checkpoint(stub, frame, timestamp))
        else:
            pending_tasks.append((frame, timestamp))

    total = len(frames)
    print(
        f"\nAnalyzing behavior in {total} frames "
        f"({len(pending_tasks)} pending, {len(visual_observations)} from checkpoint, "
        f"{retry_count} retrying failed stubs)..."
    )
    print(f"Estimated incremental cost: ${len(pending_tasks) * 0.015:.2f}")

    analyzer._parallel_request_delay = max(0.0, float(request_delay_sec))
    try:
        ckpt_lock = threading.Lock()

        def _run_behavior(fr: Path, ts: float) -> VisualBehaviorObservation:
            obs = analyzer.analyze_frame_behavior(fr, ts)
            if checkpoint_path:
                payload = {"frame_id": obs.frame_id, "observation": asdict(obs)}
                with ckpt_lock:
                    with open(checkpoint_path, "a", encoding="utf-8") as cf:
                        cf.write(json.dumps(payload, default=str) + "\n")
            return obs

        if pending_tasks:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_run_behavior, fr, ts): fr for fr, ts in pending_tasks}
                completed = 0
                for future in as_completed(futures):
                    completed += 1
                    visual_observations.append(future.result())
                    if completed % 10 == 0 or completed == len(pending_tasks):
                        print(f"  Progress: {completed}/{len(pending_tasks)} pending")
    finally:
        analyzer._parallel_request_delay = 0.0
    
    visual_observations.sort(key=lambda x: x.timestamp_sec)
    
    # Analyze transcript if provided. Prefer the structured `transcript_obj`
    # path when both are supplied so observations get real timestamps.
    verbal_observations = None
    if transcript_obj is not None:
        print("\nAnalyzing transcript (structured) for verbal behavior...")
        verbal_observations = analyzer.analyze_transcript_behavior(
            transcript_obj=transcript_obj
        )
        analyzer.result.transcription_backend = str(
            getattr(transcript_obj, "backend", "") or ""
        )
        analyzer.result.transcription_model = str(
            getattr(transcript_obj, "model_id", "") or ""
        )
    elif transcript:
        print("\nAnalyzing transcript (string) for verbal behavior...")
        verbal_observations = analyzer.analyze_transcript_behavior(transcript)
    
    # Compile results
    print("\nCompiling behavior analysis...")
    result = analyzer.compile_behavior_results(visual_observations, verbal_observations)
    
    # Generate report
    report = analyzer.generate_behavior_report()
    print("\n" + report)
    
    # Save results
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        with open(output_path / "behavior_analysis.json", 'w') as f:
            json.dump(asdict(result), f, indent=2, default=str)
        
        with open(output_path / "behavior_report.txt", 'w') as f:
            f.write(report)
        
        print(f"\nResults saved to: {output_dir}")
    
    return result
