#!/usr/bin/env python3
"""
Process ALL training PDFs from CME Video Recordings folder
Extract test terminology, keywords, and patterns to expand TEST_TAXONOMY
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any
import logging
from collections import defaultdict
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import PDF libraries
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    logger.warning("pdfplumber not installed. Install with: pip install pdfplumber")

try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False
    logger.warning("PyPDF2 not installed. Install with: pip install PyPDF2")

# Try AWS Bedrock for AI extraction
try:
    import boto3
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
    HAS_BEDROCK = True
except Exception as e:
    HAS_BEDROCK = False
    logger.warning(f"AWS Bedrock not available: {e}")

TRAINING_FOLDER = "CME Video Recordings"
OUTPUT_FILE = "extracted_test_terminology.json"
TAXONOMY_UPDATE_FILE = "test_taxonomy_expansion.py"

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF"""
    text = ""
    
    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            if text.strip():
                return text
        except Exception as e:
            logger.warning(f"pdfplumber failed for {pdf_path}: {e}")
    
    if HAS_PYPDF2:
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
            return text
        except Exception as e:
            logger.error(f"PyPDF2 failed for {pdf_path}: {e}")
    
    return text

def extract_tests_with_pattern_matching(text: str, domain: str) -> List[Dict[str, Any]]:
    """Extract test terminology using pattern matching (no AI needed)"""
    tests_found = []
    text_lower = text.lower()
    
    # Common test patterns
    test_patterns = {
        'range_of_motion': [
            r'range\s+of\s+motion',
            r'rom\s+(?:test|exam|assessment)',
            r'joint\s+mobility',
            r'flexion.*extension',
            r'goniometer',
            r'inclinometer'
        ],
        'manual_muscle_testing': [
            r'manual\s+muscle\s+test',
            r'mmt',
            r'strength\s+testing',
            r'grade\s+[0-5]',
            r'muscle\s+strength'
        ],
        'deep_tendon_reflexes': [
            r'deep\s+tendon\s+reflex',
            r'dtr',
            r'patellar\s+reflex',
            r'achilles\s+reflex',
            r'biceps\s+reflex',
            r'triceps\s+reflex'
        ],
        'sensation': [
            r'sensation\s+test',
            r'light\s+touch',
            r'pinprick',
            r'two.point\s+discrimination',
            r'vibration\s+sense',
            r'proprioception',
            r'graphesthesia',
            r'stereognosis'
        ],
        'gait_observation': [
            r'gait\s+(?:test|exam|observation)',
            r'walking\s+pattern',
            r'tandem\s+gait',
            r'heel\s+walk',
            r'toe\s+walk'
        ],
        'straight_leg_raise': [
            r'straight\s+leg\s+raise',
            r'slr',
            r'lasègue',
            r'leg\s+raise\s+test'
        ],
        'spurlings_test': [
            r'spurling',
            r'cervical\s+compression',
            r'foraminal\s+compression'
        ],
        'babinski_sign': [
            r'babinski',
            r'plantar\s+reflex',
            r'toe\s+sign'
        ],
        'romberg_test': [
            r'romberg',
            r'balance\s+test',
            r'standing\s+balance'
        ],
        'cranial_nerves': [
            r'cranial\s+nerve',
            r'cn\s+[ivx]+',
            r'olfactory',
            r'optic',
            r'oculomotor',
            r'trochlear',
            r'trigeminal',
            r'abducens',
            r'facial',
            r'vestibulocochlear',
            r'glossopharyngeal',
            r'vagus',
            r'accessory',
            r'hypoglossal'
        ],
        'moca_test': [
            r'moca',
            r'montreal\s+cognitive',
            r'cognitive\s+assessment'
        ],
        'lachman_test': [
            r'lachman',
            r'acl\s+test',
            r'anterior\s+cruciate'
        ],
        'mcmurray_test': [
            r'mcmurray',
            r'meniscal\s+test',
            r'knee\s+meniscus'
        ],
        'phalens_test': [
            r'phalen',
            r'carpal\s+tunnel',
            r'wrist\s+flexion'
        ],
        'tinels_sign': [
            r'tinel',
            r'percussion\s+test',
            r'nerve\s+percussion'
        ],
        'faber_test': [
            r'faber',
            r'patrick',
            r'figure.4\s+test'
        ],
        'neer_test': [
            r'neer',
            r'impingement\s+test',
            r'shoulder\s+impingement'
        ],
        'hawkins_kennedy_test': [
            r'hawkins',
            r'kennedy',
            r'shoulder\s+impingement'
        ],
        'hoffmanns_sign': [
            r'hoffmann',
            r'finger\s+flexion',
            r'cervical\s+myelopathy'
        ],
        'palpation': [
            r'palpation',
            r'palpate',
            r'tenderness',
            r'trigger\s+point'
        ]
    }
    
    # Extract keywords from text
    keywords_found = defaultdict(list)
    
    for test_type, patterns in test_patterns.items():
        for pattern in patterns:
            matches = re.finditer(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                # Extract context around match
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].strip()
                
                keywords_found[test_type].append({
                    'pattern': pattern,
                    'context': context,
                    'position': match.start()
                })
    
    # Build test entries
    for test_type, matches in keywords_found.items():
        if matches:
            # Extract unique keywords from context
            all_keywords = set()
            for match in matches:
                # Extract words around the match
                words = re.findall(r'\b[a-z]+\b', match['context'].lower())
                all_keywords.update(words)
            
            tests_found.append({
                'test_type': test_type,
                'keywords': list(all_keywords)[:20],  # Limit keywords
                'patterns': [m['pattern'] for m in matches[:5]],  # Top patterns
                'domain': domain,
                'match_count': len(matches)
            })
    
    return tests_found

