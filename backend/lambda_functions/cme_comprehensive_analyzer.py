"""
CME COMPREHENSIVE ANALYZER - Full Video + Audio Analysis
========================================================

Analyzes EVERYTHING in a CME examination:

VIDEO ANALYSIS:
- Patient attire (gown vs clothes)
- Tests performed and technique
- Equipment usage
- Doctor's attention/eye contact
- Body language
- Rushing indicators
- Dismissive behavior

AUDIO/SENTIMENT ANALYSIS:
- Tone of voice (condescending, dismissive, professional)
- Interrupting patient
- Ignoring patient concerns
- Rude or inappropriate comments
- Empathy indicators
- Time listening vs talking
- Rushing patient

TIMING ANALYSIS:
- Actual exam duration
- Time per test category
- Comparison to claimed time

Cost: ~$3-5 per case (video + audio analysis)
"""

import base64
import json
import subprocess
import tempfile
import os
import threading
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, TYPE_CHECKING
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

from .cme_analysis_utils import (
    add_analyze_result_cost,
    total_video_duration_sec,
)
from .prompts.production import (
    AUDIO_ANALYSIS_PROMPT_TEMPLATE,
    AUDIO_ANALYSIS_PROMPT_VERSION,
    FRAME_ANALYSIS_PROMPT,
    TECHNIQUE_FRAME_PROMPT_VERSION,
)
from .vision_client import VisionClient, default_model_for, make_vision_client, resolve_provider

if TYPE_CHECKING:
    from .cme_transcription import Transcript


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"  
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class BehaviorIssue:
    """A detected behavioral or professionalism issue."""
    category: str  # "rudeness", "dismissiveness", "rushing", "inattention", etc.
    description: str
    timestamp_sec: float
    evidence: str
    severity: Severity
    helps_plaintiff: bool = True


@dataclass
class TechniqueIssue:
    """A detected technique/procedural issue."""
    category: str
    description: str
    timestamp_sec: float
    evidence: str
    severity: Severity
    standard_of_care: str  # What SHOULD have been done


@dataclass
class FrameAnalysis:
    """Complete analysis of a video frame."""
    frame_id: str
    timestamp_sec: float
    video_file: str
    
    # Patient
    patient_attire: str = ""
    patient_visible_distress: bool = False
    patient_trying_to_speak: bool = False
    
    # Test being performed
    test_type: str = ""
    test_details: str = ""
    body_region: str = ""
    
    # Technique
    technique_issues: List[str] = field(default_factory=list)
    equipment_visible: List[str] = field(default_factory=list)
    
    # Doctor behavior
    doctor_facing_patient: bool = True
    doctor_making_eye_contact: bool = False
    doctor_appears_rushed: bool = False
    doctor_dismissive_gesture: bool = False
    doctor_on_phone_or_distracted: bool = False
    
    # Notes
    notes: str = ""
    raw_response: str = ""

    visibility: str = ""
    occlusion_notes: str = ""
    confidence: float = 0.0
    technique_prompt_version: str = ""

    model_id: str = ""
    provider: str = ""


@dataclass
class AudioSegmentAnalysis:
    """Analysis of an audio segment.

    `start_sec` / `end_sec` are `Optional[float]` because the legacy
    string-only transcript path has no real timing information to attach.
    The structured `transcript_obj` path populates them from real
    `TranscriptSegment` boundaries; the string fallback path leaves them
    as `None`.
    """
    segment_id: str
    start_sec: Optional[float]
    end_sec: Optional[float]
    
    # Speaker identification
    speaker: str = ""  # "doctor", "patient", "unknown"
    
    # Content
    transcript: str = ""
    
    # Sentiment/Tone
    tone: str = ""  # "professional", "condescending", "dismissive", "empathetic", "rushed", "rude"
    sentiment_score: float = 0.0  # -1 to 1 (negative to positive)
    
    # Behavior flags
    interrupting: bool = False
    dismissing_concern: bool = False
    rude_comment: bool = False
    showing_empathy: bool = False
    rushing_patient: bool = False
    ignoring_question: bool = False
    inappropriate_comment: bool = False
    
    # Evidence
    problematic_quotes: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class CMEComprehensiveResult:
    """Complete analysis result."""
    case_id: str = ""
    plaintiff_name: str = ""
    examiner_name: str = ""
    exam_date: str = ""
    
    # Timing
    total_video_duration_sec: float = 0
    claimed_exam_time_min: float = 30
    actual_hands_on_exam_sec: float = 0
    
    # Counts
    total_frames_analyzed: int = 0
    total_audio_segments: int = 0
    
    # Patient attire
    patient_wore_gown: bool = False
    attire_details: str = ""
    
    # Tests
    tests_performed: Dict[str, int] = field(default_factory=dict)
    tests_missed: List[str] = field(default_factory=list)
    
    # Equipment
    equipment_observed: List[str] = field(default_factory=list)
    equipment_missing: List[str] = field(default_factory=list)
    
    # Issues
    technique_issues: List[Dict] = field(default_factory=list)
    behavior_issues: List[Dict] = field(default_factory=list)
    
    # Sentiment summary
    overall_tone: str = ""
    doctor_empathy_score: float = 0.0  # 0-10
    doctor_professionalism_score: float = 0.0  # 0-10
    patient_concerns_addressed: int = 0
    patient_concerns_dismissed: int = 0
    interruption_count: int = 0
    rude_comment_count: int = 0
    
    # Key quotes
    problematic_quotes: List[Dict] = field(default_factory=list)
    
    # Claim comparisons
    claim_vs_reality: List[Dict] = field(default_factory=list)
    
    # Summary scores
    examination_quality_score: float = 0.0  # 0-100
    professionalism_score: float = 0.0  # 0-100
    
    # Cost
    total_cost_usd: float = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    model_used: str = ""

    technique_prompt_version: str = ""
    audio_prompt_version: str = ""

    # ASR provenance (populated when a structured Transcript is fed
    # through `analyze_cme_comprehensive(..., transcript_obj=...)`).
    # Empty strings when the legacy string-transcript path is used or
    # when no transcript was supplied.
    transcription_backend: str = ""
    transcription_model: str = ""

    # Per-claim verdicts from cme_claim_verifier. Populated by
    # analyze_cme_comprehensive AFTER both vision passes have written
    # their JSON; compile_results itself no longer touches claims so the
    # comprehensive pass remains responsible only for what it can observe.
    claim_verdicts: List[Dict] = field(default_factory=list)


