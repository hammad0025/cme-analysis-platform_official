#!/usr/bin/env python3
"""
Analyze CME Video Recordings folder to extract training data
Identifies videos, transcripts, and ground truth annotations for training
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any
import subprocess

TRAINING_FOLDER = "CME Video Recordings"

def scan_training_folder() -> Dict[str, Any]:
    """Scan the CME Video Recordings folder and catalog all training materials"""
    
    base_path = Path(TRAINING_FOLDER)
    if not base_path.exists():
        return {'error': f'Folder {TRAINING_FOLDER} not found'}
    
    catalog = {
        'folders': {},
        'videos': [],
        'pdfs': [],
        'total_files': 0,
        'categories': {}
    }
    
    # Scan each subfolder
    for folder in base_path.iterdir():
        if not folder.is_dir():
            continue
        
        folder_name = folder.name
        catalog['folders'][folder_name] = {
            'path': str(folder),
            'videos': [],
            'pdfs': [],
            'other_files': []
        }
        
        # Scan files in folder
        for file_path in folder.rglob('*'):
            if file_path.is_file():
                catalog['total_files'] += 1
                ext = file_path.suffix.lower()
                
                file_info = {
                    'name': file_path.name,
                    'path': str(file_path),
                    'size_mb': file_path.stat().st_size / (1024 * 1024)
                }
                
                if ext in ['.mp4', '.mpg', '.mpeg', '.mov', '.avi']:
                    catalog['folders'][folder_name]['videos'].append(file_info)
                    catalog['videos'].append(file_info)
                    
                    # Categorize by folder name
                    category = folder_name.lower()
                    if 'mental' in category or 'moca' in category:
                        category_type = 'mental_status'
                    elif 'range' in category and 'spine' in category:
                        category_type = 'spine_rom'
                    elif 'range' in category and 'limb' in category:
                        category_type = 'limb_rom'
                    elif 'sensory' in category:
                        category_type = 'sensory'
                    elif 'gait' in category:
                        category_type = 'gait'
                    elif 'cranial' in category:
                        category_type = 'cranial_nerves'
                    elif 'orthopedic' in category or 'ortho' in category:
                        category_type = 'orthopedic'
                    elif 'romberg' in category:
                        category_type = 'romberg'
                    elif 'rsd' in category or 'crps' in category:
                        category_type = 'rsd_crps'
                    else:
                        category_type = 'other'
                    
                    if category_type not in catalog['categories']:
                        catalog['categories'][category_type] = []
                    catalog['categories'][category_type].append(file_info)
                    
                elif ext == '.pdf':
                    catalog['folders'][folder_name]['pdfs'].append(file_info)
                    catalog['pdfs'].append(file_info)
                else:
                    catalog['folders'][folder_name]['other_files'].append(file_info)
    
    return catalog

def identify_training_opportunities(catalog: Dict[str, Any]) -> Dict[str, Any]:
    """Identify how this data can be used for training"""
    
    opportunities = {
        'video_training': {
            'description': 'Use videos to train video analysis models',
            'count': len(catalog.get('videos', [])),
            'use_cases': [
                'Visual test detection (ROM, gait, reflexes)',
                'Motion pattern recognition',
                'Examiner-patient interaction patterns',
                'Test performance validation'
            ]
        },
        'transcript_training': {
            'description': 'Extract transcripts to improve NLP detection',
            'count': len(catalog.get('videos', [])),
            'use_cases': [
                'Test mention patterns',
                'Doctor command recognition',
                'Medical terminology extraction',
                'Speaker diarization training'
            ]
        },
        'ground_truth_creation': {
            'description': 'Create ground truth annotations from Dr. Hunter references',
            'count': len(catalog.get('folders', {})),
            'use_cases': [
                'Test detection calibration',
                'Performance validation',
                'Precision/recall improvement',
                'Threshold tuning'
            ]
        },
        'taxonomy_expansion': {
            'description': 'Extract test types and patterns from PDFs',
            'count': len(catalog.get('pdfs', [])),
            'use_cases': [
                'Add new test types to TEST_TAXONOMY',
                'Extract keywords and patterns',
                'Improve detection accuracy',
                'Domain-specific terminology'
            ]
        }
    }
    
    return opportunities

def generate_training_plan(catalog: Dict[str, Any]) -> str:
    """Generate a training plan based on available data"""
    
    plan = []
    plan.append("=" * 60)
    plan.append("🎓 TRAINING DATA ANALYSIS & PLAN")
    plan.append("=" * 60)
    plan.append("")
    
    plan.append(f"📊 DATA INVENTORY:")
    plan.append(f"   Total files: {catalog.get('total_files', 0)}")
    plan.append(f"   Videos: {len(catalog.get('videos', []))}")
    plan.append(f"   PDFs: {len(catalog.get('pdfs', []))}")
    plan.append(f"   Categories: {len(catalog.get('categories', {}))}")
    plan.append("")
    
    plan.append("📁 CATEGORIES FOUND:")
    for category, files in catalog.get('categories', {}).items():
        plan.append(f"   - {category}: {len(files)} videos")
    plan.append("")
    
    opportunities = identify_training_opportunities(catalog)
    
    plan.append("🎯 TRAINING OPPORTUNITIES:")
    for opp_name, opp_data in opportunities.items():
        plan.append(f"\n   {opp_name.replace('_', ' ').title()}:")
        plan.append(f"      {opp_data['description']}")
        plan.append(f"      Available: {opp_data['count']} items")
        plan.append(f"      Use cases:")
        for use_case in opp_data['use_cases']:
            plan.append(f"         • {use_case}")
    
    plan.append("")
    plan.append("📋 RECOMMENDED TRAINING STEPS:")
    plan.append("")
    plan.append("   1. VIDEO ANALYSIS TRAINING:")
    plan.append("      - Process videos through current pipeline")
    plan.append("      - Extract visual patterns for each test type")
    plan.append("      - Build motion pattern library")
    plan.append("      - Train Rekognition custom labels")
    plan.append("")
    plan.append("   2. TRANSCRIPT TRAINING:")
    plan.append("      - Transcribe all videos")
    plan.append("      - Extract test mention patterns")
    plan.append("      - Build keyword/pattern database")
    plan.append("      - Improve TEST_TAXONOMY")
    plan.append("")
    plan.append("   3. GROUND TRUTH CREATION:")
    plan.append("      - Have Dr. Hunter annotate sample videos")
    plan.append("      - Create ground truth JSON files")
    plan.append("      - Calibrate detection thresholds")
    plan.append("      - Measure precision/recall improvements")
    plan.append("")
    plan.append("   4. PDF KNOWLEDGE EXTRACTION:")
    plan.append("      - Process PDFs for test terminology")
    plan.append("      - Extract procedures and keywords")
    plan.append("      - Expand TEST_TAXONOMY")
    plan.append("      - Add domain-specific patterns")
    plan.append("")
    plan.append("=" * 60)
    
    return "\n".join(plan)

def main():
    print("🔍 Scanning CME Video Recordings folder...")
    print("")
    
    catalog = scan_training_folder()
    
    if 'error' in catalog:
        print(f"❌ {catalog['error']}")
        return
    
    # Save catalog
    with open('training_data_catalog.json', 'w') as f:
        json.dump(catalog, f, indent=2, default=str)
    
    print("✅ Catalog saved to training_data_catalog.json")
    print("")
    
    # Generate and print training plan
    plan = generate_training_plan(catalog)
    print(plan)
    
    # Save plan
    with open('TRAINING_PLAN.md', 'w') as f:
        f.write(plan)
    
    print("\n✅ Training plan saved to TRAINING_PLAN.md")

if __name__ == "__main__":
    main()