def extract_tests_with_ai(text: str, domain: str, filename: str) -> List[Dict[str, Any]]:
    """Use AI to extract medical tests (if Bedrock available)"""
    if not HAS_BEDROCK:
        return []  # Skip AI if not available - pattern matching will handle it
    
    if not text or len(text) < 100:
        return []
    
    # Truncate text if too long
    text_sample = text[:8000]
    
    prompt = f"""Extract medical test names, procedures, and terminology from this {domain} medical literature.

FILENAME: {filename}
DOMAIN: {domain}

TEXT:
{text_sample}

Return JSON array with:
- test_name: Standardized name
- keywords: List of keywords/phrases
- patterns: Regex patterns for detection
- category: Domain category

Return ONLY JSON array, no text:"""

    try:
        response = bedrock_client.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4000,
                "messages": [{
                    "role": "user",
                    "content": prompt
                }]
            })
        )
        
        response_body = json.loads(response['body'].read())
        ai_result = response_body.get('content', [{}])[0].get('text', '[]')
        
        # Extract JSON
        if '```json' in ai_result:
            ai_result = ai_result.split('```json')[1].split('```')[0].strip()
        elif '```' in ai_result:
            ai_result = ai_result.split('```')[1].split('```')[0].strip()
        
        tests = json.loads(ai_result)
        return tests if isinstance(tests, list) else []
        
    except Exception as e:
        # Silently skip AI extraction - pattern matching is primary method
        # Only log if it's not the Bedrock access issue (to reduce noise)
        if 'ResourceNotFoundException' not in str(e) and 'use case details' not in str(e).lower():
            logger.debug(f"AI extraction skipped: {e}")
        return []

def process_pdf(pdf_path: str, domain: str) -> Dict[str, Any]:
    """Process a single PDF"""
    logger.info(f"Processing: {os.path.basename(pdf_path)}")
    
    text = extract_text_from_pdf(pdf_path)
    
    if not text or len(text) < 100:
        return {
            'filename': os.path.basename(pdf_path),
            'domain': domain,
            'error': 'No text extracted',
            'pattern_tests': [],
            'total_tests_found': 0
        }
    
    # Extract tests using pattern matching (always works - PRIMARY METHOD)
    pattern_tests = extract_tests_with_pattern_matching(text, domain)
    
    # Try AI extraction (if available - OPTIONAL)
    ai_tests = []
    if HAS_BEDROCK:
        try:
            ai_tests = extract_tests_with_ai(text, domain, os.path.basename(pdf_path))
        except:
            pass  # Pattern matching is sufficient
    
    return {
        'filename': os.path.basename(pdf_path),
        'domain': domain,
        'text_length': len(text),
        'pattern_tests': pattern_tests,
        'ai_tests': ai_tests,
        'total_tests_found': len(pattern_tests) + len(ai_tests),
        'pattern_matches': len(pattern_tests)  # Track pattern matching success
    }

