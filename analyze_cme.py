#!/usr/bin/env python3
"""
CME COMPREHENSIVE ANALYZER
==========================

Production-grade CME video analysis with AI vision.

ANALYZES:
- Video frames (tests, technique, equipment)
- Doctor behavior (attention, eye contact, rushing)
- Audio/sentiment (tone, rudeness, dismissiveness)
- Claim vs Reality comparison

COST: ~$3-5 per case

SETUP:
   export ANTHROPIC_API_KEY="sk-ant-..."
   
USAGE:
   python analyze_cme.py video1.mp4 video2.mov --plaintiff "John Doe" --examiner "Dr. Smith"
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.lambda_functions.cme_comprehensive_analyzer import analyze_cme_comprehensive


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive CME Video Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  # Basic analysis
  python analyze_cme.py video1.mp4 video2.mov
  
  # With case details
  python analyze_cme.py video1.mp4 video2.mov \\
      --plaintiff "Stephanie Hardecker" \\
      --examiner "Dr. Brett Osborn" \\
      --date "5/27/2022"
  
  # With transcript for sentiment analysis
  python analyze_cme.py video1.mp4 --transcript transcript.txt
  
  # With report claims to verify
  python analyze_cme.py video1.mp4 --claims claims.json
  
  # Save all results to folder
  python analyze_cme.py video1.mp4 --output ./results/

WHAT IT ANALYZES:
  VIDEO:
  - Patient attire (gown vs regular clothes)
  - Tests performed and technique
  - Equipment usage (reflex hammer, goniometer, etc.)
  - Doctor's attention and eye contact
  - Rushing indicators
  - Dismissive behavior
  
  AUDIO (if transcript provided):
  - Tone of voice (professional, condescending, dismissive)
  - Interrupting patient
  - Ignoring patient concerns
  - Rude or inappropriate comments
  - Empathy indicators
  - Rushing patient

COST: ~$3-5 per case (~$0.015/frame for video + $0.01/segment for audio)
        """
    )
    
    parser.add_argument("videos", nargs="+", help="Video file paths")
    parser.add_argument("--plaintiff", "-p", help="Plaintiff name")
    parser.add_argument("--examiner", "-e", help="Examiner name")
    parser.add_argument("--date", "-d", help="Exam date")
    parser.add_argument("--transcript", "-t", help="Transcript file for sentiment analysis")
    parser.add_argument("--claims", "-c", help="JSON file with report claims to verify")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--interval", "-i", type=float, default=5.0,
                       help="Seconds between frame extractions (default: 5)")
    parser.add_argument("--api-key", help="Anthropic API key (or set ANTHROPIC_API_KEY)")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    
    args = parser.parse_args()
    
    # Check API key
    api_key = args.api_key or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("=" * 60)
        print("ERROR: Anthropic API key required!")
        print("=" * 60)
        print("")
        print("Get your API key from: https://console.anthropic.com/")
        print("")
        print("Then either:")
        print("  1. Set environment variable:")
        print("     export ANTHROPIC_API_KEY='sk-ant-...'")
        print("")
        print("  2. Pass as argument:")
        print("     python analyze_cme.py video.mp4 --api-key sk-ant-...")
        print("")
        sys.exit(1)
    
    # Verify video files
    for video in args.videos:
        if not os.path.exists(video):
            print(f"ERROR: Video file not found: {video}")
            sys.exit(1)
    
    # Load transcript if provided
    transcript = None
    if args.transcript:
        if os.path.exists(args.transcript):
            with open(args.transcript) as f:
                transcript = f.read()
            print(f"Loaded transcript: {len(transcript)} characters")
        else:
            print(f"Warning: Transcript file not found: {args.transcript}")
    
    # Load claims if provided
    report_claims = None
    if args.claims:
        if os.path.exists(args.claims):
            import json
            with open(args.claims) as f:
                report_claims = json.load(f)
            print(f"Loaded {len(report_claims)} report claims to verify")
        else:
            print(f"Warning: Claims file not found: {args.claims}")
    
    # Estimate cost
    # Rough estimate: assume 5-10 min per video, 1 frame per 5 sec
    estimated_frames = len(args.videos) * 60  # ~5 min per video
    estimated_audio_segments = 10 if transcript else 0
    
    video_cost = estimated_frames * 0.015
    audio_cost = estimated_audio_segments * 0.01
    total_cost = video_cost + audio_cost
    
    print("")
    print("=" * 60)
    print("CME COMPREHENSIVE ANALYZER")
    print("=" * 60)
    print(f"Videos: {len(args.videos)}")
    print(f"Plaintiff: {args.plaintiff or 'Not specified'}")
    print(f"Examiner: {args.examiner or 'Not specified'}")
    print(f"Transcript: {'Yes' if transcript else 'No'}")
    print(f"Claims to verify: {len(report_claims) if report_claims else 0}")
    print("")
    print("ESTIMATED COST:")
    print(f"  Video analysis: ~${video_cost:.2f}")
    if transcript:
        print(f"  Audio analysis: ~${audio_cost:.2f}")
    print(f"  TOTAL: ~${total_cost:.2f}")
    print("=" * 60)
    
    if not args.yes:
        response = input("\nProceed with analysis? [y/N]: ")
        if response.lower() != 'y':
            print("Cancelled.")
            sys.exit(0)
    
    # Run analysis
    result = analyze_cme_comprehensive(
        video_paths=args.videos,
        transcript=transcript,
        report_claims=report_claims,
        plaintiff_name=args.plaintiff,
        examiner_name=args.examiner,
        exam_date=args.date,
        api_key=api_key,
        output_dir=args.output,
        frame_interval=args.interval
    )
    
    print("")
    print("=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Actual cost: ${result.total_cost_usd:.2f}")
    print(f"Frames analyzed: {result.total_frames_analyzed}")
    print(f"Examination Quality Score: {result.examination_quality_score:.0f}/100")
    print(f"Professionalism Score: {result.professionalism_score:.0f}/100")
    print("")
    print(f"Technique issues: {len(result.technique_issues)}")
    print(f"Behavior issues: {len(result.behavior_issues)}")
    print(f"Claim discrepancies: {len(result.claim_vs_reality)}")
    
    if args.output:
        print(f"\nFull results saved to: {args.output}")


if __name__ == "__main__":
    main()
