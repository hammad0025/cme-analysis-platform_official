#!/usr/bin/env python3
"""
CME FULL ANALYSIS - Complete Video + Audio + Behavior Analysis
==============================================================

This script runs EVERYTHING:
1. Video frame analysis (tests, technique, equipment)
2. Behavior analysis (eye contact, attention, body language)
3. Sentiment analysis (tone, rudeness, dismissiveness)
4. Claim vs Reality comparison

COST: Scales with video duration and --interval (dual vision passes). Use ~5s interval for typical cost; ~0.5s for high precision.
      Runs can cost $5–$50+ in API fees. Never run without reviewing the cost estimate below.
      For estimates over $5 you must pass --yes or --confirm-cost (no interactive default).

USAGE:
   python analyze_cme_full.py video1.mp4 video2.mov --plaintiff "Name" --examiner "Dr. Name"

With transcript for sentiment analysis:
   python analyze_cme_full.py video.mp4 --transcript transcript.txt

With claims to verify:
   python analyze_cme_full.py video.mp4 --claims claims.json
"""

import sys
import os
import json
import argparse
import tempfile
import subprocess
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.lambda_functions.cme_analysis_utils import (
    DEFAULT_AI_PROVIDER,
    DEFAULT_OPENAI_VISION_MODEL,
    DEFAULT_SONNET_MODEL,
    PRESET_INTERVALS,
    append_cost_history,
    estimate_full_analysis_cost_usd,
    median_cost_per_vision_call_usd,
    run_claim_verifier_with_merged_observations,
    write_cost_actual_json,
)
from backend.lambda_functions.cme_claim_verifier import CLAIM_VERIFIER_PROMPT_VERSION
from backend.lambda_functions.cme_provenance import (
    compute_bundle_hash,
    ffmpeg_version,
    file_sha256,
    iter_artifact_relpaths,
)
from backend.lambda_functions.cme_transcription import (
    TRANSCRIPTION_PROMPT_VERSION,
    transcribe,
)
from backend.lambda_functions.prompts.production import (
    AUDIO_ANALYSIS_PROMPT_VERSION,
    BEHAVIOR_VERBAL_PROMPT_VERSION,
    BEHAVIOR_VISUAL_PROMPT_VERSION,
    TECHNIQUE_FRAME_PROMPT_VERSION,
)
from backend.lambda_functions.vision_client import (
    SUPPORTED_PROVIDERS,
    VisionClientConfigError,
    default_model_for,
    make_vision_client,
)
from backend.lambda_functions.perplexity_client import PerplexityClient

ASR_BACKEND_CHOICES = ("auto", "faster-whisper", "openai-whisper-api", "none")

LARGE_RUN_THRESHOLD = 500
COST_CONFIRM_THRESHOLD_USD = 5.0
ALLOW_LOCAL_ENV = "CME_ALLOW_LOCAL_ANALYSIS"

PROVIDER_ENV_VAR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
}


