#!/usr/bin/env python3
"""
Comprehensive PDF processing script for ALL PDFs in the repo
Processes PDFs from all folders including TBI, Ortho, Spine, etc.
"""

import os
import json
import logging
import argparse
import time
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict

# PDF extraction libraries
try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

# Test taxonomy patterns (from existing taxonomy)
TEST_PATTERNS = {
    'deep_tendon_reflexes': [
        r'dtr', r'deep\s+tendon\s+reflex', r'biceps\s+reflex', r'triceps\s+reflex',
        r'patellar\s+reflex', r'achilles\s+reflex', r'knee\s+jerks?', r'ankle\s+jerks?'
    ],
    'cranial_nerves': [
        r'cranial\s+nerve', r'cn\s+[ivx]+', r'olfactory', r'optic', r'oculomotor',
        r'trochlear', r'trigeminal', r'abducens', r'facial', r'vestibulocochlear',
        r'glossopharyngeal', r'vagus', r'accessory', r'hypoglossal'
    ],
    'range_of_motion': [
        r'range\s+of\s+motion', r'rom\s+(?:test|exam)', r'flexion', r'extension',
        r'goniometer', r'inclinometer', r'joint\s+mobility'
    ],
    'manual_muscle_testing': [
        r'muscle\s+strength', r'mmt', r'strength\s+testing', r'grade\s+[0-5]',
        r'manual\s+muscle\s+test', r'resistance\s+testing'
    ],
    'palpation': [
        r'palpat(?:e|ion)', r'tenderness', r'tender\s+points?', r'trigger\s+points?'
    ],
    'gait_observation': [
        r'gait\s+(?:test|exam|observation)', r'walking\s+pattern', r'ambulation',
        r'tandem\s+gait', r'heel\s+to\s+toe'
    ],
    'tinels_sign': [
        r'tinel', r'tinel\'?s\s+sign', r'percussion\s+test'
    ],
    'straight_leg_raise': [
        r'slr', r'straight\s+leg\s+raise', r'lasègue', r'lasegue'
    ],
    'babinski_sign': [
        r'babinski', r'plantar\s+reflex', r'toe\s+sign'
    ],
    'hoffmanns_sign': [
        r'hoffmann', r'finger\s+flexion\s+test'
    ],
    'lachman_test': [
        r'lachman', r'anterior\s+cruciate\s+ligament', r'acl\s+test'
    ],
    'neer_test': [
        r'neer\s+test', r'impingement\s+test'
    ],
    'hawkins_kennedy_test': [
        r'hawkins', r'kennedy\s+test'
    ],
    'mcmurray_test': [
        r'mcmurray', r'meniscal\s+test'
    ],
    'faber_test': [
        r'faber', r'patrick\s+test'
    ],
    'moca_test': [
        r'moca', r'montreal\s+cognitive', r'cognitive\s+assessment'
    ],
    'romberg_test': [
        r'romberg', r'balance\s+test', r'standing\s+balance'
    ],
    'phalens_test': [
        r'phalen', r'wrist\s+flexion\s+test', r'carpal\s+tunnel'
    ]
}

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from PDF using available libraries"""
    text = ""
    
    # Try pdfplumber first (better quality)
    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages_text = []
                for page in pdf.pages[:50]:  # Limit to first 50 pages
                    page_text = page.extract_text()
                    if page_text:
                        pages_text.append(page_text)
                text = "\n".join(pages_text)
                if text:
                    return text
        except Exception as e:
            logger.debug(f"pdfplumber failed for {pdf_path.name}: {e}")
    
    # Fallback to PyPDF2
    if HAS_PYPDF2:
        try:
            with open(pdf_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                pages_text = []
                for page_num in range(min(50, len(pdf_reader.pages))):
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text()
                    if page_text:
                        pages_text.append(page_text)
                text = "\n".join(pages_text)
                if text:
                    return text
        except Exception as e:
            logger.debug(f"PyPDF2 failed for {pdf_path.name}: {e}")
    
    return text

def extract_tests_with_pattern_matching(text: str, domain: str) -> List[Dict[str, Any]]:
    """Extract medical tests using pattern matching"""
    import re
    
    text_lower = text.lower()
    found_tests = []
    
    for test_type, patterns in TEST_PATTERNS.items():
        matches = []
        for pattern in patterns:
            regex_matches = re.finditer(pattern, text_lower, re.IGNORECASE)
            for match in regex_matches:
                matches.append({
                    'pattern': pattern,
                    'position': match.start(),
                    'context': text[max(0, match.start()-50):match.end()+50]
                })
        
        if matches:
            found_tests.append({
                'test_type': test_type,
                'match_count': len(matches),
                'matches': matches[:10]  # Limit to 10 matches
            })
    
    return found_tests

def categorize_pdf(pdf_path: Path) -> str:
    """Categorize PDF by folder path"""
    path_str = str(pdf_path).lower()
    
    if 'tbi' in path_str:
        return 'tbi'
    elif 'ortho' in path_str or 'orthopedic' in path_str:
        return 'orthopedic'
    elif 'spine' in path_str:
        return 'spine'
    elif 'pain' in path_str:
        return 'pain'
    elif 'mental' in path_str or 'moca' in path_str:
        return 'mental_status'
    elif 'cranial' in path_str or 'nerve' in path_str:
        return 'cranial_nerves'
    elif 'gait' in path_str:
        return 'gait'
    elif 'reflex' in path_str:
        return 'reflexes'
    elif 'sensory' in path_str:
        return 'sensory'
    elif 'rom' in path_str or 'range' in path_str or 'motion' in path_str:
        return 'range_of_motion'
    else:
        return 'general'

def process_pdf(pdf_path: Path) -> Dict[str, Any]:
    """Process a single PDF"""
    logger.info(f"Processing: {pdf_path.name}")
    
    domain = categorize_pdf(pdf_path)
    text = extract_text_from_pdf(pdf_path)
    
    if not text or len(text) < 100:
        return {
            'filename': pdf_path.name,
            'path': str(pdf_path),
            'domain': domain,
            'error': 'No text extracted',
            'pattern_tests': [],
            'total_tests_found': 0
        }
    
    # Extract tests using pattern matching
    pattern_tests = extract_tests_with_pattern_matching(text, domain)
    
    return {
        'filename': pdf_path.name,
        'path': str(pdf_path),
        'domain': domain,
        'text_length': len(text),
        'pattern_tests': pattern_tests,
        'total_tests_found': len(pattern_tests),
        'pattern_matches': len(pattern_tests)
    }

def main():
    parser = argparse.ArgumentParser(description="Process ALL PDFs in the repo")
    parser.add_argument('--chunk-size', type=int, default=50, help='PDFs per chunk')
    parser.add_argument('--output', default='comprehensive_pdf_extraction.json', help='Output file')
    parser.add_argument('--progress', default='comprehensive_pdf_progress.json', help='Progress file')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🔍 COMPREHENSIVE PDF PROCESSING")
    print("=" * 60)
    print("")
    
    # Find all PDFs
    print("📂 Scanning for PDFs...")
    root = Path('.')
    all_pdfs = []
    
    for pdf_file in root.rglob('*.pdf'):
        if 'node_modules' in str(pdf_file) or '.git' in str(pdf_file):
            continue
        all_pdfs.append(pdf_file)
    
    print(f"   ✅ Found {len(all_pdfs)} PDFs")
    
    # Load existing progress
    results = []
    processed_paths = set()
    
    if Path(args.progress).exists():
        with open(args.progress, 'r') as f:
            progress_data = json.load(f)
            results = progress_data.get('results', [])
            processed_paths = {r['path'] for r in results}
            print(f"   📂 Resuming: {len(results)} already processed")
    
    # Filter out already processed
    pdfs_to_process = [p for p in all_pdfs if str(p) not in processed_paths]
    print(f"   🎯 Processing: {len(pdfs_to_process)} new PDFs")
    
    if not pdfs_to_process:
        print("   ✅ All PDFs already processed!")
        return
    
    # Process in chunks
    chunk_size = args.chunk_size
    total_chunks = (len(pdfs_to_process) + chunk_size - 1) // chunk_size
    
    print(f"\n📦 Processing in chunks of {chunk_size} ({total_chunks} chunks)")
    print("")
    
    for chunk_idx in range(0, len(pdfs_to_process), chunk_size):
        chunk = pdfs_to_process[chunk_idx:chunk_idx + chunk_size]
        chunk_num = chunk_idx // chunk_size + 1
        
        print("=" * 60)
        print(f"📦 PROCESSING CHUNK {chunk_num}/{total_chunks} ({len(chunk)} PDFs)")
        print("=" * 60)
        
        chunk_results = []
        for pdf_path in chunk:
            try:
                result = process_pdf(pdf_path)
                chunk_results.append(result)
                
                if result.get('pattern_tests'):
                    test_count = result['total_tests_found']
                    print(f"   ✅ {pdf_path.name}: {test_count} test types found")
                else:
                    print(f"   ⚠️  {pdf_path.name}: No tests found")
            except Exception as e:
                logger.error(f"Error processing {pdf_path.name}: {e}")
                chunk_results.append({
                    'filename': pdf_path.name,
                    'path': str(pdf_path),
                    'error': str(e),
                    'pattern_tests': []
                })
        
        results.extend(chunk_results)
        
        # Save progress
        progress_data = {
            'total_pdfs': len(all_pdfs),
            'processed_pdfs': len(results),
            'results': results,
            'last_updated': time.time()
        }
        
        with open(args.progress, 'w') as f:
            json.dump(progress_data, f, indent=2)
        
        print(f"\n💾 Progress saved: {len(results)}/{len(all_pdfs)} PDFs processed")
        print(f"✅ Chunk {chunk_num} complete!")
        print("")
        
        # Small delay to avoid overwhelming
        time.sleep(1)
    
    # Generate taxonomy expansion
    print("=" * 60)
    print("📊 GENERATING TAXONOMY EXPANSION")
    print("=" * 60)
    
    taxonomy_expansion = defaultdict(lambda: {
        'keywords': set(),
        'patterns': set(),
        'source_count': 0,
        'domains': set()
    })
    
    for result in results:
        if result.get('pattern_tests'):
            domain = result.get('domain', 'general')
            for test_data in result['pattern_tests']:
                test_type = test_data['test_type']
                taxonomy_expansion[test_type]['source_count'] += 1
                taxonomy_expansion[test_type]['domains'].add(domain)
                
                # Extract keywords from matches
                for match in test_data.get('matches', [])[:5]:
                    context = match.get('context', '')
                    # Simple keyword extraction (first few words)
                    words = context.lower().split()[:5]
                    taxonomy_expansion[test_type]['keywords'].update(words)
    
    # Convert sets to lists for JSON
    final_taxonomy = {}
    for test_type, data in taxonomy_expansion.items():
        final_taxonomy[test_type] = {
            'keywords': list(data['keywords'])[:50],  # Limit to 50
            'patterns': list(data['patterns']),
            'source_count': data['source_count'],
            'domains': list(data['domains'])
        }
    
    # Save final results
    final_output = {
        'total_pdfs': len(all_pdfs),
        'processed_pdfs': len(results),
        'taxonomy_expansion': final_taxonomy,
        'results': results[:100]  # Limit results in final file
    }
    
    with open(args.output, 'w') as f:
        json.dump(final_output, f, indent=2)
    
    print(f"\n✅ Final results saved to {args.output}")
    print(f"   Test types found: {len(final_taxonomy)}")
    print(f"   Total keywords: {sum(len(t['keywords']) for t in final_taxonomy.values())}")
    print("\n🎉 Processing complete!")

if __name__ == "__main__":
    main()