def determine_domain_from_folder(folder_name: str) -> str:
    """Determine domain category from folder name"""
    folder_lower = folder_name.lower()
    
    if 'mental' in folder_lower or 'moca' in folder_lower:
        return 'mental_status'
    elif 'spine' in folder_lower and 'rom' in folder_lower:
        return 'spine_rom'
    elif 'limb' in folder_lower and 'rom' in folder_lower:
        return 'limb_rom'
    elif 'sensory' in folder_lower:
        return 'sensory'
    elif 'gait' in folder_lower:
        return 'gait'
    elif 'cranial' in folder_lower:
        return 'cranial_nerves'
    elif 'orthopedic' in folder_lower or 'ortho' in folder_lower:
        return 'orthopedic'
    elif 'romberg' in folder_lower:
        return 'romberg'
    elif 'reflex' in folder_lower:
        return 'reflexes'
    elif 'motor' in folder_lower:
        return 'motor'
    elif 'palpation' in folder_lower:
        return 'palpation'
    elif 'coordination' in folder_lower:
        return 'coordination'
    elif 'slr' in folder_lower or 'straight' in folder_lower:
        return 'slr'
    elif 'tbi' in folder_lower or 'neuropsych' in folder_lower:
        return 'tbi'
    elif 'spine' in folder_lower:
        return 'spine'
    elif 'knee' in folder_lower:
        return 'knee'
    elif 'pain' in folder_lower:
        return 'pain'
    else:
        return 'general'

def load_progress():
    """Load previous progress if exists"""
    progress_file = 'pdf_processing_progress.json'
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def save_progress(all_results, taxonomy_expansion, processed_pdfs, total_pdfs):
    """Save progress after each chunk"""
    progress_file = 'pdf_processing_progress.json'
    
    progress_data = {
        'processed_pdfs': processed_pdfs,
        'total_pdfs': total_pdfs,
        'results': all_results,
        'taxonomy_expansion': {
            k: {
                'keywords': list(v['keywords']),
                'patterns': list(v['patterns']),
                'domains': list(v['domains']),
                'sources': list(v['sources'])
            }
            for k, v in taxonomy_expansion.items()
        },
        'last_updated': int(time.time())
    }
    
    with open(progress_file, 'w') as f:
        json.dump(progress_data, f, indent=2, default=str)
    
    logger.info(f"💾 Progress saved: {processed_pdfs}/{total_pdfs} PDFs processed")

def process_all_pdfs(chunk_size=50, resume=True):
    """Process all PDFs in training folder in chunks"""
    base_path = Path(TRAINING_FOLDER)
    
    if not base_path.exists():
        logger.error(f"Training folder not found: {TRAINING_FOLDER}")
        return
    
    # Load previous progress if resuming
    processed_pdf_paths = set()
    all_results = []
    taxonomy_expansion = defaultdict(lambda: {
        'keywords': set(),
        'patterns': set(),
        'domains': set(),
        'sources': []
    })
    
    if resume:
        progress = load_progress()
        if progress:
            logger.info(f"📂 Resuming from previous run...")
            logger.info(f"   Already processed: {progress['processed_pdfs']}/{progress['total_pdfs']}")
            
            # Restore results and taxonomy
            all_results = progress.get('results', [])
            processed_pdf_paths = {r['filename'] for r in all_results}
            
            # Restore taxonomy expansion
            for test_type, data in progress.get('taxonomy_expansion', {}).items():
                taxonomy_expansion[test_type]['keywords'].update(data.get('keywords', []))
                taxonomy_expansion[test_type]['patterns'].update(data.get('patterns', []))
                taxonomy_expansion[test_type]['domains'].update(data.get('domains', []))
                taxonomy_expansion[test_type]['sources'].extend(data.get('sources', []))
    
    # Load catalog
    try:
        with open('training_data_catalog.json', 'r') as f:
            catalog = json.load(f)
    except:
        logger.error("training_data_catalog.json not found. Run analyze_training_data.py first.")
        return
    
    # Collect all PDFs to process
    all_pdfs_to_process = []
    for folder_name, folder_data in catalog.get('folders', {}).items():
        domain = determine_domain_from_folder(folder_name)
        pdfs = folder_data.get('pdfs', [])
        
        for pdf_info in pdfs:
            pdf_path = pdf_info['path']
            # Skip if already processed
            if pdf_info['name'] not in processed_pdf_paths:
                all_pdfs_to_process.append({
                    'path': pdf_path,
                    'folder': folder_name,
                    'domain': domain,
                    'name': pdf_info['name']
                })
    
    total_pdfs = len(all_pdfs_to_process) + len(processed_pdf_paths)
    remaining = len(all_pdfs_to_process)
    
    logger.info(f"\n📊 PROCESSING PLAN:")
    logger.info(f"   Total PDFs: {total_pdfs}")
    logger.info(f"   Already processed: {len(processed_pdf_paths)}")
    logger.info(f"   Remaining: {remaining}")
    logger.info(f"   Chunk size: {chunk_size}")
    logger.info(f"   Estimated chunks: {(remaining + chunk_size - 1) // chunk_size}")
    logger.info("")
    
    # Process in chunks
    chunk_num = 0
    processed_in_session = 0
    
    for i in range(0, len(all_pdfs_to_process), chunk_size):
        chunk = all_pdfs_to_process[i:i + chunk_size]
        chunk_num += 1
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📦 PROCESSING CHUNK {chunk_num} ({len(chunk)} PDFs)")
        logger.info(f"{'='*60}")
        
        for pdf_info in chunk:
            pdf_path = pdf_info['path']
            domain = pdf_info['domain']
            folder_name = pdf_info['folder']
            
            try:
                result = process_pdf(pdf_path, domain)
                result['folder'] = folder_name
                result['filename'] = pdf_info['name']
                all_results.append(result)
                
                # Aggregate taxonomy data
                for test in result.get('pattern_tests', []):
                    test_type = test.get('test_type', 'unknown')
                    taxonomy_expansion[test_type]['keywords'].update(test.get('keywords', []))
                    taxonomy_expansion[test_type]['patterns'].update(test.get('patterns', []))
                    taxonomy_expansion[test_type]['domains'].add(domain)
                    taxonomy_expansion[test_type]['sources'].append(pdf_info['name'])
                
                processed_in_session += 1
                
                if processed_in_session % 10 == 0:
                    logger.info(f"   ✅ Processed {processed_in_session}/{remaining} in this session...")
                    
            except Exception as e:
                logger.error(f"❌ Error processing {pdf_path}: {e}")
                continue
        
        # Save progress after each chunk
        total_processed = len(processed_pdf_paths) + processed_in_session
        save_progress(all_results, taxonomy_expansion, total_processed, total_pdfs)
        
        logger.info(f"\n✅ Chunk {chunk_num} complete!")
        logger.info(f"   Progress: {total_processed}/{total_pdfs} ({total_processed*100//total_pdfs}%)")
        logger.info(f"   Test types found so far: {len(taxonomy_expansion)}")
    
    # Final save
    logger.info(f"\n💾 Saving final results...")
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump({
            'total_processed': len(processed_pdf_paths) + processed_in_session,
            'total_pdfs': total_pdfs,
            'results': all_results,
            'taxonomy_expansion': {
                k: {
                    'keywords': list(v['keywords']),
                    'patterns': list(v['patterns']),
                    'domains': list(v['domains']),
                    'source_count': len(v['sources'])
                }
                for k, v in taxonomy_expansion.items()
            }
        }, f, indent=2, default=str)
    
    logger.info(f"✅ Final results saved to {OUTPUT_FILE}")
    
    # Generate taxonomy expansion code
    generate_taxonomy_code(taxonomy_expansion)
    
    logger.info(f"\n🎯 FINAL SUMMARY:")
    logger.info(f"   Processed: {len(processed_pdf_paths) + processed_in_session}/{total_pdfs} PDFs")
    logger.info(f"   Test types found: {len(taxonomy_expansion)}")
    logger.info(f"   Taxonomy code: {TAXONOMY_UPDATE_FILE}")

