"""
CME VISION ANALYZER - Production Video Analysis with AI Vision
==============================================================

Uses Claude Vision API for comprehensive frame-by-frame CME video analysis.

Cost: ~$1.50 per CME case (100 frames @ $0.015/frame with Sonnet)

Features:
- Automatic frame extraction from any video format
- AI-powered analysis of each frame
- Detection of technique errors, equipment, patient attire
- Comparison against report claims
- Comprehensive findings report
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
import time

from .vision_client import VisionClient, make_vision_client


class AnalysisModel(Enum):
    """Available vision models."""
    HAIKU = "claude-3-haiku-20240307"      # Fast, cheap (~$0.005/frame)
    SONNET = "claude-3-sonnet-20240229"    # Balanced (~$0.015/frame)
    OPUS = "claude-3-opus-20240229"        # Best quality (~$0.075/frame)


@dataclass
class FrameAnalysis:
    """Structured analysis of a single video frame."""
    frame_id: str
    timestamp_sec: float
    video_file: str
    
    # Patient
    patient_attire: str = ""  # "gown", "regular_clothes", "partial"
    attire_details: str = ""
    
    # Test being performed
    test_type: str = ""  # strength, sensory, reflex, rom, gait, coordination, romberg, palpation, cranial_nerve, none
    test_details: str = ""
    body_region: str = ""
    
    # Technique assessment
    technique_issues: List[str] = field(default_factory=list)
    
    # Equipment
    equipment_visible: List[str] = field(default_factory=list)
    
    # Additional observations
    notes: str = ""
    confidence: float = 0.0
    raw_response: str = ""


@dataclass  
class CMEVideoAnalysisResult:
    """Complete analysis result for CME video(s)."""
    case_id: str = ""
    plaintiff_name: str = ""
    examiner_name: str = ""
    exam_date: str = ""
    
    # Timing
    total_video_duration_sec: float = 0
    estimated_exam_duration_sec: float = 0
    
    # Frames
    total_frames_analyzed: int = 0
    frames: List[FrameAnalysis] = field(default_factory=list)
    
    # Summary findings
    patient_wore_gown: bool = False
    attire_summary: str = ""
    
    tests_performed: Dict[str, int] = field(default_factory=dict)
    technique_issues_found: List[Dict] = field(default_factory=list)
    equipment_observed: List[str] = field(default_factory=list)
    equipment_missing: List[str] = field(default_factory=list)
    
    # Claim comparisons
    claim_vs_reality: List[Dict] = field(default_factory=list)
    
    # Cost tracking
    total_cost_usd: float = 0
    model_used: str = ""


# Analysis prompt for each frame
FRAME_ANALYSIS_PROMPT = """Analyze this frame from a Compulsory Medical Examination (CME) video for a legal case.

Provide your analysis in this EXACT JSON format:
{
    "patient_attire": "gown" or "regular_clothes" or "partial" or "unknown",
    "attire_details": "description of what patient is wearing",
    "test_type": "strength" or "sensory" or "reflex" or "rom" or "gait" or "coordination" or "romberg" or "palpation" or "cranial_nerve" or "conversation" or "none",
    "test_details": "specific description of test being performed",
    "body_region": "neck/shoulder/arm/hand/back/hip/leg/foot/full_body/face/none",
    "technique_issues": ["list of issues observed"],
    "equipment_visible": ["list: reflex_hammer, goniometer, inclinometer, sensory_pin, tuning_fork, tape_measure, etc"],
    "notes": "any other relevant observations",
    "confidence": 0.0 to 1.0
}

TECHNIQUE ISSUES to look for:
- "testing_through_clothing" - sensory/palpation done over clothes instead of bare skin
- "no_measurement_device" - ROM testing without goniometer/inclinometer
- "improper_romberg" - Romberg with arms outstretched (should be at sides) or too brief
- "patient_not_in_gown" - patient wearing street clothes for neurological exam
- "incomplete_dermatome" - sensory testing skipping dermatomes
- "no_reflex_hammer" - reflex claims without visible hammer

