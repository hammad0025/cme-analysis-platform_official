#!/usr/bin/env python3
"""
CME DOROTHY ANALYZER - Full Implementation of Dorothy's Requirements
====================================================================

Based on Dorothy Clay Sims requirements (Feb 4 & Feb 11, 2026)

WHAT IT ANALYZES:

1. TOP 10-20 EGREGIOUS BEHAVIORS (at beginning of report)
2. CLAIM VS REALITY - what report claims vs what actually happened (MOST IMPORTANT)
3. TRANSCRIPT MISREPRESENTATIONS - report vs what was actually said
4. DOCTOR BEHAVIOR - rude, not observing, interruptions with timestamps
5. PATIENT OBSERVATIONS - crying, confusion, distress (documented each time)
6. EXAM TIMING - actual vs claimed
7. CRANIAL NERVES - which were/weren't properly assessed
8. MENTAL STATUS - MOCA vs Folstein, actual vs reported score
9. RANGE OF MOTION - actual measurements, goniometer usage
10. BODY PART BREAKDOWN - analysis by body region
11. DR. HUNTER REFERENCES - how it should have been done

VERIFICATION:
- Ensures ENTIRE video is watched (coverage check)
- Saves project by patient name
- Includes redlined report for verification

USAGE:
    python analyze_cme_dorothy.py video1.mp4 video2.mov \\
        --patient "John Doe" \\
        --examiner "Dr. Smith" \\
        --claims claims.json \\
        --transcript transcript.txt \\
        --redlined redlined_report.pdf \\
        --output ./projects/

COST: ~$5-10 per case (depends on video length)
"""

import sys
import os
import json
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.lambda_functions.cme_dorothy_analyzer import analyze_cme_dorothy