class CMEComprehensiveAnalyzer:
    """
    Comprehensive CME analyzer - video, audio, behavior, everything.
    """
    
    COST_PER_FRAME = 0.005  # OpenAI default frame pass
    COST_PER_AUDIO_SEGMENT = 0.01
    
    def __init__(
        self,
        api_key: str = None,
        model: str = None,
        vision_client: Optional[VisionClient] = None,
    ):
        """Initialize analyzer.

        When `vision_client` is not provided, builds the configured default
        provider client (OpenAI unless CME_VISION_PROVIDER overrides it). When
        provided, the caller controls the vendor. All model calls route through
        `self.vision_client`, so no raw vendor SDK is instantiated here.
        """
        provider = resolve_provider()
        self.api_key = api_key
        self.model = model or default_model_for(provider)

        if vision_client is None:
            self.vision_client: VisionClient = make_vision_client(
                provider, api_key=self.api_key, model_id=self.model
            )
        else:
            self.vision_client = vision_client

        self.result = CMEComprehensiveResult()
        self.result.model_used = getattr(self.vision_client, "default_model_id", "") or self.model
        self.result.technique_prompt_version = TECHNIQUE_FRAME_PROMPT_VERSION
        self.result.audio_prompt_version = AUDIO_ANALYSIS_PROMPT_VERSION
        self._parallel_request_delay = 0.0
        # When set by analyze_cme_comprehensive, raw model output per frame
        # is externalized to {raw_output_dir}/{frame_id}.txt and the
        # FrameAnalysis.raw_response field stores the relative path instead
        # of the inline text. Older checkpoints that have inline raw text
        # remain valid; the field type is unchanged.
        self._raw_output_dir: Optional[Path] = None
        
    def extract_frames(self, video_paths: List[str], output_dir: str,
                      interval_sec: float = 5.0,
                      max_frame_width: Optional[int] = None) -> List[Path]:
        """Extract frames from videos."""
        frames_dir = Path(output_dir) / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        
        all_frames = []
        fps = 1 / interval_sec
        vf_parts = [f'fps={fps}']
        if max_frame_width and max_frame_width > 0:
            vf_parts.append(f"scale=min(iw\\,{max_frame_width}):-2")
        vf = ','.join(vf_parts)
        
        for i, video_path in enumerate(video_paths):
            print(f"Extracting frames from video {i+1}...")
            
            # Get duration
            result = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', video_path
            ], capture_output=True, text=True)
            
            try:
                duration = float(result.stdout.strip())
                self.result.total_video_duration_sec += duration
                print(f"  Duration: {duration:.0f}s ({duration/60:.1f} min)")
            except:
                pass
            
            # Extract frames
            output_pattern = str(frames_dir / f'video{i+1}_frame_%04d.jpg')
            subprocess.run([
                'ffmpeg', '-i', video_path, '-vf', vf, '-q:v', '2',
                output_pattern, '-y', '-loglevel', 'error'
            ])
            
            frames = sorted(frames_dir.glob(f'video{i+1}_frame_*.jpg'))
            print(f"  Extracted {len(frames)} frames")
            all_frames.extend(frames)
            
        return all_frames
    
    def extract_audio(self, video_paths: List[str], output_dir: str) -> List[Path]:
        """Extract audio from videos."""
        audio_dir = Path(output_dir) / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        
        audio_files = []
        
        for i, video_path in enumerate(video_paths):
            print(f"Extracting audio from video {i+1}...")
            output_path = audio_dir / f"video{i+1}_audio.mp3"
            
            subprocess.run([
                'ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame',
                '-q:a', '2', str(output_path), '-y', '-loglevel', 'error'
            ])
            
            if output_path.exists():
                audio_files.append(output_path)
                print(f"  Saved: {output_path.name}")
                
        return audio_files
    
    def transcribe_audio(self, audio_paths: List[str], output_dir: str) -> str:
        """Transcribe audio using AWS Transcribe or Whisper."""
        # For now, return existing transcript if available
        # In production, would use AWS Transcribe
        transcript_path = Path(output_dir) / "transcript.txt"
        
        if transcript_path.exists():
            return transcript_path.read_text()
        
        # Use local whisper if available
        try:
            import whisper
            model = whisper.load_model("base")
            
            full_transcript = ""
            for audio_path in audio_paths:
                result = model.transcribe(str(audio_path))
                full_transcript += result["text"] + "\n\n"
            
            transcript_path.write_text(full_transcript)
            return full_transcript
            
        except ImportError:
            print("Whisper not installed - using existing transcript if available")
            return ""
    
    def analyze_frame(self, frame_path: Path, interval_sec: float = 5.0) -> FrameAnalysis:
        """Analyze a single frame via the configured VisionClient."""
        delay = getattr(self, "_parallel_request_delay", 0.0) or 0.0
        if delay > 0:
            time.sleep(delay)

        parts = frame_path.stem.split('_')
        video_name = parts[0]
        frame_num = int(parts[-1])
        timestamp = (frame_num - 1) * interval_sec

        with open(frame_path, 'rb') as f:
            image_bytes = f.read()

        provider = getattr(self.vision_client, "provider", "")
        default_model_id = getattr(self.vision_client, "default_model_id", "") or self.model

        try:
            result = self.vision_client.analyze(
                image_bytes,
                FRAME_ANALYSIS_PROMPT,
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

            stored_raw = raw_full
            raw_dir = getattr(self, "_raw_output_dir", None)
            if raw_dir is not None:
                try:
                    Path(raw_dir).mkdir(parents=True, exist_ok=True)
                    raw_path = Path(raw_dir) / f"{frame_path.stem}.txt"
                    raw_path.write_text(raw_full, encoding="utf-8")
                    stored_raw = f"raw/{frame_path.stem}.txt"
                except OSError:
                    pass

            try:
                conf = float(data.get("confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                conf = 0.0
            analysis = FrameAnalysis(
                frame_id=frame_path.stem,
                timestamp_sec=timestamp,
                video_file=video_name,
                patient_attire=data.get('patient_attire', ''),
                patient_visible_distress=data.get('patient_visible_distress', False),
                patient_trying_to_speak=data.get('patient_trying_to_speak', False),
                test_type=data.get('test_type', ''),
                test_details=data.get('test_details', ''),
                body_region=data.get('body_region', ''),
                technique_issues=data.get('technique_issues', []),
                equipment_visible=data.get('equipment_visible', []),
                doctor_facing_patient=data.get('doctor_facing_patient', True),
                doctor_making_eye_contact=data.get('doctor_making_eye_contact', False),
                doctor_appears_rushed=data.get('doctor_appears_rushed', False),
                doctor_dismissive_gesture=data.get('doctor_dismissive_gesture', False),
                doctor_on_phone_or_distracted=data.get('doctor_on_phone_or_distracted', False),
                notes=data.get('notes', ''),
                raw_response=stored_raw,
                visibility=str(data.get("visibility", "") or ""),
                occlusion_notes=str(data.get("occlusion_notes", "") or ""),
                confidence=conf,
                technique_prompt_version=TECHNIQUE_FRAME_PROMPT_VERSION,
                model_id=result.model_id or default_model_id,
                provider=result.provider or provider,
            )

            return analysis

        except Exception as e:
            print(f"Error analyzing frame {frame_path.name}: {e}")
            return FrameAnalysis(
                frame_id=frame_path.stem,
                timestamp_sec=timestamp,
                video_file=video_name,
                technique_prompt_version=TECHNIQUE_FRAME_PROMPT_VERSION,
                model_id=default_model_id,
                provider=provider,
            )
    
    def analyze_transcript_segment(
        self,
        transcript: Optional[str] = None,
        start_sec: float = 0,
        *,
        transcript_obj: Optional["Transcript"] = None,
    ) -> List[AudioSegmentAnalysis]:
        """Analyze transcript for sentiment and behavior.

        Structured path (`transcript_obj`): chunks are built from real
        `TranscriptSegment` boundaries, grouped until ~500 words OR a
        30-second span, whichever first. Each chunk carries honest
        `start_sec` / `end_sec`. String path: legacy 500-word chunking,
        `start_sec` / `end_sec` left as `None` rather than synthesized.

        Routes through VisionClient.text_analyze so the transcript pass
        can run under any supported provider (Anthropic / OpenAI / Gemini).
        """
        if transcript_obj is None and not transcript:
            return []

        chunks = self._build_audio_chunks(transcript_obj, transcript)
        analyses: List[AudioSegmentAnalysis] = []

        for i, chunk in enumerate(chunks):
            print(f"  Analyzing transcript segment {i+1}/{len(chunks)}...")

            try:
                prompt = AUDIO_ANALYSIS_PROMPT_TEMPLATE.format(transcript=chunk["text"])
                result = self.vision_client.text_analyze(prompt, max_tokens=2000)
                raw = getattr(result, "text", "") or getattr(result, "raw_text", "") or ""
                add_analyze_result_cost(
                    self.result, result, fallback_usd=self.COST_PER_AUDIO_SEGMENT
                )

                try:
                    if "```json" in raw:
                        raw = raw.split("```json")[1].split("```")[0]
                    elif "```" in raw:
                        raw = raw.split("```")[1].split("```")[0]
                    data = json.loads(raw.strip())
                except Exception:
                    data = {}

                for seg in data.get('segments', []):
                    analysis = AudioSegmentAnalysis(
                        segment_id=f"seg_{i}_{len(analyses)}",
                        start_sec=chunk.get("start_sec"),
                        end_sec=chunk.get("end_sec"),
                        speaker=seg.get('speaker', ''),
                        transcript=seg.get('text', ''),
                        tone=seg.get('tone', ''),
                        sentiment_score=seg.get('sentiment_score', 0),
                        interrupting=seg.get('issues', {}).get('interrupting', False),
                        dismissing_concern=seg.get('issues', {}).get('dismissing_concern', False),
                        rude_comment=seg.get('issues', {}).get('rude_comment', False),
                        showing_empathy=seg.get('issues', {}).get('showing_empathy', False),
                        rushing_patient=seg.get('issues', {}).get('rushing_patient', False),
                        ignoring_question=seg.get('issues', {}).get('ignoring_question', False),
                        inappropriate_comment=seg.get('issues', {}).get('inappropriate_comment', False),
                        problematic_quotes=[seg.get('problematic_quote', '')] if seg.get('problematic_quote') else [],
                        notes=seg.get('notes', '')
                    )
                    analyses.append(analysis)

                for quote in data.get('helpful_for_plaintiff', []):
                    self.result.problematic_quotes.append({
                        'quote': quote,
                        'segment': i,
                        'type': 'helpful_for_plaintiff'
                    })

            except Exception as e:
                print(f"Error analyzing transcript segment: {e}")

        return analyses

    @staticmethod
    def _build_audio_chunks(
        transcript_obj: Optional["Transcript"],
        transcript: Optional[str],
    ) -> List[Dict]:
        """Group transcript content into chunks for the audio/sentiment pass.

        Structured path: ~500 word windows over real
        `TranscriptSegment` boundaries, capped at 30-second spans. Each
        chunk records honest start/end seconds from the first/last word.
        String path: legacy 500-word slicing, start/end set to `None`.
        """
        MAX_WORDS = 500
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
            chunk_size = 500
            for i in range(0, len(words), chunk_size):
                chunks.append(
                    {
                        "text": " ".join(words[i:i + chunk_size]),
                        "start_sec": None,
                        "end_sec": None,
                    }
                )
        return chunks
    
    def _load_frame_checkpoint(self, path: Path) -> Dict[str, dict]:
        """Load NDJSON checkpoint lines keyed by frame_id."""
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
                    done[fid] = row.get("analysis") or row
            except json.JSONDecodeError:
                continue
        return done

    def _frame_from_checkpoint_dict(self, d: dict, frame_path: Path, interval_sec: float) -> FrameAnalysis:
        """Rehydrate FrameAnalysis from checkpoint dict."""
        parts = frame_path.stem.split('_')
        video_name = parts[0]
        frame_num = int(parts[-1])
        ts = (frame_num - 1) * interval_sec
        try:
            try:
                conf = float(d.get("confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                conf = 0.0
            return FrameAnalysis(
                frame_id=d.get("frame_id", frame_path.stem),
                timestamp_sec=float(d.get("timestamp_sec", ts)),
                video_file=d.get("video_file", video_name),
                patient_attire=d.get("patient_attire", ""),
                patient_visible_distress=bool(d.get("patient_visible_distress", False)),
                patient_trying_to_speak=bool(d.get("patient_trying_to_speak", False)),
                test_type=d.get("test_type", ""),
                test_details=d.get("test_details", ""),
                body_region=d.get("body_region", ""),
                technique_issues=list(d.get("technique_issues") or []),
                equipment_visible=list(d.get("equipment_visible") or []),
                doctor_facing_patient=bool(d.get("doctor_facing_patient", True)),
                doctor_making_eye_contact=bool(d.get("doctor_making_eye_contact", False)),
                doctor_appears_rushed=bool(d.get("doctor_appears_rushed", False)),
                doctor_dismissive_gesture=bool(d.get("doctor_dismissive_gesture", False)),
                doctor_on_phone_or_distracted=bool(d.get("doctor_on_phone_or_distracted", False)),
                notes=d.get("notes", ""),
                raw_response=d.get("raw_response", ""),
                visibility=str(d.get("visibility", "") or ""),
                occlusion_notes=str(d.get("occlusion_notes", "") or ""),
                confidence=conf,
                technique_prompt_version=str(
                    d.get("technique_prompt_version", TECHNIQUE_FRAME_PROMPT_VERSION) or ""
                ),
                model_id=str(d.get("model_id", "") or ""),
                provider=str(d.get("provider", "") or ""),
            )
        except Exception:
            return FrameAnalysis(frame_id=frame_path.stem, timestamp_sec=ts, video_file=video_name)

    def analyze_frames_parallel(
        self,
        frames: List[Path],
        max_workers: int = 5,
        interval_sec: float = 5.0,
        checkpoint_path: Optional[Path] = None,
        resume: bool = False,
        request_delay_sec: float = 0.0,
    ) -> List[FrameAnalysis]:
        """Analyze frames in parallel with optional NDJSON checkpoint and resume."""
        self._parallel_request_delay = max(0.0, float(request_delay_sec))
        try:
            loaded: Dict[str, dict] = {}
            if resume and checkpoint_path:
                loaded = self._load_frame_checkpoint(checkpoint_path)

            analyses: List[FrameAnalysis] = []
            pending: List[Path] = []

            def _checkpoint_has_model_output(stub: dict) -> bool:
                """False for API-failure placeholders (no text came back from the model)."""
                if not isinstance(stub, dict):
                    return False
                return bool(str(stub.get("raw_response") or "").strip())

            for f in frames:
                if f.stem in loaded:
                    stub = loaded[f.stem]
                    if resume and not _checkpoint_has_model_output(stub):
                        pending.append(f)
                    else:
                        analyses.append(self._frame_from_checkpoint_dict(stub, f, interval_sec))
                else:
                    pending.append(f)

            total = len(frames)
            print(f"\nAnalyzing {total} frames ({len(pending)} pending, {len(analyses)} from checkpoint)...")
            print(f"Estimated incremental video analysis cost: ${len(pending) * self.COST_PER_FRAME:.2f}")

            ckpt_lock = threading.Lock()

            def _run_one(fp: Path) -> FrameAnalysis:
                result = self.analyze_frame(fp, interval_sec)
                if checkpoint_path:
                    payload = {"frame_id": result.frame_id, "analysis": asdict(result)}
                    with ckpt_lock:
                        with open(checkpoint_path, "a", encoding="utf-8") as cf:
                            cf.write(json.dumps(payload, default=str) + "\n")
                return result

            if pending:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(_run_one, p): p for p in pending}
                    completed = 0
                    for future in as_completed(futures):
                        completed += 1
                        analyses.append(future.result())
                        if completed % 10 == 0 or completed == len(pending):
                            print(f"  Progress: {completed}/{len(pending)} pending")

            analyses.sort(key=lambda x: (x.video_file, x.timestamp_sec))
            return analyses
        finally:
            self._parallel_request_delay = 0.0
    
    def compile_results(self, frame_analyses: List[FrameAnalysis],
                       audio_analyses: List[AudioSegmentAnalysis] = None,
                       report_claims: Dict[str, str] = None,
                       frame_interval_sec: float = 5.0):
        """Compile all analyses into final result."""
        
        self.result.total_frames_analyzed = len(frame_analyses)
        
        # Patient attire
        gown_count = sum(1 for a in frame_analyses if a.patient_attire == 'gown')
        clothes_count = sum(1 for a in frame_analyses if a.patient_attire == 'regular_clothes')
        self.result.patient_wore_gown = gown_count > clothes_count
        
        attire_details = [a.notes for a in frame_analyses if 'shirt' in a.notes.lower() or 'pants' in a.notes.lower()]
        if attire_details:
            self.result.attire_details = attire_details[0]
        
        # Tests performed
        for a in frame_analyses:
            if a.test_type and a.test_type not in ['none', 'conversation', '']:
                self.result.tests_performed[a.test_type] = \
                    self.result.tests_performed.get(a.test_type, 0) + 1
        
        # Technique issues
        issue_set = {}
        for a in frame_analyses:
            for issue in a.technique_issues:
                if issue and issue not in issue_set:
                    issue_set[issue] = {
                        'issue': issue,
                        'timestamp_sec': a.timestamp_sec,
                        'frame': a.frame_id,
                        'severity': 'high' if 'clothing' in issue or 'goniometer' in issue else 'medium'
                    }
        self.result.technique_issues = list(issue_set.values())
        
        # Behavior issues from video
        behavior_issues = []
        
        # Check for doctor not paying attention
        not_facing = [a for a in frame_analyses if not a.doctor_facing_patient]
        if len(not_facing) > 3:
            behavior_issues.append({
                'category': 'inattention',
                'description': f'Doctor not facing patient in {len(not_facing)} frames',
                'severity': 'medium',
                'timestamps': [a.timestamp_sec for a in not_facing[:5]]
            })
        
        # Check for rushing
        rushed = [a for a in frame_analyses if a.doctor_appears_rushed]
        if rushed:
            behavior_issues.append({
                'category': 'rushing',
                'description': f'Doctor appeared rushed in {len(rushed)} frames',
                'severity': 'medium',
                'timestamps': [a.timestamp_sec for a in rushed[:5]]
            })
        
        # Check for dismissive behavior
        dismissive = [a for a in frame_analyses if a.doctor_dismissive_gesture]
        if dismissive:
            behavior_issues.append({
                'category': 'dismissiveness',
                'description': f'Dismissive gestures observed in {len(dismissive)} frames',
                'severity': 'high',
                'timestamps': [a.timestamp_sec for a in dismissive[:5]]
            })
        
        # Check for patient distress
        distress = [a for a in frame_analyses if a.patient_visible_distress]
        if distress:
            behavior_issues.append({
                'category': 'patient_distress',
                'description': f'Patient showed visible distress in {len(distress)} frames',
                'severity': 'high',
                'timestamps': [a.timestamp_sec for a in distress[:5]],
                'helps_plaintiff': True
            })
        
        # Audio analysis results
        if audio_analyses:
            self.result.total_audio_segments = len(audio_analyses)
            
            # Count issues
            self.result.interruption_count = sum(1 for a in audio_analyses if a.interrupting)
            self.result.rude_comment_count = sum(1 for a in audio_analyses if a.rude_comment)
            self.result.patient_concerns_dismissed = sum(1 for a in audio_analyses if a.dismissing_concern)
            
            # Collect problematic quotes
            for a in audio_analyses:
                for quote in a.problematic_quotes:
                    if quote:
                        self.result.problematic_quotes.append({
                            'quote': quote,
                            'timestamp_sec': a.start_sec,
                            'tone': a.tone,
                            'type': 'rude' if a.rude_comment else 'dismissive' if a.dismissing_concern else 'other'
                        })
            
            # Add audio-based behavior issues
            if self.result.interruption_count > 2:
                behavior_issues.append({
                    'category': 'interrupting',
                    'description': f'Doctor interrupted patient {self.result.interruption_count} times',
                    'severity': 'high'
                })
            
            if self.result.rude_comment_count > 0:
                behavior_issues.append({
                    'category': 'rudeness',
                    'description': f'{self.result.rude_comment_count} rude or inappropriate comments',
                    'severity': 'critical'
                })
            
            if self.result.patient_concerns_dismissed > 0:
                behavior_issues.append({
                    'category': 'dismissiveness',
                    'description': f'Dismissed {self.result.patient_concerns_dismissed} patient concerns',
                    'severity': 'high'
                })
            
            # Calculate empathy/professionalism scores
            empathy_indicators = sum(1 for a in audio_analyses if a.showing_empathy)
            negative_indicators = (self.result.interruption_count + 
                                 self.result.rude_comment_count + 
                                 self.result.patient_concerns_dismissed)
            
            total_segments = len(audio_analyses) or 1
            self.result.doctor_empathy_score = min(10, (empathy_indicators / total_segments) * 20)
            self.result.doctor_professionalism_score = max(0, 10 - (negative_indicators / total_segments) * 10)
        
        self.result.behavior_issues = behavior_issues
        
        # Equipment
        equipment_set = set()
        for a in frame_analyses:
            for eq in a.equipment_visible:
                equipment_set.add(eq)
        self.result.equipment_observed = list(equipment_set)
        
        expected = {'reflex_hammer', 'goniometer', 'sensory_pin', 'tape_measure'}
        self.result.equipment_missing = list(expected - equipment_set)
        
        # Exam duration estimate
        exam_frames = sum(1 for a in frame_analyses if a.test_type not in ['none', 'conversation', ''])
        self.result.actual_hands_on_exam_sec = exam_frames * frame_interval_sec

        # Note: claim verification has moved out of compile_results into a
        # dedicated stage executed by analyze_cme_comprehensive AFTER both
        # vision passes complete and comprehensive_frame_analyses.json is
        # written. See backend.lambda_functions.cme_claim_verifier.
        # The legacy `_compare_claims` method below is intentionally kept
        # in place as a fallback path; it is no longer called on the main
        # flow.
        _ = report_claims  # kept for signature compatibility

        # Calculate overall scores
        technique_penalty = len(self.result.technique_issues) * 10
        behavior_penalty = sum(20 if b['severity'] == 'critical' else 10 if b['severity'] == 'high' else 5 
                              for b in behavior_issues)
        
        self.result.examination_quality_score = max(0, 100 - technique_penalty)
        self.result.professionalism_score = max(0, 100 - behavior_penalty)
        
        return self.result
    
    def _compare_claims(self, claims: Dict[str, str]):
        """Legacy hardcoded claim comparison (kept as a fallback path; the
        main flow now uses cme_claim_verifier.verify_all_claims instead)."""
        
        # Exam time
        if 'exam_time' in claims:
            actual_min = self.result.total_video_duration_sec / 60
            if actual_min < 15:  # Less than half of typical 30 min claim
                self.result.claim_vs_reality.append({
                    'claim': claims['exam_time'],
                    'observation': f'Video shows only {actual_min:.1f} minutes',
                    'issue': 'TIME_DISCREPANCY',
                    'severity': 'high'
                })
        
        # Cranial nerves
        if 'cranial_nerves' in claims:
            cn_count = self.result.tests_performed.get('cranial_nerve', 0)
            if cn_count == 0:
                self.result.claim_vs_reality.append({
                    'claim': claims['cranial_nerves'],
                    'observation': 'NO cranial nerve testing observed',
                    'issue': 'CLAIM_NOT_SUPPORTED',
                    'severity': 'critical'
                })
        
        # Strength
        if 'strength' in claims and '5/5' in claims['strength']:
            strength_count = self.result.tests_performed.get('strength', 0)
            if strength_count < 15:
                self.result.claim_vs_reality.append({
                    'claim': claims['strength'],
                    'observation': f'Only {strength_count} strength test frames (incomplete)',
                    'issue': 'INCOMPLETE_TESTING',
                    'severity': 'high'
                })
        
        # ROM
        if 'rom' in claims:
            if 'goniometer' not in self.result.equipment_observed:
                self.result.claim_vs_reality.append({
                    'claim': claims['rom'],
                    'observation': 'No goniometer visible - not objectively measured',
                    'issue': 'NO_OBJECTIVE_MEASUREMENT',
                    'severity': 'high'
                })
        
        # Romberg
        if 'romberg' in claims:
            romberg_issues = [i for i in self.result.technique_issues if 'romberg' in i['issue'].lower()]
            if romberg_issues:
                self.result.claim_vs_reality.append({
                    'claim': claims['romberg'],
                    'observation': 'Non-standard Romberg technique',
                    'issue': 'IMPROPER_TECHNIQUE',
                    'severity': 'medium'
                })
        
        # Attire/sensory
        if not self.result.patient_wore_gown:
            clothing_issues = [i for i in self.result.technique_issues if 'clothing' in i['issue'].lower()]
            if clothing_issues:
                self.result.claim_vs_reality.append({
                    'claim': 'Sensory examination',
                    'observation': 'Patient not in gown - tested through clothing',
                    'issue': 'TESTING_THROUGH_CLOTHING',
                    'severity': 'high'
                })
    
    def generate_report(self) -> str:
        """Generate comprehensive human-readable report."""
        r = self.result
        
        lines = [
            "=" * 80,
            "COMPREHENSIVE CME ANALYSIS REPORT",
            "=" * 80,
            "",
            f"Plaintiff: {r.plaintiff_name}",
            f"Examiner: {r.examiner_name}",
            f"Date: {r.exam_date}",
            f"Analysis Cost: ${r.total_cost_usd:.2f}",
            "",
            "=" * 80,
            "SUMMARY SCORES",
            "=" * 80,
            f"Examination Quality:  {r.examination_quality_score:.0f}/100",
            f"Professionalism:      {r.professionalism_score:.0f}/100",
            f"Empathy Score:        {r.doctor_empathy_score:.1f}/10",
            "",
            "=" * 80,
            "TIMING",
            "=" * 80,
            f"Total Video Duration: {r.total_video_duration_sec:.0f}s ({r.total_video_duration_sec/60:.1f} min)",
            f"Claimed Exam Time: {r.claimed_exam_time_min} minutes",
            f"Actual Hands-On Exam: ~{r.actual_hands_on_exam_sec:.0f}s ({r.actual_hands_on_exam_sec/60:.1f} min)",
        ]
        
        if r.total_video_duration_sec < r.claimed_exam_time_min * 30:  # Less than half
            lines.append(f"⚠️  SIGNIFICANT TIME DISCREPANCY")
        
        lines.extend([
            "",
            "=" * 80,
            "PATIENT ATTIRE",
            "=" * 80,
            f"Wore Examination Gown: {'YES' if r.patient_wore_gown else 'NO ⚠️'}",
        ])
        if r.attire_details:
            lines.append(f"Details: {r.attire_details}")
        
        lines.extend([
            "",
            "=" * 80,
            "TESTS PERFORMED",
            "=" * 80,
        ])
        for test, count in sorted(r.tests_performed.items()):
            lines.append(f"  {test}: {count} frames")
        
        lines.extend([
            "",
            "=" * 80,
            "EQUIPMENT",
            "=" * 80,
            f"Observed: {', '.join(r.equipment_observed) or 'None'}",
            f"Missing: {', '.join(r.equipment_missing) or 'None'}",
        ])
        
        if r.technique_issues:
            lines.extend([
                "",
                "=" * 80,
                "TECHNIQUE ISSUES",
                "=" * 80,
            ])
            for issue in r.technique_issues:
                sev = "🔴" if issue['severity'] == 'critical' else "🟡" if issue['severity'] == 'high' else "⚪"
                lines.append(f"  {sev} {issue['issue'].replace('_', ' ').upper()}")
                lines.append(f"     At: {issue['timestamp_sec']:.0f}s")
        
        if r.behavior_issues:
            lines.extend([
                "",
                "=" * 80,
                "BEHAVIOR / PROFESSIONALISM ISSUES",
                "=" * 80,
            ])
            for issue in r.behavior_issues:
                sev = "🔴" if issue['severity'] == 'critical' else "🟡" if issue['severity'] == 'high' else "⚪"
                lines.append(f"  {sev} {issue['category'].upper()}: {issue['description']}")
        
        if r.problematic_quotes:
            lines.extend([
                "",
                "=" * 80,
                "PROBLEMATIC QUOTES",
                "=" * 80,
            ])
            for q in r.problematic_quotes[:10]:  # Top 10
                lines.append(f"  \"{q['quote']}\"")
                lines.append(f"     Type: {q.get('type', 'other')}")
                lines.append("")
        
        if r.claim_vs_reality:
            lines.extend([
                "",
                "=" * 80,
                "CLAIM VS REALITY",
                "=" * 80,
            ])
            for cvr in r.claim_vs_reality:
                sev = "🔴" if cvr['severity'] == 'critical' else "🟡" if cvr['severity'] == 'high' else "⚪"
                lines.append(f"  {sev} CLAIM: {cvr['claim']}")
                lines.append(f"     REALITY: {cvr['observation']}")
                lines.append("")
        
        # Summary stats
        lines.extend([
            "",
            "=" * 80,
            "STATISTICS",
            "=" * 80,
            f"Frames Analyzed: {r.total_frames_analyzed}",
            f"Audio Segments: {r.total_audio_segments}",
            f"Technique Issues: {len(r.technique_issues)}",
            f"Behavior Issues: {len(r.behavior_issues)}",
            f"Claim Discrepancies: {len(r.claim_vs_reality)}",
        ])
        
        if r.interruption_count or r.rude_comment_count:
            lines.extend([
                f"Interruptions: {r.interruption_count}",
                f"Rude Comments: {r.rude_comment_count}",
                f"Concerns Dismissed: {r.patient_concerns_dismissed}",
            ])
        
        return "\n".join(lines)


def analyze_cme_comprehensive(
    video_paths: List[str],
    transcript: str = None,
    report_claims: Dict[str, str] = None,
    plaintiff_name: str = None,
    examiner_name: str = None,
    exam_date: str = None,
    api_key: str = None,
    output_dir: str = None,
    frame_interval: float = 5.0,
    frames_dir: Optional[str] = None,
    max_frame_width: Optional[int] = None,
    max_workers: int = 5,
    request_delay_sec: float = 0.0,
    resume: bool = False,
    model: str = None,
    vision_client: Optional[VisionClient] = None,
    transcript_obj: Optional["Transcript"] = None,
) -> CMEComprehensiveResult:
    """
    Run comprehensive CME analysis.
    
    Args:
        video_paths: List of video files (duration; extraction if frames_dir not set)
        transcript: Optional transcript text (will extract if not provided)
        report_claims: Dict of claims from doctor's report
        plaintiff_name: Plaintiff name
        examiner_name: Examiner name  
        exam_date: Exam date
        api_key: Provider API key
        output_dir: Output directory
        frame_interval: Seconds between frames
        frames_dir: Pre-extracted JPEG directory (skips ffmpeg in this module)
        max_frame_width: Scale extracted frames to max width (cost/quality tradeoff)
        max_workers: Parallel workers for vision API
        request_delay_sec: Delay per frame request (429 mitigation)
        resume: Continue from comprehensive_checkpoint.jsonl in output_dir
        model: Provider model id
        
    Returns:
        CMEComprehensiveResult with all findings
    """
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="cme_analysis_")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Initialize
    analyzer = CMEComprehensiveAnalyzer(
        api_key=api_key, model=model, vision_client=vision_client
    )
    analyzer.result.plaintiff_name = plaintiff_name or ""
    analyzer.result.examiner_name = examiner_name or ""
    analyzer.result.exam_date = exam_date or ""
    
    # Extract and analyze frames
    print("\n" + "=" * 60)
    print("PHASE 1: VIDEO FRAME ANALYSIS")
    print("=" * 60)
    
    if frames_dir:
        analyzer.result.total_video_duration_sec = total_video_duration_sec(video_paths)
        frames = sorted(Path(frames_dir).glob("*.jpg"))
        print(f"Using {len(frames)} pre-extracted frames from {frames_dir}")
    else:
        frames = analyzer.extract_frames(
            video_paths, str(output_path), frame_interval, max_frame_width=max_frame_width
        )

    # Raw model output externalization: per-frame raw text lands in
    # comprehensive/raw/{frame_id}.txt; FrameAnalysis.raw_response stores
    # the relative path "raw/{frame_id}.txt" for the provenance bundle.
    raw_output_dir = output_path / "raw"
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    analyzer._raw_output_dir = raw_output_dir

    checkpoint_path = output_path / "comprehensive_checkpoint.jsonl"
    if resume:
        print(f"Resume enabled; checkpoint: {checkpoint_path}")
    else:
        if checkpoint_path.exists():
            checkpoint_path.unlink()

    frame_analyses = analyzer.analyze_frames_parallel(
        frames,
        max_workers=max_workers,
        interval_sec=frame_interval,
        checkpoint_path=checkpoint_path,
        resume=resume,
        request_delay_sec=request_delay_sec,
    )

    frames_json = output_path / "comprehensive_frame_analyses.json"
    with open(frames_json, "w", encoding="utf-8") as fj:
        json.dump([asdict(a) for a in frame_analyses], fj, indent=2, default=str)
    print(f"Per-frame analyses saved to {frames_json}")
    
    # Analyze transcript if provided. Prefer structured `transcript_obj`
    # so segment timestamps come from real ASR boundaries.
    audio_analyses = None
    if transcript_obj is not None:
        print("\n" + "=" * 60)
        print("PHASE 2: AUDIO/SENTIMENT ANALYSIS (structured transcript)")
        print("=" * 60)
        audio_analyses = analyzer.analyze_transcript_segment(
            transcript_obj=transcript_obj
        )
        analyzer.result.transcription_backend = str(
            getattr(transcript_obj, "backend", "") or ""
        )
        analyzer.result.transcription_model = str(
            getattr(transcript_obj, "model_id", "") or ""
        )
    elif transcript:
        print("\n" + "=" * 60)
        print("PHASE 2: AUDIO/SENTIMENT ANALYSIS (string transcript)")
        print("=" * 60)
        audio_analyses = analyzer.analyze_transcript_segment(transcript)
    
    # Compile results
    print("\n" + "=" * 60)
    print("PHASE 3: COMPILING RESULTS")
    print("=" * 60)
    
    result = analyzer.compile_results(
        frame_analyses, audio_analyses, report_claims, frame_interval_sec=frame_interval
    )

    # Per-claim verifier: runs AFTER both vision passes have completed and
    # the per-frame JSON has been written, but before the final
    # comprehensive_analysis.json dump so claim_verdicts are stored
    # alongside the rest of the result. Behavior observations are not
    # available in this single-pass entrypoint; analyze_cme_full re-runs
    # the verifier with the merged behavior+verbal observations included.
    # Only invoked when claims are supplied so vanilla runs without a
    # claims file produce no new artifacts.
    if report_claims:
        from .cme_claim_verifier import verify_all_claims

        verdicts = verify_all_claims(
            claims=report_claims,
            frame_analyses=frame_analyses,
            behavior_observations=[],
            verbal_observations=audio_analyses or [],
            vision_client=analyzer.vision_client,
            output_dir=output_path,
            max_workers=max_workers,
        )
        analyzer.result.claim_verdicts = [asdict(v) for v in verdicts]
        print(
            f"Claim verifier produced {len(verdicts)} verdicts -> "
            f"{output_path / 'claim_verdicts.json'}"
        )

    # Generate report
    report = analyzer.generate_report()
    print("\n" + report)
    
    # Save results
    results_path = output_path / "comprehensive_analysis.json"
    with open(results_path, 'w') as f:
        json.dump(asdict(result), f, indent=2, default=str)
    print(f"\nResults saved to: {results_path}")
    
    report_path = output_path / "analysis_report.txt"
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"Report saved to: {report_path}")
    
    return result
