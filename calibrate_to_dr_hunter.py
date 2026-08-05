#!/usr/bin/env python3
"""
Calibration Script - Match Dr. Hunter's Gold Standard Analysis
Compares our detection against Dr. Hunter's ground truth findings
"""

import json
import boto3
from typing import Dict, List, Any
from decimal import Decimal

# Load Dr. Hunter's ground truth
with open('dr_hunter_ground_truth.json', 'r') as f:
    GROUND_TRUTH = json.load(f)

def compare_detections(our_tests: List[Dict], ground_truth: Dict) -> Dict[str, Any]:
    """
    Compare our detections against Dr. Hunter's ground truth
    
    Returns:
        Comparison metrics and discrepancies
    """
    gt_tests = {t['test_name']: t for t in ground_truth['gold_standard_tests']}
    
    # Match our tests to ground truth by timestamp proximity
    matched = []
    unmatched_ours = []
    unmatched_gt = []
    
    for our_test in our_tests:
        our_timestamp = float(our_test.get('timestamp', 0))
        our_label = our_test.get('label', 'unknown')
        
        # Find closest ground truth test within 30 seconds
        best_match = None
        best_distance = float('inf')
        
        for gt_name, gt_test in gt_tests.items():
            gt_timestamp = gt_test['timestamp']
            distance = abs(our_timestamp - gt_timestamp)
            
            if distance < 30 and distance < best_distance:
                best_match = gt_test
                best_distance = distance
        
        if best_match:
            matched.append({
                'our_test': our_test,
                'ground_truth': best_match,
                'timestamp_diff': best_distance
            })
        else:
            unmatched_ours.append(our_test)
    
    # Find unmatched ground truth tests
    matched_gt_names = {m['ground_truth']['test_name'] for m in matched}
    for gt_name, gt_test in gt_tests.items():
        if gt_name not in matched_gt_names:
            unmatched_gt.append(gt_test)
    
    return {
        'total_ground_truth': len(gt_tests),
        'total_our_detections': len(our_tests),
        'matched': len(matched),
        'unmatched_ours': len(unmatched_ours),
        'unmatched_ground_truth': len(unmatched_gt),
        'precision': len(matched) / len(our_tests) if our_tests else 0,
        'recall': len(matched) / len(gt_tests) if gt_tests else 0,
        'matched_tests': matched,
        'unmatched_ours': unmatched_ours,
        'unmatched_ground_truth': unmatched_gt
    }

def generate_calibration_report(comparison: Dict[str, Any]) -> str:
    """Generate a calibration report"""
    report = []
    report.append("=" * 60)
    report.append("CALIBRATION REPORT - Dr. Hunter's Gold Standard")
    report.append("=" * 60)
    report.append("")
    report.append(f"Ground Truth Tests: {comparison['total_ground_truth']}")
    report.append(f"Our Detections: {comparison['total_our_detections']}")
    report.append(f"Matched: {comparison['matched']}")
    report.append(f"Precision: {comparison['precision']:.1%}")
    report.append(f"Recall: {comparison['recall']:.1%}")
    report.append("")
    
    if comparison['unmatched_ground_truth']:
        report.append("⚠️ MISSED TESTS (Dr. Hunter found, we didn't):")
        for gt_test in comparison['unmatched_ground_truth']:
            report.append(f"   - {gt_test['test_name']} ({gt_test['timestamp_formatted']})")
        report.append("")
    
    if comparison['unmatched_ours']:
        report.append("⚠️ FALSE POSITIVES (We detected, Dr. Hunter didn't):")
        for our_test in comparison['unmatched_ours'][:10]:  # Show first 10
            report.append(f"   - {our_test.get('label', 'unknown')} (ts: {our_test.get('timestamp', 0)})")
        report.append("")
    
    return "\n".join(report)

if __name__ == "__main__":
    # Example usage - would be called with actual detection results
    print("🎯 Calibration script ready")
    print("Use this to compare our detections against Dr. Hunter's ground truth")