def main():
    parser = argparse.ArgumentParser(
        description="CME Analysis - Dorothy's Full Requirements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
DOROTHY'S REQUIREMENTS CHECKLIST:
  ✓ Top 10-20 egregious behaviors (at beginning of report)
  ✓ Claim vs Reality (MOST IMPORTANT)
  ✓ Transcript misrepresentations
  ✓ Doctor rudeness detection
  ✓ Not observing patient during tests
  ✓ Interruption count + timestamps
  ✓ Patient crying (documented each time)
  ✓ Patient confusion (documented each time)
  ✓ Exam length
  ✓ Cranial nerves - which were/weren't assessed
  ✓ Mental status (MOCA vs Folstein, actual vs reported)
  ✓ Range of motion + goniometer check
  ✓ Body part breakdown
  ✓ Dr. Hunter references
  ✓ Project saved by patient name
  ✓ Video coverage verification (ensures entire video watched)

EXAMPLES:
  # Basic analysis
  python analyze_cme_dorothy.py video.mp4 --patient "John Doe"
  
  # Full analysis with all inputs
  python analyze_cme_dorothy.py video1.mp4 video2.mov \\
      --patient "John Doe" \\
      --examiner "Dr. Smith" \\
      --date "2024-01-15" \\
      --claims claims.json \\
      --transcript transcript.txt \\
      --redlined redlined_report.pdf \\
      --output ./cme_projects/
        """
    )
    
    parser.add_argument("videos", nargs="+", help="Video file paths")
    parser.add_argument("--patient", "-p", required=True, help="Patient name (REQUIRED)")
    parser.add_argument("--examiner", "-e", help="Examiner name")
    parser.add_argument("--date", "-d", help="Exam date")
    parser.add_argument("--claims", "-c", help="JSON file with report claims")
    parser.add_argument("--transcript", "-t", help="Transcript file")
    parser.add_argument("--redlined", "-r", help="Redlined report PDF for verification")
    parser.add_argument("--output", "-o", default="./cme_projects", help="Output directory")
    parser.add_argument("--interval", "-i", type=float, default=3.0,
                       help="Frame interval in seconds (default: 3)")
    parser.add_argument("--api-key", help="Anthropic API key")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    
    args = parser.parse_args()
    
    # Check API key
    api_key = args.api_key or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("\n" + "=" * 60)
        print("ERROR: Anthropic API key required!")
        print("=" * 60)
        print("\nGet your key: https://console.anthropic.com/")
        print("\nThen run:")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)
    
    # Check videos exist
    for video in args.videos:
        if not os.path.exists(video):
            print(f"ERROR: Video not found: {video}")
            sys.exit(1)
    
    # Load claims
    claims = None
    if args.claims:
        if os.path.exists(args.claims):
            with open(args.claims) as f:
                claims = json.load(f)
            print(f"Loaded {len(claims)} report claims")
        else:
            print(f"Warning: Claims file not found: {args.claims}")
    
    # Load transcript
    transcript = None
    if args.transcript:
        if os.path.exists(args.transcript):
            with open(args.transcript) as f:
                transcript = f.read()
            print(f"Loaded transcript: {len(transcript)} characters")
        else:
            print(f"Warning: Transcript file not found: {args.transcript}")
    
    # Estimate cost
    # Assume ~5 min per video at 3 sec intervals = ~100 frames per video
    est_frames = len(args.videos) * 100
    est_cost = est_frames * 0.015
    if transcript:
        est_cost += 0.20  # Transcript analysis
    
    print("\n" + "=" * 60)
    print("CME DOROTHY ANALYZER")
    print("=" * 60)
    print(f"Patient: {args.patient}")
    print(f"Examiner: {args.examiner or 'Not specified'}")
    print(f"Videos: {len(args.videos)}")
    print(f"Claims file: {'Yes' if claims else 'No'}")
    print(f"Transcript: {'Yes' if transcript else 'No'}")
    print(f"Redlined report: {'Yes' if args.redlined else 'No'}")
    print("")
    print("DOROTHY'S REQUIREMENTS TO BE ANALYZED:")
    print("  1. Top 10-20 egregious behaviors")
    print("  2. Claim vs Reality (MOST IMPORTANT)")
    print("  3. Transcript misrepresentations")
    print("  4. Doctor rudeness")
    print("  5. Not observing patient during tests")
    print("  6. Interruption count + locations")
    print("  7. Patient crying instances")
    print("  8. Patient confusion instances")
    print("  9. Exam length")
    print("  10. Cranial nerve assessment")
    print("  11. Mental status (MOCA/Folstein)")
    print("  12. Range of motion + goniometer")
    print("  13. Body part breakdown")
    print("  14. Dr. Hunter references")
    print("")
    print(f"ESTIMATED COST: ~${est_cost:.2f}")
    print(f"Frame interval: {args.interval}s (smaller = more thorough)")
    print("=" * 60)
    
    if not args.yes:
        response = input("\nProceed with analysis? [y/N]: ")
        if response.lower() != 'y':
            print("Cancelled.")
            sys.exit(0)
    
    # Run analysis
    result = analyze_cme_dorothy(
        video_paths=args.videos,
        patient_name=args.patient,
        examiner_name=args.examiner,
        exam_date=args.date,
        report_claims=claims,
        transcript=transcript,
        redlined_report_path=args.redlined,
        api_key=api_key,
        output_dir=args.output,
        frame_interval=args.interval
    )
    
    # Summary
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Project ID: {result.project_id}")
    print(f"Video Coverage: {result.video_coverage_percent:.1f}%")
    print(f"Frames Analyzed: {result.frames_analyzed}")
    print("")
    print("KEY FINDINGS:")
    print(f"  Top Egregious Behaviors: {len(result.top_egregious_behaviors)}")
    print(f"  Claim vs Reality Discrepancies: {len(result.claim_vs_reality)}")
    print(f"  Cranial Nerves NOT Tested: {len(result.cranial_nerves_not_tested)}")
    print(f"  Patient Crying: {len(result.patient_crying_instances)} times")
    print(f"  Patient Confused: {len(result.patient_confusion_instances)} times")
    print(f"  Interruptions: {result.interruption_count}")
    print(f"  Doctor Rude: {'YES' if result.was_doctor_rude else 'NO'}")
    print("")
    print(f"Total Cost: ${result.total_cost_usd:.2f}")
    print(f"Project saved to: {args.output}/{result.project_id}")


if __name__ == "__main__":
    main()