Be precise and factual. Only report what you can clearly observe.
Return ONLY the JSON object, no other text."""


class CMEVisionAnalyzer:
    """
    Production CME video analyzer using Claude Vision API.
    """
    
    # Cost per image (approximate, in USD)
    COST_PER_IMAGE = {
        AnalysisModel.HAIKU: 0.005,
        AnalysisModel.SONNET: 0.015,
        AnalysisModel.OPUS: 0.075
    }
    
    def __init__(
        self,
        api_key: str = None,
        model: AnalysisModel = AnalysisModel.SONNET,
        vision_client: Optional[VisionClient] = None,
    ):
        """
        Initialize the analyzer.

        Args:
            api_key: Anthropic API key (or set ANTHROPIC_API_KEY env var)
            model: Which Claude model to use for vision analysis
            vision_client: Optional pre-built VisionClient (alt provider)
        """
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        self.model = model
        if vision_client is None:
            if not self.api_key:
                raise ValueError(
                    "Anthropic API key required. Set ANTHROPIC_API_KEY or pass api_key parameter."
                )
            self.vision_client: VisionClient = make_vision_client(
                "anthropic", api_key=self.api_key, model_id=model.value
            )
        else:
            self.vision_client = vision_client
        self.result = CMEVideoAnalysisResult()
        self.result.model_used = model.value
        
    def extract_frames(self, video_paths: List[str], output_dir: str = None,
                      frame_interval_sec: float = 5.0) -> List[Path]:
        """
        Extract frames from video files.
        
        Args:
            video_paths: List of video file paths
            output_dir: Directory to save frames (default: temp dir)
            frame_interval_sec: Seconds between frame extractions (default: 5)
            
        Returns:
            List of frame file paths
        """
        if output_dir:
            frames_dir = Path(output_dir)
            frames_dir.mkdir(exist_ok=True)
        else:
            frames_dir = Path(tempfile.mkdtemp(prefix="cme_frames_"))
            
        all_frames = []
        fps = 1 / frame_interval_sec
        
        for i, video_path in enumerate(video_paths):
            video_name = f"video{i+1}"
            print(f"Extracting frames from {Path(video_path).name}...")
            
            # Get video duration
            result = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', video_path
            ], capture_output=True, text=True)
            
            try:
                duration = float(result.stdout.strip())
                self.result.total_video_duration_sec += duration
                print(f"  Duration: {duration:.1f} seconds")
            except:
                print(f"  Warning: Could not determine duration")
            
            # Extract frames
            output_pattern = str(frames_dir / f'{video_name}_frame_%04d.jpg')
            subprocess.run([
                'ffmpeg', '-i', video_path, '-vf', f'fps={fps}', '-q:v', '2',
                output_pattern, '-y', '-loglevel', 'error'
            ], capture_output=True)
            
            # Collect frame paths
            frames = sorted(frames_dir.glob(f'{video_name}_frame_*.jpg'))
            print(f"  Extracted {len(frames)} frames")
            all_frames.extend(frames)
            
        return all_frames
    
    def analyze_frame(self, frame_path: Path, frame_interval_sec: float = 5.0) -> FrameAnalysis:
        """
        Analyze a single frame using Claude Vision.
        
        Args:
            frame_path: Path to frame image
            frame_interval_sec: Seconds between frames (for timestamp calculation)
            
        Returns:
            FrameAnalysis object
        """
        # Parse frame info from filename
        parts = frame_path.stem.split('_')
        video_name = parts[0]
        frame_num = int(parts[-1])
        timestamp = (frame_num - 1) * frame_interval_sec
        
        with open(frame_path, 'rb') as f:
            image_bytes = f.read()

        try:
            result = self.vision_client.analyze(
                image_bytes,
                FRAME_ANALYSIS_PROMPT,
                max_tokens=1000,
                mime_type="image/jpeg",
            )
            raw_response = getattr(result, "text", "") or getattr(result, "raw_text", "") or ""
            
            # Parse JSON response
            try:
                # Handle potential markdown code blocks
                if "```json" in raw_response:
                    raw_response = raw_response.split("```json")[1].split("```")[0]
                elif "```" in raw_response:
                    raw_response = raw_response.split("```")[1].split("```")[0]
                    
                data = json.loads(raw_response.strip())
            except json.JSONDecodeError:
                data = {}
            
            analysis = FrameAnalysis(
                frame_id=frame_path.stem,
                timestamp_sec=timestamp,
                video_file=video_name,
                patient_attire=data.get('patient_attire', 'unknown'),
                attire_details=data.get('attire_details', ''),
                test_type=data.get('test_type', 'unknown'),
                test_details=data.get('test_details', ''),
                body_region=data.get('body_region', ''),
                technique_issues=data.get('technique_issues', []),
                equipment_visible=data.get('equipment_visible', []),
                notes=data.get('notes', ''),
                confidence=data.get('confidence', 0.5),
                raw_response=raw_response
            )
            
            # Track cost
            self.result.total_cost_usd += self.COST_PER_IMAGE[self.model]
            
            return analysis
            
        except Exception as e:
            print(f"Error analyzing {frame_path.name}: {e}")
            return FrameAnalysis(
                frame_id=frame_path.stem,
                timestamp_sec=timestamp,
                video_file=video_name,
                notes=f"Analysis failed: {str(e)}"
            )
    
    def analyze_frames_parallel(self, frame_paths: List[Path], 
                               max_workers: int = 5,
                               frame_interval_sec: float = 5.0) -> List[FrameAnalysis]:
        """
        Analyze multiple frames in parallel.
        
        Args:
            frame_paths: List of frame paths to analyze
            max_workers: Number of parallel API calls
            frame_interval_sec: Seconds between frames
            
        Returns:
            List of FrameAnalysis objects
        """
        analyses = []
        total = len(frame_paths)
        
        print(f"\nAnalyzing {total} frames with {self.model.value}...")
        print(f"Estimated cost: ${total * self.COST_PER_IMAGE[self.model]:.2f}")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.analyze_frame, path, frame_interval_sec): path 
                for path in frame_paths
            }
            
            completed = 0
            for future in as_completed(futures):
                completed += 1
                analysis = future.result()
                analyses.append(analysis)
                
                if completed % 10 == 0 or completed == total:
                    print(f"  Progress: {completed}/{total} frames analyzed (${self.result.total_cost_usd:.2f})")
        
        # Sort by timestamp
        analyses.sort(key=lambda x: (x.video_file, x.timestamp_sec))
        
        return analyses
    
    def compile_results(self, analyses: List[FrameAnalysis],
                       report_claims: Dict[str, str] = None) -> CMEVideoAnalysisResult:
        """
        Compile frame analyses into comprehensive result.
        
        Args:
            analyses: List of frame analyses
            report_claims: Optional dict of claims from doctor's report
            
        Returns:
            CMEVideoAnalysisResult
        """
        self.result.total_frames_analyzed = len(analyses)
        self.result.frames = analyses
        
        # Determine patient attire
        gown_count = sum(1 for a in analyses if a.patient_attire == 'gown')
        clothes_count = sum(1 for a in analyses if a.patient_attire == 'regular_clothes')
        
        self.result.patient_wore_gown = gown_count > clothes_count
        
        attire_details = [a.attire_details for a in analyses if a.attire_details]
        if attire_details:
            self.result.attire_summary = attire_details[0]
        
        # Count tests performed
        for a in analyses:
            if a.test_type and a.test_type not in ['none', 'unknown', 'conversation']:
                self.result.tests_performed[a.test_type] = \
                    self.result.tests_performed.get(a.test_type, 0) + 1
        
        # Collect technique issues
        issue_set = {}
        for a in analyses:
            for issue in a.technique_issues:
                if issue and issue not in issue_set:
                    issue_set[issue] = {
                        'issue': issue,
                        'first_seen_at': a.timestamp_sec,
                        'frame': a.frame_id
                    }
        self.result.technique_issues_found = list(issue_set.values())
        
        # Collect equipment
        equipment_set = set()
        for a in analyses:
            for eq in a.equipment_visible:
                if eq:
                    equipment_set.add(eq)
        self.result.equipment_observed = list(equipment_set)
        
        # Determine missing equipment
        expected = {'reflex_hammer', 'goniometer', 'sensory_pin', 'tape_measure'}
        self.result.equipment_missing = list(expected - equipment_set)
        
        # Estimate actual exam duration (frames with actual testing)
        exam_frames = sum(1 for a in analyses 
                        if a.test_type not in ['none', 'unknown', 'conversation', ''])
        self.result.estimated_exam_duration_sec = exam_frames * 5
        
        # Compare against claims if provided
        if report_claims:
            self._compare_claims(report_claims, analyses)
        
        return self.result
    
    def _compare_claims(self, claims: Dict[str, str], analyses: List[FrameAnalysis]):
        """Compare video observations against report claims."""
        
        # Check cranial nerve claim
        if 'cranial_nerves' in claims:
            cn_frames = [a for a in analyses if a.test_type == 'cranial_nerve']
            if len(cn_frames) == 0:
                self.result.claim_vs_reality.append({
                    'claim': claims['cranial_nerves'],
                    'observation': 'NO cranial nerve testing observed in video',
                    'issue': 'CLAIM_NOT_SUPPORTED',
                    'severity': 'critical'
                })
        
        # Check strength claim
        if 'strength' in claims and '5/5' in claims['strength']:
            strength_frames = [a for a in analyses if a.test_type == 'strength']
            if len(strength_frames) < 15:  # Should see many for "throughout"
                self.result.claim_vs_reality.append({
                    'claim': claims['strength'],
                    'observation': f'Only {len(strength_frames)} strength test frames observed',
                    'issue': 'INCOMPLETE_TESTING',
                    'severity': 'high'
                })
        
        # Check ROM claim
        if 'rom' in claims:
            if 'goniometer' not in self.result.equipment_observed and \
               'inclinometer' not in self.result.equipment_observed:
                self.result.claim_vs_reality.append({
                    'claim': claims['rom'],
                    'observation': 'No goniometer/inclinometer visible - ROM not objectively measured',
                    'issue': 'NO_OBJECTIVE_MEASUREMENT',
                    'severity': 'high'
                })
        
        # Check Romberg claim
        if 'romberg' in claims:
            romberg_issues = [i for i in self.result.technique_issues_found 
                           if 'romberg' in i['issue'].lower()]
            if romberg_issues:
                self.result.claim_vs_reality.append({
                    'claim': claims['romberg'],
                    'observation': 'Romberg test performed with non-standard technique',
                    'issue': 'IMPROPER_TECHNIQUE',
                    'severity': 'medium'
                })
        
        # Check attire and sensory
        if not self.result.patient_wore_gown:
            clothing_issues = [i for i in self.result.technique_issues_found
                            if 'clothing' in i['issue'].lower()]
            if clothing_issues:
                self.result.claim_vs_reality.append({
                    'claim': 'Sensory examination performed',
                    'observation': 'Patient not in gown - sensory testing through clothing observed',
                    'issue': 'TESTING_THROUGH_CLOTHING',
                    'severity': 'high'
                })
        
        # Check exam time
        if 'exam_time' in claims:
            claimed_min = 30  # Extract from claim if possible
            actual_min = self.result.total_video_duration_sec / 60
            if actual_min < claimed_min * 0.5:
                self.result.claim_vs_reality.append({
                    'claim': claims['exam_time'],
                    'observation': f'Video shows only {actual_min:.1f} minutes of examination',
                    'issue': 'TIME_DISCREPANCY',
                    'severity': 'medium'
                })
    
    def generate_report(self) -> str:
        """Generate human-readable analysis report."""
        r = self.result
        
        lines = [
            "=" * 70,
            "CME VIDEO ANALYSIS REPORT - AI VISION VERIFIED",
            "=" * 70,
            "",
            f"Case: {r.plaintiff_name or 'Unknown'} | Examiner: {r.examiner_name or 'Unknown'}",
            f"Model: {r.model_used}",
            f"Analysis Cost: ${r.total_cost_usd:.2f}",
            "",
            f"Total Video Duration: {r.total_video_duration_sec:.0f}s ({r.total_video_duration_sec/60:.1f} min)",
            f"Estimated Exam Duration: {r.estimated_exam_duration_sec:.0f}s ({r.estimated_exam_duration_sec/60:.1f} min)",
            f"Frames Analyzed: {r.total_frames_analyzed}",
            "",
            "=" * 70,
            "PATIENT ATTIRE",
            "=" * 70,
            f"Wore Gown: {'YES' if r.patient_wore_gown else 'NO'}",
            f"Details: {r.attire_summary}",
        ]
        
        if not r.patient_wore_gown:
            lines.append("⚠️  ISSUE: Patient not in examination gown")
        
        lines.extend([
            "",
            "=" * 70,
            "TESTS OBSERVED",
            "=" * 70,
        ])
        
        for test_type, count in sorted(r.tests_performed.items()):
            lines.append(f"  {test_type}: {count} frames")
        
        lines.extend([
            "",
            "=" * 70,
            "EQUIPMENT",
            "=" * 70,
            f"Observed: {', '.join(r.equipment_observed) or 'None detected'}",
            f"Missing: {', '.join(r.equipment_missing) or 'None'}",
        ])
        
        if r.technique_issues_found:
            lines.extend([
                "",
                "=" * 70,
                "TECHNIQUE ISSUES",
                "=" * 70,
            ])
            for issue in r.technique_issues_found:
                lines.append(f"  🔴 {issue['issue'].replace('_', ' ').upper()}")
                lines.append(f"     First observed at: {issue['first_seen_at']:.0f}s")
        
        if r.claim_vs_reality:
            lines.extend([
                "",
                "=" * 70,
                "CLAIM VS REALITY",
                "=" * 70,
            ])
            for cvr in r.claim_vs_reality:
                sev = {"critical": "🔴", "high": "🟡", "medium": "⚪"}.get(cvr['severity'], "⚪")
                lines.append(f"  {sev} CLAIM: {cvr['claim']}")
                lines.append(f"     OBSERVED: {cvr['observation']}")
                lines.append("")
        
        return "\n".join(lines)
    
    def save_results(self, output_path: str):
        """Save results to JSON file."""
        data = {
            'case_id': self.result.case_id,
            'plaintiff_name': self.result.plaintiff_name,
            'examiner_name': self.result.examiner_name,
            'exam_date': self.result.exam_date,
            'total_video_duration_sec': self.result.total_video_duration_sec,
            'estimated_exam_duration_sec': self.result.estimated_exam_duration_sec,
            'total_frames_analyzed': self.result.total_frames_analyzed,
            'model_used': self.result.model_used,
            'total_cost_usd': self.result.total_cost_usd,
            'patient_wore_gown': self.result.patient_wore_gown,
            'attire_summary': self.result.attire_summary,
            'tests_performed': self.result.tests_performed,
            'technique_issues_found': self.result.technique_issues_found,
            'equipment_observed': self.result.equipment_observed,
            'equipment_missing': self.result.equipment_missing,
            'claim_vs_reality': self.result.claim_vs_reality,
            'frames': [asdict(f) for f in self.result.frames]
        }
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)


def analyze_cme_case(
    video_paths: List[str],
    report_claims: Dict[str, str] = None,
    plaintiff_name: str = None,
    examiner_name: str = None,
    exam_date: str = None,
    api_key: str = None,
    model: str = "sonnet",
    frame_interval: float = 5.0,
    output_dir: str = None
) -> CMEVideoAnalysisResult:
    """
    Complete CME video analysis pipeline.
    
    Args:
        video_paths: List of video file paths
        report_claims: Dict of claims from doctor's report
        plaintiff_name: Name of plaintiff
        examiner_name: Name of examining doctor
        exam_date: Date of examination
        api_key: Anthropic API key (or set ANTHROPIC_API_KEY env var)
        model: "haiku", "sonnet", or "opus"
        frame_interval: Seconds between frame extractions
        output_dir: Directory to save frames and results
        
    Returns:
        CMEVideoAnalysisResult with all findings
    """
    # Select model
    model_map = {
        "haiku": AnalysisModel.HAIKU,
        "sonnet": AnalysisModel.SONNET,
        "opus": AnalysisModel.OPUS
    }
    analysis_model = model_map.get(model.lower(), AnalysisModel.SONNET)
    
    # Initialize analyzer
    analyzer = CMEVisionAnalyzer(api_key=api_key, model=analysis_model)
    analyzer.result.plaintiff_name = plaintiff_name or ""
    analyzer.result.examiner_name = examiner_name or ""
    analyzer.result.exam_date = exam_date or ""
    
    # Extract frames
    frames = analyzer.extract_frames(video_paths, output_dir, frame_interval)
    
    # Analyze frames
    analyses = analyzer.analyze_frames_parallel(frames, max_workers=5, 
                                                frame_interval_sec=frame_interval)
    
    # Compile results
    result = analyzer.compile_results(analyses, report_claims)
    
    # Generate report
    print("\n" + analyzer.generate_report())
    
    # Save results if output_dir provided
    if output_dir:
        output_path = Path(output_dir) / "analysis_results.json"
        analyzer.save_results(str(output_path))
        print(f"\nResults saved to: {output_path}")
    
    return result


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="CME Video Analysis with AI Vision")
    parser.add_argument("videos", nargs="+", help="Video file paths")
    parser.add_argument("--plaintiff", help="Plaintiff name")
    parser.add_argument("--examiner", help="Examiner name")
    parser.add_argument("--date", help="Exam date")
    parser.add_argument("--model", default="sonnet", choices=["haiku", "sonnet", "opus"])
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between frames")
    parser.add_argument("--output", help="Output directory")
    parser.add_argument("--api-key", help="Anthropic API key")
    
    args = parser.parse_args()
    
    result = analyze_cme_case(
        video_paths=args.videos,
        plaintiff_name=args.plaintiff,
        examiner_name=args.examiner,
        exam_date=args.date,
        api_key=args.api_key,
        model=args.model,
        frame_interval=args.interval,
        output_dir=args.output
    )
    
    print(f"\nAnalysis complete. Total cost: ${result.total_cost_usd:.2f}")