def generate_html_report(comprehensive_result, behavior_result, output_path: str):
    """Generate a beautiful HTML report combining all results."""
    
    c = comprehensive_result
    b = behavior_result
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>CME Analysis Report - {c.plaintiff_name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e8e8e8;
            min-height: 100vh;
            padding: 2rem;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{
            text-align: center;
            padding: 2rem;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            margin-bottom: 2rem;
        }}
        h1 {{ font-size: 2.5rem; margin-bottom: 0.5rem; color: #fff; }}
        .subtitle {{ color: #888; font-size: 1.1rem; }}
        .case-info {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1rem;
            margin-top: 1rem;
        }}
        .case-info-item {{ background: rgba(255,255,255,0.05); padding: 1rem; border-radius: 8px; }}
        .case-info-item label {{ color: #888; font-size: 0.85rem; }}
        .case-info-item span {{ display: block; font-size: 1.1rem; color: #fff; margin-top: 0.25rem; }}
        
        .scores {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .score-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 1.5rem;
            text-align: center;
        }}
        .score-card.critical {{ border: 2px solid #ef4444; background: rgba(239,68,68,0.1); }}
        .score-card.warning {{ border: 2px solid #f59e0b; background: rgba(245,158,11,0.1); }}
        .score-card.good {{ border: 2px solid #22c55e; background: rgba(34,197,94,0.1); }}
        .score-value {{ font-size: 2.5rem; font-weight: 700; margin-bottom: 0.5rem; }}
        .score-label {{ color: #888; font-size: 0.9rem; }}
        
        .section {{
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }}
        .section h2 {{
            font-size: 1.3rem;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        
        .issue {{ 
            padding: 1rem;
            margin-bottom: 0.75rem;
            border-radius: 8px;
            background: rgba(0,0,0,0.2);
        }}
        .issue.critical {{ border-left: 4px solid #ef4444; }}
        .issue.high {{ border-left: 4px solid #f59e0b; }}
        .issue.medium {{ border-left: 4px solid #3b82f6; }}
        .issue-category {{ font-weight: 600; color: #fff; }}
        .issue-description {{ color: #aaa; margin-top: 0.25rem; }}
        
        .quote {{
            background: rgba(0,0,0,0.3);
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 0.75rem;
            border-left: 4px solid #f59e0b;
        }}
        .quote-text {{ font-style: italic; color: #fff; margin-bottom: 0.5rem; }}
        .quote-context {{ color: #888; font-size: 0.85rem; }}
        
        .claim-comparison {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }}
        .claim, .reality {{
            padding: 1rem;
            border-radius: 8px;
        }}
        .claim {{ background: rgba(59,130,246,0.2); }}
        .reality {{ background: rgba(239,68,68,0.2); }}
        .claim-label, .reality-label {{
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 0.5rem;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        th {{ color: #888; font-weight: 500; }}
        
        .metric-bar {{
            height: 8px;
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
            overflow: hidden;
        }}
        .metric-bar-fill {{ height: 100%; border-radius: 4px; }}
        .metric-bar-fill.good {{ background: #22c55e; }}
        .metric-bar-fill.warning {{ background: #f59e0b; }}
        .metric-bar-fill.bad {{ background: #ef4444; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>CME Analysis Report</h1>
            <p class="subtitle">Comprehensive Video, Behavior & Sentiment Analysis</p>
            <div class="case-info">
                <div class="case-info-item">
                    <label>Plaintiff</label>
                    <span>{c.plaintiff_name}</span>
                </div>
                <div class="case-info-item">
                    <label>Examiner</label>
                    <span>{c.examiner_name}</span>
                </div>
                <div class="case-info-item">
                    <label>Exam Date</label>
                    <span>{c.exam_date}</span>
                </div>
            </div>
        </div>
        
        <div class="scores">
            <div class="score-card {'critical' if c.examination_quality_score < 50 else 'warning' if c.examination_quality_score < 75 else 'good'}">
                <div class="score-value">{c.examination_quality_score:.0f}</div>
                <div class="score-label">Exam Quality</div>
            </div>
            <div class="score-card {'critical' if c.professionalism_score < 50 else 'warning' if c.professionalism_score < 75 else 'good'}">
                <div class="score-value">{c.professionalism_score:.0f}</div>
                <div class="score-label">Professionalism</div>
            </div>
            <div class="score-card {'critical' if b.empathy_score < 3 else 'warning' if b.empathy_score < 6 else 'good'}">
                <div class="score-value">{b.empathy_score:.1f}</div>
                <div class="score-label">Empathy (0-10)</div>
            </div>
            <div class="score-card {'critical' if b.attention_score < 50 else 'warning' if b.attention_score < 75 else 'good'}">
                <div class="score-value">{b.attention_score:.0f}%</div>
                <div class="score-label">Attention</div>
            </div>
        </div>
        
        <div class="section">
            <h2>🕐 Examination Timing</h2>
            <table>
                <tr>
                    <td>Total Video Duration</td>
                    <td>{c.total_video_duration_sec/60:.1f} minutes</td>
                </tr>
                <tr>
                    <td>Claimed Exam Time</td>
                    <td>{c.claimed_exam_time_min} minutes</td>
                </tr>
                <tr>
                    <td>Actual Hands-On Exam</td>
                    <td>~{c.actual_hands_on_exam_sec/60:.1f} minutes</td>
                </tr>
            </table>
        </div>
        
        <div class="section">
            <h2>👔 Patient Attire</h2>
            <p><strong>Wore Examination Gown:</strong> {'YES ✅' if c.patient_wore_gown else 'NO ⚠️'}</p>
            {f'<p style="color: #aaa; margin-top: 0.5rem;">{c.attire_details}</p>' if c.attire_details else ''}
        </div>
        
        <div class="section">
            <h2>👁️ Doctor Behavior</h2>
            <table>
                <tr>
                    <td>Eye Contact</td>
                    <td>
                        <div class="metric-bar">
                            <div class="metric-bar-fill {'good' if b.eye_contact_score >= 70 else 'warning' if b.eye_contact_score >= 50 else 'bad'}" 
                                 style="width: {b.eye_contact_score}%"></div>
                        </div>
                        {b.eye_contact_score:.0f}% of time
                    </td>
                </tr>
                <tr>
                    <td>Attention to Patient</td>
                    <td>
                        <div class="metric-bar">
                            <div class="metric-bar-fill {'good' if b.attention_score >= 70 else 'warning' if b.attention_score >= 50 else 'bad'}" 
                                 style="width: {b.attention_score}%"></div>
                        </div>
                        {b.attention_score:.0f}% focused
                    </td>
                </tr>
                <tr>
                    <td>Overall Demeanor</td>
                    <td><strong style="color: {'#ef4444' if b.overall_demeanor in ['hostile', 'dismissive'] else '#f59e0b' if b.overall_demeanor in ['cold/clinical', 'rushed'] else '#22c55e'}">{b.overall_demeanor.upper()}</strong></td>
                </tr>
                <tr>
                    <td>Interruptions</td>
                    <td>{b.interruption_count}</td>
                </tr>
                <tr>
                    <td>Dismissive Instances</td>
                    <td>{b.dismissive_instances}</td>
                </tr>
                <tr>
                    <td>Rude/Condescending</td>
                    <td style="color: {'#ef4444' if b.rude_instances > 0 else 'inherit'}">{b.rude_instances}</td>
                </tr>
            </table>
        </div>
"""
    
    # Technique Issues
    if c.technique_issues:
        html += """
        <div class="section">
            <h2>⚠️ Technique Issues</h2>
"""
        for issue in c.technique_issues:
            sev = issue.get('severity', 'medium')
            html += f"""
            <div class="issue {sev}">
                <div class="issue-category">{issue.get('issue', '').replace('_', ' ').upper()}</div>
                <div class="issue-description">At {issue.get('timestamp_sec', 0):.0f}s</div>
            </div>
"""
        html += "</div>"
    
    # Behavior Issues
    if c.behavior_issues or b.behavior_issues:
        all_behavior = c.behavior_issues + b.behavior_issues
        html += """
        <div class="section">
            <h2>🚨 Behavior Issues</h2>
"""
        for issue in all_behavior:
            sev = issue.get('severity', {})
            if isinstance(sev, dict):
                sev = sev.get('value', 'medium')
            html += f"""
            <div class="issue {sev}">
                <div class="issue-category">{issue.get('category', '')}</div>
                <div class="issue-description">{issue.get('description', '')}</div>
            </div>
"""
        html += "</div>"
    
    # Problematic Quotes
    all_quotes = c.problematic_quotes + b.problematic_quotes
    if all_quotes:
        html += """
        <div class="section">
            <h2>💬 Problematic Quotes</h2>
"""
        for q in all_quotes[:10]:
            html += f"""
            <div class="quote">
                <div class="quote-text">"{q.get('quote', '')}"</div>
                <div class="quote-context">{q.get('type', q.get('problem', ''))}</div>
            </div>
"""
        html += "</div>"
    
    # Claim vs Reality
    if c.claim_vs_reality:
        html += """
        <div class="section">
            <h2>📋 Claim vs Reality</h2>
"""
        for cvr in c.claim_vs_reality:
            html += f"""
            <div style="margin-bottom: 1rem;">
                <div class="claim-comparison">
                    <div class="claim">
                        <div class="claim-label">Doctor's Claim</div>
                        {cvr.get('claim', '')}
                    </div>
                    <div class="reality">
                        <div class="reality-label">Video Evidence</div>
                        {cvr.get('observation', '')}
                    </div>
                </div>
            </div>
"""
        html += "</div>"
    
    # Footer
    html += f"""
        <div class="section" style="text-align: center; background: transparent;">
            <p style="color: #666;">Analysis generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
            <p style="color: #666;">Total cost: ${c.total_cost_usd + b.total_cost_usd:.2f}</p>
        </div>
    </div>
</body>
</html>
"""
    
    with open(output_path, 'w') as f:
        f.write(html)
    
    return output_path


def _str_to_bool(value):
    """argparse helper: accept true/false/yes/no/1/0 (case-insensitive)."""
    if isinstance(value, bool):
        return value
    s = str(value or "").strip().lower()
    if s in {"true", "t", "yes", "y", "1"}:
        return True
    if s in {"false", "f", "no", "n", "0"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected boolean value, got {value!r}")


def main():
    parser = argparse.ArgumentParser(
        description="CME Full Analysis - Video + Behavior + Sentiment",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("videos", nargs="+", help="Video file paths")
    parser.add_argument("--plaintiff", "-p", help="Plaintiff name")
    parser.add_argument("--examiner", "-e", help="Examiner name")
    parser.add_argument("--date", "-d", help="Exam date")
    parser.add_argument("--injury-date", help="Date of injury (standard report header)")
    parser.add_argument("--dob", help="Patient DOB (standard report header)")
    parser.add_argument("--transcript", "-t", help="Transcript file for sentiment analysis")
    parser.add_argument(
        "--transcript-json",
        help=(
            "Pre-existing normalized transcript.json (asdict of Transcript, e.g. "
            "converted AWS Transcribe output). Skips ASR and feeds the structured "
            "transcript into the behavior/verbal passes."
        ),
    )
    parser.add_argument(
        "--auto-transcribe",
        type=_str_to_bool,
        default=True,
        help=(
            "Auto-transcribe video audio with word-level timestamps when no "
            "--transcript is supplied. Skips with a clear log when no ASR "
            "backend is available. Default: true."
        ),
    )
    parser.add_argument(
        "--asr-backend",
        choices=list(ASR_BACKEND_CHOICES),
        default="auto",
        help=(
            "ASR backend selector. 'auto' prefers faster-whisper, falls "
            "back to OpenAI Whisper API when OPENAI_API_KEY is set. "
            "'none' disables transcription entirely."
        ),
    )
    parser.add_argument("--claims", "-c", help="JSON file with report claims to verify")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--interval", "-i", type=float, default=None,
                       help="Seconds between frames (default 5 or --preset)")
    parser.add_argument(
        "--preset",
        choices=list(PRESET_INTERVALS.keys()),
        default=None,
        help="standard=5s, high=1s, half_second|max=0.5s (if --interval omitted)",
    )
    parser.add_argument(
        "--max-frame-width",
        type=int,
        default=None,
        help="Max JPEG width when extracting (reduces vision token cost)",
    )
    parser.add_argument("--max-workers", type=int, default=5, help="Parallel API calls per pass")
    parser.add_argument(
        "--request-delay-sec",
        type=float,
        default=0.0,
        help="Sleep before each frame API call (429 mitigation)",
    )
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint JSONL")
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Primary-provider frame model "
            f"(default {DEFAULT_OPENAI_VISION_MODEL} for openai; "
            f"{DEFAULT_SONNET_MODEL} for anthropic)"
        ),
    )
    parser.add_argument(
        "--providers",
        default=DEFAULT_AI_PROVIDER,
        help=(
            "Comma-separated vision providers; first one is primary. "
            f"Supported: {','.join(SUPPORTED_PROVIDERS)}. Default: {DEFAULT_AI_PROVIDER}."
        ),
    )
    parser.add_argument(
        "--session-id",
        help="Live session id; timestamps in the standard report become deep-links to /sessions/{id}?t={sec}",
    )
    parser.add_argument(
        "--app-base-url",
        default=os.environ.get("CME_APP_BASE_URL", ""),
        help="Web app base URL for report deep-links (default: production Vercel app)",
    )
    parser.add_argument(
        "--report-format",
        choices=["default", "standard"],
        default="default",
        help="Also write STANDARD_CME_REPORT.html/pdf when standard",
    )
    parser.add_argument("--api-key", help="Primary-provider API key (overrides env)")
    parser.add_argument(
        "--with-research",
        type=_str_to_bool,
        default=None,
        help=(
            "Augment claim verification with Perplexity Sonar research on exam "
            "standards. Opt-in only (requires PERPLEXITY_API_KEY). Default: off."
        ),
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    parser.add_argument(
        "--confirm-cost",
        action="store_true",
        help=f"Acknowledge estimated cost and proceed (required when estimate exceeds ${COST_CONFIRM_THRESHOLD_USD:.0f})",
    )

    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent / ".env")
    except ImportError:
        pass

    if os.environ.get(ALLOW_LOCAL_ENV) != "1":
        print("\n" + "=" * 60)
        print("REFUSED: Local full analysis is disabled by default.")
        print("=" * 60)
        print(f"Set {ALLOW_LOCAL_ENV}=1 to enable (runs cost $5–$50+ in API fees).")
        print("Preview cost first: python scripts/estimate_cme_cost.py <video>")
        print("For estimates over $5 you must also pass --confirm-cost or --yes.")
        sys.exit(1)

    providers = [p.strip().lower() for p in (args.providers or DEFAULT_AI_PROVIDER).split(",") if p.strip()]
    if not providers:
        providers = [DEFAULT_AI_PROVIDER]
    for p in providers:
        if p not in SUPPORTED_PROVIDERS:
            print(f"ERROR: Unsupported provider {p!r}. Supported: {SUPPORTED_PROVIDERS}")
            sys.exit(1)
    primary_provider = providers[0]

    if args.interval is not None:
        frame_interval = args.interval
    elif args.preset:
        frame_interval = PRESET_INTERVALS[args.preset]
    else:
        frame_interval = 5.0

    primary_model = args.model or default_model_for(primary_provider)

    # API key check is per-primary-provider. OpenAI is the default provider;
    # Anthropic and Gemini remain explicit fallback choices.
    primary_env_var = PROVIDER_ENV_VAR[primary_provider]
    primary_api_key = args.api_key or os.environ.get(primary_env_var)
    if primary_provider == "gemini" and not primary_api_key:
        primary_api_key = os.environ.get("GEMINI_API_KEY")
    if not primary_api_key:
        print("\n" + "=" * 60)
        print(f"ERROR: {primary_provider} API key required!")
        print("=" * 60)
        if primary_provider == "anthropic":
            print("\nGet your key: https://console.anthropic.com/")
            print("\nThen run:")
            print("  export ANTHROPIC_API_KEY='sk-ant-...'")
            print("  python analyze_cme_full.py video.mp4")
        elif primary_provider == "openai":
            print("\nGet your key: https://platform.openai.com/api-keys")
            print("\nThen run:")
            print("  export OPENAI_API_KEY='sk-...'")
            print("  python analyze_cme_full.py video.mp4")
        else:
            print("\nGet your key: https://aistudio.google.com/apikey")
            print("\nThen run:")
            print("  export GOOGLE_API_KEY='...'")
            print("  python analyze_cme_full.py video.mp4 --providers gemini")
        sys.exit(1)

    # Backwards-compat: downstream analyzers still accept `api_key` named
    # after the Anthropic key. When primary is Anthropic this is unchanged.
    api_key = primary_api_key
    model = primary_model

    try:
        vision_client = make_vision_client(
            primary_provider, api_key=primary_api_key, model_id=primary_model
        )
    except VisionClientConfigError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    with_research = bool(args.with_research)
    research_client = PerplexityClient() if with_research else None
    if with_research and research_client is not None and not research_client.enabled:
        print(
            "Note: --with-research requested but PERPLEXITY_API_KEY is not set; "
            "claim verification will run without Perplexity."
        )
        research_client = None
    elif research_client is not None and research_client.enabled:
        print("Perplexity research: enabled for claim verification.")
    
    # Check videos exist
    for video in args.videos:
        if not os.path.exists(video):
            print(f"ERROR: Video not found: {video}")
            sys.exit(1)
    
    # Load transcript (string path, kept for back-compat).
    transcript = None
    if args.transcript and os.path.exists(args.transcript):
        with open(args.transcript) as f:
            transcript = f.read()

    # Whether auto-transcription will be attempted. The structured
    # Transcript object is built later (after output_dir is materialized);
    # this banner-level flag is what the run summary prints.
    auto_transcribe_enabled = bool(args.auto_transcribe) and args.asr_backend != "none"
    if transcript is not None:
        # User supplied a transcript explicitly; do not auto-transcribe.
        auto_transcribe_enabled = False
    
    # Load claims
    claims = None
    claims_path = None
    if args.claims and os.path.exists(args.claims):
        claims_path = Path(args.claims)
        with open(claims_path) as f:
            claims = json.load(f)
    
    est = estimate_full_analysis_cost_usd(
        args.videos,
        frame_interval,
        dual_vision_pass=True,
        transcript_word_count=len(transcript.split()) if transcript else 0,
    )
    api_calls = est["vision_api_calls"]
    total_cost_est = est["estimated_total_usd"]
    
    print("\n" + "=" * 60)
    print("CME FULL ANALYSIS")
    print("=" * 60)
    print(f"Videos: {len(args.videos)}")
    print(f"Frame interval: {frame_interval}s")
    print(f"Estimated frames: {est['estimated_frames']}")
    print(f"Vision API calls (2 passes): {api_calls}")
    print(f"Total video duration: {est['total_duration_sec']:.0f}s ({est['total_duration_sec']/60:.1f} min)")
    print(f"Plaintiff: {args.plaintiff or 'Not specified'}")
    print(f"Examiner: {args.examiner or 'Not specified'}")
    print(f"Providers: {', '.join(providers)} (primary: {primary_provider})")
    print(f"Primary model: {primary_model}")
    if len(providers) > 1:
        print(
            "Note: secondary providers are accepted but not yet wired into the "
            "vision passes (roadmap step 2). Only the primary provider is called."
        )
    print(f"Transcript: {'Yes' if transcript else 'No'}")
    print(
        f"Auto-transcribe: {'On' if auto_transcribe_enabled else 'Off'} "
        f"(backend={args.asr_backend})"
    )
    print("")
    print("WHAT WILL BE ANALYZED:")
    print("  ✓ Video frames (tests, technique, equipment)")
    print("  ✓ Doctor behavior (eye contact, attention, body language)")
    print("  ✓ Professionalism (rushing, dismissiveness, gestures)")
    if transcript:
        print("  ✓ Sentiment analysis (tone, rudeness, empathy)")
    if claims:
        print("  ✓ Claim verification")
    print("")
    print(f"ESTIMATED COST: ~${total_cost_est:.2f} (heuristic; actual uses token usage when available)")
    hist_med = median_cost_per_vision_call_usd()
    if hist_med is not None:
        print(
            f"Rolling median from prior runs: ~${hist_med:.4f} per vision call "
            "(use to sanity-check the heuristic)."
        )
    if api_calls > LARGE_RUN_THRESHOLD:
        print("")
        print("WARNING: Large run. Consider --request-delay-sec 0.25–1.0 and/or lower --max-workers.")
    print("=" * 60)
    
    if total_cost_est > COST_CONFIRM_THRESHOLD_USD:
        if not (args.yes or args.confirm_cost):
            print(
                f"\nREFUSED: Estimated cost ${total_cost_est:.2f} exceeds "
                f"${COST_CONFIRM_THRESHOLD_USD:.0f}."
            )
            print("Re-run with --yes or --confirm-cost only if you accept this spend.")
            sys.exit(1)
    elif not (args.yes or args.confirm_cost):
        if not sys.stdin.isatty():
            print(
                "\nREFUSED: Non-interactive runs require --yes or --confirm-cost."
            )
            sys.exit(1)
        response = input("\nProceed? [y/N]: ")
        if response.lower() != 'y':
            print("Cancelled.")
            sys.exit(0)

    wall_t0 = time.perf_counter()
    run_id = uuid.uuid4().hex
    run_created_at = datetime.now(timezone.utc).isoformat()

    # Setup output directory
    output_dir = args.output or tempfile.mkdtemp(prefix="cme_full_analysis_")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Extract frames once
    print("\n" + "=" * 60)
    print("PHASE 1: EXTRACTING FRAMES")
    print("=" * 60)
    
    frames_dir = output_path / "frames"
    frames_dir.mkdir(exist_ok=True)
    
    fps = 1 / frame_interval
    vf_parts = [f'fps={fps}']
    if args.max_frame_width and args.max_frame_width > 0:
        vf_parts.append(f"scale=min(iw\\,{args.max_frame_width}):-2")
    vf = ','.join(vf_parts)
    all_frames = []
    total_duration = 0.0
    
    for i, video in enumerate(args.videos):
        print(f"Extracting from video {i+1}: {video}")
        
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', video
        ], capture_output=True, text=True)
        
        try:
            duration = float(result.stdout.strip())
            total_duration += duration
            print(f"  Duration: {duration:.0f}s ({duration/60:.1f} min)")
        except Exception:
            pass
        
        output_pattern = str(frames_dir / f'video{i+1}_frame_%04d.jpg')
        subprocess.run([
            'ffmpeg', '-i', video, '-vf', vf, '-q:v', '2',
            output_pattern, '-y', '-loglevel', 'error'
        ])
        
        frames = sorted(frames_dir.glob(f'video{i+1}_frame_*.jpg'))
        print(f"  Extracted {len(frames)} frames")
        all_frames.extend(frames)
    
    print(f"\nTotal: {len(all_frames)} frames from {total_duration/60:.1f} min of video")
    video_len_str = f"{int(total_duration // 60)}:{int(total_duration % 60):02d}"

    # Optional auto-transcription pass. Runs BEFORE the comprehensive +
    # behavior passes so the structured Transcript can be fed into both.
    # Degrades gracefully when no ASR backend is available: the
    # transcribe() helper prints a clear skip message and returns None,
    # leaving the visual-only pipeline functional. The default flow
    # (only ANTHROPIC_API_KEY set, no faster-whisper installed) hits
    # this skip path and proceeds exactly as it did pre-A3.
    transcript_obj = None
    if args.transcript_json and os.path.exists(args.transcript_json):
        from backend.lambda_functions.cme_transcription import transcript_from_dict

        print("\n" + "=" * 60)
        print("PHASE 1b: REUSING EXISTING TRANSCRIPT")
        print("=" * 60)
        with open(args.transcript_json) as f:
            transcript_obj = transcript_from_dict(json.load(f))
        print(
            f"Loaded {transcript_obj.word_count} words across "
            f"{len(transcript_obj.segments)} segments from {args.transcript_json} "
            f"(backend={transcript_obj.backend})"
        )
        if transcript is None:
            transcript = "\n".join(
                (seg.text or "").strip() for seg in transcript_obj.segments
            ).strip()
        # Persist the standard audio artifacts alongside the run when
        # they are not already under <output>/audio.
        audio_dir = output_path / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        src = Path(args.transcript_json).resolve()
        dest = (audio_dir / "transcript.json").resolve()
        if src != dest:
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        txt_dest = audio_dir / "transcript.txt"
        if not txt_dest.exists():
            txt_dest.write_text(transcript + "\n", encoding="utf-8")
        auto_transcribe_enabled = False
    elif auto_transcribe_enabled:
        print("\n" + "=" * 60)
        print("PHASE 1b: AUDIO TRANSCRIPTION")
        print("=" * 60)
        try:
            transcript_obj = transcribe(
                video_path=Path(args.videos[0]),
                out_dir=output_path / "audio",
                prefer=args.asr_backend or "auto",
            )
        except Exception as exc:
            print(f"[transcription] backend error: {exc}; skipping ASR.")
            transcript_obj = None

        if transcript_obj is not None:
            mean_pct = transcript_obj.mean_word_confidence * 100.0
            seg_count = len(transcript_obj.segments)
            print(
                f"Transcribed {transcript_obj.word_count} words across "
                f"{seg_count} segments using {transcript_obj.backend} "
                f"({transcript_obj.model_id}); mean confidence {mean_pct:.0f}%."
            )
            # Also expose the plain-text file via the legacy `transcript`
            # string path so callers that only consume the string keep
            # working (legacy report builders, ad-hoc grep, etc).
            try:
                transcript_txt = (output_path / "audio" / "transcript.txt").read_text(
                    encoding="utf-8"
                )
                if transcript_txt and transcript is None:
                    transcript = transcript_txt
            except OSError:
                pass

    # Run comprehensive analysis
    print("\n" + "=" * 60)
    print("PHASE 2: VIDEO & TECHNIQUE ANALYSIS")
    print("=" * 60)
    
    from backend.lambda_functions.cme_comprehensive_analyzer import analyze_cme_comprehensive
    
    comprehensive_result = analyze_cme_comprehensive(
        video_paths=args.videos,
        transcript=transcript,
        report_claims=claims,
        plaintiff_name=args.plaintiff,
        examiner_name=args.examiner,
        exam_date=args.date,
        api_key=api_key,
        output_dir=str(output_path / "comprehensive"),
        frame_interval=frame_interval,
        frames_dir=str(frames_dir),
        max_workers=args.max_workers,
        request_delay_sec=args.request_delay_sec,
        resume=args.resume,
        model=model,
        vision_client=vision_client,
        transcript_obj=transcript_obj,
    )
    
    # Run behavior analysis
    print("\n" + "=" * 60)
    print("PHASE 3: BEHAVIOR & PROFESSIONALISM ANALYSIS")
    print("=" * 60)
    
    from backend.lambda_functions.cme_behavior_analyzer import analyze_cme_behavior
    
    behavior_result = analyze_cme_behavior(
        frames_dir=str(frames_dir),
        transcript=transcript,
        plaintiff_name=args.plaintiff,
        examiner_name=args.examiner,
        api_key=api_key,
        frame_interval=frame_interval,
        output_dir=str(output_path / "behavior"),
        max_workers=args.max_workers,
        request_delay_sec=args.request_delay_sec,
        resume=args.resume,
        model=model,
        vision_client=vision_client,
        transcript_obj=transcript_obj,
    )

    # Re-run the claim verifier with merged behavior + verbal observations
    # so verdicts can cite both visual technique frames and verbal /
    # behavior cues. The comprehensive pass already wrote a
    # comprehensive-only claim_verdicts.json; we overwrite it with the
    # merged version once behavior data is available. Only fires when
    # claims were supplied (default behavior unchanged otherwise).
    merged_verdicts: list = []
    if claims:
        comp_frames_json_path = (
            output_path / "comprehensive" / "comprehensive_frame_analyses.json"
        )
        try:
            frame_analyses_dicts = json.loads(
                comp_frames_json_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            frame_analyses_dicts = []

        behavior_visual = list(getattr(behavior_result, "visual_observations", []) or [])
        behavior_verbal = list(getattr(behavior_result, "verbal_observations", []) or [])

        merged_verdicts = run_claim_verifier_with_merged_observations(
            claims=claims,
            frame_analyses=frame_analyses_dicts,
            behavior_observations=behavior_visual,
            verbal_observations=behavior_verbal,
            vision_client=vision_client,
            output_dir=output_path / "comprehensive",
            max_workers=args.max_workers,
            model_id=model,
            resume=args.resume,
            research_client=research_client,
        )
        if merged_verdicts:
            counts = Counter(
                (v.get("verdict") or "insufficient_evidence") for v in merged_verdicts
            )
            print(
                "Claim verdicts: "
                f"{counts.get('supported', 0)} supported, "
                f"{counts.get('contradicted', 0)} contradicted, "
                f"{counts.get('not_shown', 0)} not_shown, "
                f"{counts.get('partially_supported', 0)} partially, "
                f"{counts.get('insufficient_evidence', 0)} insufficient"
            )

    # Generate HTML report
    print("\n" + "=" * 60)
    print("GENERATING REPORT")
    print("=" * 60)
    
    html_path = output_path / f"cme_report_{args.plaintiff.replace(' ', '_') if args.plaintiff else 'analysis'}.html"
    generate_html_report(comprehensive_result, behavior_result, str(html_path))
    
    print(f"\nHTML Report: {html_path}")

    
    # Summary
    total_cost = comprehensive_result.total_cost_usd + behavior_result.total_cost_usd
    wall_sec = time.perf_counter() - wall_t0
    vision_calls = len(all_frames) * 2
    provider_models = {p: (primary_model if p == primary_provider else default_model_for(p)) for p in providers}
    cost_payload = {
        "estimated_total_usd": round(total_cost_est, 4),
        "actual_total_usd": round(total_cost, 4),
        "delta_usd": round(total_cost - total_cost_est, 4),
        "wall_clock_sec": round(wall_sec, 2),
        "frame_count": len(all_frames),
        "vision_api_calls": vision_calls,
        "model": model,
        "providers": providers,
        "primary_provider": primary_provider,
        "provider_models": provider_models,
        "frame_interval_sec": frame_interval,
        "technique_prompt_version": comprehensive_result.technique_prompt_version,
        "audio_prompt_version": comprehensive_result.audio_prompt_version,
        "behavior_visual_prompt_version": behavior_result.visual_prompt_version,
        "behavior_verbal_prompt_version": behavior_result.verbal_prompt_version,
        "comprehensive_cost_usd": round(comprehensive_result.total_cost_usd, 4),
        "behavior_cost_usd": round(behavior_result.total_cost_usd, 4),
        "comprehensive_input_tokens": getattr(comprehensive_result, "total_input_tokens", 0),
        "comprehensive_output_tokens": getattr(comprehensive_result, "total_output_tokens", 0),
        "behavior_input_tokens": getattr(behavior_result, "total_input_tokens", 0),
        "behavior_output_tokens": getattr(behavior_result, "total_output_tokens", 0),
    }
    hist_med = median_cost_per_vision_call_usd()
    if hist_med is not None:
        cost_payload["median_usd_per_vision_call_from_history"] = round(hist_med, 6)
    cost_path = write_cost_actual_json(output_path, cost_payload)
    append_cost_history(
        {
            "actual_total_usd": cost_payload["actual_total_usd"],
            "estimated_total_usd": cost_payload["estimated_total_usd"],
            "vision_api_calls": vision_calls,
            "frame_count": len(all_frames),
            "model": model,
        }
    )
    print(f"\nCost reconciliation: {cost_path}")
    print(
        f"Estimated ${cost_payload['estimated_total_usd']:.2f} vs "
        f"actual ${cost_payload['actual_total_usd']:.2f} "
        f"({cost_payload['wall_clock_sec']:.0f}s wall clock)"
    )

    # Provenance MANIFEST.json: deterministic catalog of the analytical
    # artifacts produced under output_path along with a Merkle-ish bundle
    # hash. Written BEFORE the standard report so that the report footer
    # can embed `bundle_sha256` from the manifest. Presentation-only
    # renders (the dark-themed cme_report_*.html and the standard report
    # HTML/PDF) are intentionally excluded from the rolled-up hash; they
    # are derived views of the JSON artifacts, not part of the integrity
    # surface. MANIFEST.json excludes itself from its own hash via
    # compute_bundle_hash's exclude_names.
    video_entries = []
    for v in args.videos:
        v_path = Path(v)
        try:
            video_entries.append(
                {
                    "path": str(v_path),
                    "size_bytes": v_path.stat().st_size if v_path.exists() else None,
                    "sha256": file_sha256(v_path) if v_path.exists() else None,
                }
            )
        except OSError:
            video_entries.append({"path": str(v_path), "size_bytes": None, "sha256": None})

    # audio.wav is intentionally excluded from the bundle hash: it is
    # a large binary derived from the source video, bit-identical given
    # the same ffmpeg invocation, and not part of the analytical text
    # surface. transcript.json / transcript.raw.json / transcript.txt
    # are NOT excluded -- they are first-class analytical artifacts.
    presentation_exclusions = {
        "MANIFEST.json",
        "STANDARD_CME_REPORT.html",
        "STANDARD_CME_REPORT.pdf",
        html_path.name,
    }
    bundle_hash_extra_excludes = {"audio/audio.wav"}
    bundle_hash, file_pairs = compute_bundle_hash(
        output_path,
        exclude_names=presentation_exclusions,
        exclude_relpaths=bundle_hash_extra_excludes,
    )
    manifest_payload = {
        "run_id": run_id,
        "created_at": run_created_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "sources": video_entries,
        "frame_extractor": {
            "tool": "ffmpeg",
            "version": ffmpeg_version(),
            "interval_sec": frame_interval,
            "frame_count": len(all_frames),
            "max_frame_width": args.max_frame_width,
        },
        "providers": providers,
        "primary_provider": primary_provider,
        "provider_models": provider_models,
        "prompt_versions": {
            "technique": TECHNIQUE_FRAME_PROMPT_VERSION,
            "behavior_visual": BEHAVIOR_VISUAL_PROMPT_VERSION,
            "behavior_verbal": BEHAVIOR_VERBAL_PROMPT_VERSION,
            "audio": AUDIO_ANALYSIS_PROMPT_VERSION,
            "claim_verifier": CLAIM_VERIFIER_PROMPT_VERSION,
            "transcription": TRANSCRIPTION_PROMPT_VERSION,
        },
        "transcription": (
            {
                "backend": transcript_obj.backend,
                "model_id": transcript_obj.model_id,
                "prompt_version": TRANSCRIPTION_PROMPT_VERSION,
                "word_count": transcript_obj.word_count,
                "mean_confidence": transcript_obj.mean_word_confidence,
                "duration_sec": transcript_obj.duration_sec,
                "language": transcript_obj.language,
            }
            if transcript_obj is not None
            else None
        ),
        "artifacts": [rel for rel, _digest in file_pairs],
        "artifact_digests": {rel: digest for rel, digest in file_pairs},
        "bundle_sha256": bundle_hash,
        "bundle_hash_excludes": sorted(presentation_exclusions),
        "bundle_hash_extra_excludes": sorted(bundle_hash_extra_excludes),
    }
    manifest_path = output_path / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Provenance manifest: {manifest_path}")
    print(f"Bundle sha256: {bundle_hash}")

    if args.report_format == "standard":
        from backend.lambda_functions.cme_report_builder import write_standard_reports
        case_meta = {
            "patient": args.plaintiff or "Unknown",
            "dob": args.dob or "",
            "examiner": args.examiner or "",
            "exam_date": args.date or "",
            "injury_date": args.injury_date or "",
            "video_length": video_len_str,
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "run_id": run_id,
            "bundle_sha256": bundle_hash,
            "session_id": args.session_id or "",
            "app_base_url": args.app_base_url or "",
        }
        std_html, std_pdf = write_standard_reports(
            output_path, case_meta, claims_path, frame_interval
        )
        print(f"Standard report HTML: {std_html}")
        if std_pdf:
            print(f"Standard report PDF: {std_pdf}")

    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Examination Quality: {comprehensive_result.examination_quality_score:.0f}/100")
    print(f"Professionalism: {comprehensive_result.professionalism_score:.0f}/100")
    print(f"Empathy Score: {behavior_result.empathy_score:.1f}/10")
    print(f"Eye Contact: {behavior_result.eye_contact_score:.0f}%")
    print(f"Overall Demeanor: {behavior_result.overall_demeanor.upper()}")
    print("")
    print(f"Technique Issues: {len(comprehensive_result.technique_issues)}")
    print(f"Behavior Issues: {len(comprehensive_result.behavior_issues) + len(behavior_result.behavior_issues)}")
    print(f"Problematic Quotes: {len(comprehensive_result.problematic_quotes) + len(behavior_result.problematic_quotes)}")
    print("")
    print(f"Total Cost: ${total_cost:.2f}")
    print(f"Results saved to: {output_dir}")


if __name__ == "__main__":
    main()