def generate_taxonomy_code(taxonomy_expansion: Dict[str, Any]):
    """Generate Python code to update TEST_TAXONOMY"""
    
    code_lines = [
        "# Auto-generated TEST_TAXONOMY expansion from training PDFs",
        "# Add this to cme_nlp_processor.py TEST_TAXONOMY",
        "",
        "TAXONOMY_EXPANSION = {"
    ]
    
    for test_type, data in sorted(taxonomy_expansion.items()):
        keywords = list(data['keywords'])[:30]  # Limit keywords
        patterns = list(data['patterns'])[:10]  # Limit patterns
        
        code_lines.append(f"    '{test_type}': {{")
        code_lines.append(f"        'keywords': {keywords},")
        code_lines.append(f"        'patterns': {patterns},")
        code_lines.append(f"        'domains': {list(data['domains'])},")
        code_lines.append(f"        'source_count': {len(data['sources'])}")
        code_lines.append("    },")
    
    code_lines.append("}")
    
    with open(TAXONOMY_UPDATE_FILE, 'w') as f:
        f.write('\n'.join(code_lines))
    
    logger.info(f"✅ Taxonomy code saved to {TAXONOMY_UPDATE_FILE}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Process training PDFs in chunks')
    parser.add_argument('--chunk-size', type=int, default=50, help='Number of PDFs per chunk (default: 50)')
    parser.add_argument('--no-resume', action='store_true', help='Start fresh (ignore previous progress)')
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("🎓 PROCESSING ALL TRAINING PDFs (CHUNK MODE)")
    logger.info("=" * 60)
    logger.info("")
    
    if not HAS_PDFPLUMBER and not HAS_PYPDF2:
        logger.error("No PDF libraries available! Install pdfplumber or PyPDF2")
        sys.exit(1)
    
    process_all_pdfs(chunk_size=args.chunk_size, resume=not args.no_resume)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ PROCESSING COMPLETE!")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()

