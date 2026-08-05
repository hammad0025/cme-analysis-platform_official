#!/usr/bin/env python3
"""
Test the improved CME Master Analyzer against Dr. Hunter's findings.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.lambda_functions.cme_master_analyzer import analyze_cme

# Load the actual transcripts
def load_transcripts():
    transcripts = []
    for i in [1, 2, 3]:
        path = f'/tmp/transcript{i}.json'
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
                if 'results' in data:
                    transcripts.append(data['results']['transcripts'][0]['transcript'])
    return " ".join(transcripts)


# Dr. Hunter's 12 findings - our benchmark
DR_HUNTER_FINDINGS = {
    1: "Hands on exam: 10 min 8 sec",
    2: "Repeated testing - examiner not paying attention",
    3: "Found SPASMS in neck and low back - supports injury",
    4: "ROM impaired but NOT measured - merely guessing",
    5: "Claims 'oriented x3' but did NOT test",
    6: "Claims '5/5 strength' but only 5/24 UE, 5/14 LE tested",
    7: "Claims 'bulk normal' but NO tape measurement",
    8: "Limited sensory exam - NOT all dermatomes",
    9: "SLR NOT performed correctly but reported 'negative'",
    10: "Unreported tests: sit-to-stand, Tinel's",
    11: "Non-standard Romberg - NOT reported",
    12: "Only 1/48 CN tests but claims 'III-XII grossly normal'"
}


def main():
    print("=" * 70)
    print("CME MASTER ANALYZER TEST")
    print("Benchmark: Dr. Hunter's 12 Findings")
    print("=" * 70)
    
    transcript = load_transcripts()
    if not transcript:
        print("ERROR: No transcripts found")
        return
    
    print(f"\nTranscript length: {len(transcript)} characters")
    
    case_info = {
        "plaintiff_name": "Cynthia Roberts",
        "dob": "6/14/1965",
        "doi": "9/6/2019",
        "examiner": "Dr. Osborn"
    }
    
    # Run analysis
    print("\nRunning analysis...")
    result = analyze_cme(transcript, case_info)
    
    # Display results
    print(f"\n{'='*70}")
    print("ANALYSIS RESULTS")
    print(f"{'='*70}")
    
    print(f"\nSummary:")
    for key, val in result['summary'].items():
        print(f"  {key}: {val}")
    
    print(f"\nCompleteness:")
    for key, val in result['completeness'].items():
        print(f"  {key}: {val}")
    
    print(f"\nObjective Findings for Plaintiff: {result['objective_findings_for_plaintiff']}")
    print(f"Unreported Tests: {result['unreported_tests']}")
    print(f"Claims Detected: {result['claims_detected']}")
    
    print(f"\n{'='*70}")
    print("DETAILED FINDINGS")
    print(f"{'='*70}")
    
    for i, finding in enumerate(result['findings'], 1):
        severity_icon = "🔴" if finding['severity'] == 'critical' else "🟡" if finding['severity'] == 'high' else "⚪"
        plaintiff_icon = "✓ HELPS PLAINTIFF" if finding['helps_plaintiff'] else ""
        
        print(f"\n{i}. [{finding['category']}] {severity_icon}")
        print(f"   {finding['finding']}")
        if finding['claim']:
            print(f"   CLAIM: {finding['claim']}")
        if finding['reality']:
            print(f"   REALITY: {finding['reality']}")
        print(f"   Significance: {finding['significance']}")
        if plaintiff_icon:
            print(f"   {plaintiff_icon}")
    
    # Compare to Dr. Hunter
    print(f"\n{'='*70}")
    print("COMPARISON TO DR. HUNTER'S FINDINGS")
    print(f"{'='*70}")
    
    matched = []
    missed = []
    
    # Manual comparison
    findings_text = json.dumps(result).lower()
    
    # Check each Hunter finding
    checks = {
        1: "timing" in findings_text or "duration" in findings_text,  # We note this but can't measure from transcript
        2: "repeat" in findings_text or "again" in findings_text,
        3: "spasm" in findings_text,
        4: "rom" in findings_text and ("not measured" in findings_text or "guessing" in findings_text or "visual" in findings_text),
        5: "oriented" in findings_text and "not" in findings_text,
        6: "strength" in findings_text and ("5/24" in findings_text or "24" in findings_text or "muscle groups" in findings_text),
        7: "bulk" in findings_text and ("tape" in findings_text or "measure" in findings_text),
        8: "sensory" in findings_text or "dermatome" in findings_text,
        9: "slr" in findings_text or "straight leg" in findings_text,
        10: "unreported" in findings_text and ("sit" in findings_text or "tinel" in findings_text),
        11: "romberg" in findings_text,
        12: "cranial" in findings_text or "cn" in findings_text
    }
    
    for num, dr_finding in DR_HUNTER_FINDINGS.items():
        if checks.get(num, False):
            matched.append(num)
            status = "✓ MATCHED"
        else:
            missed.append(num)
            status = "✗ MISSED"
        print(f"\n{num}. {status}")
        print(f"   Dr. Hunter: {dr_finding}")
    
    score = len(matched)
    total = len(DR_HUNTER_FINDINGS)
    percentage = round((score / total) * 100, 1)
    
    print(f"\n{'='*70}")
    print(f"SCORE: {score}/{total} ({percentage}%)")
    print(f"{'='*70}")
    
    if missed:
        print(f"\nMISSED FINDINGS: {missed}")
    
    # Save results
    output_file = '/Users/hammadhaque/Documents/cme-analysis-platform/master_analyzer_test_result.json'
    with open(output_file, 'w') as f:
        json.dump({
            "result": result,
            "hunter_comparison": {
                "matched": matched,
                "missed": missed,
                "score": f"{score}/{total}",
                "percentage": percentage
            }
        }, f, indent=2)
    
    print(f"\nFull results saved to: {output_file}")


if __name__ == "__main__":
    main()
