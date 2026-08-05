#!/usr/bin/env python3
"""
===================================================================
COMPREHENSIVE CME PDF PARSER - ALL DOCUMENTS
===================================================================

This script parses ALL PDFs in the CME Video Recordings folder,
not just the Reference A-Y folders.

Additional folders to parse:
- Spine Oregon Hunter/ (100+ PDFs)
- tbi Oregon Hunter/ (200+ PDFs)
- knee Oregon Hunter/
- Pain Oregon Hunter/ (60+ PDFs)
- redlined exhibits Oregon Hunter/ (300+ PDFs)
- Neuropsych TBI Oregon Hunter/
- ortho exam Oregon Hunter/
- Plus top-level PDFs

Outputs:
1. cme_complete_knowledge_base.json - All indexed content
2. cme_complete_parsing_log.json - Parsing progress
3. cme_medical_concepts_index.json - All medical concepts found
"""

import os
import sys
import json
import re
import logging
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Optional, Set, Tuple
import argparse

# PDF parsing
try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    print("PyMuPDF not available, trying pdfplumber...")

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

if not HAS_FITZ and not HAS_PDFPLUMBER:
    print("ERROR: Need either PyMuPDF or pdfplumber")
    print("Install with: pip install PyMuPDF pdfplumber")
    sys.exit(1)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_PATH = "/Users/hammadhaque/Documents/cme-analysis-platform/CME Video Recordings"

# Categories to detect from folder names and content
CATEGORY_PATTERNS = {
    # Spine Categories
    'spine_disc_herniation': [
        r'disc herniat', r'herniated disc', r'hnp', r'disc extrusion',
        r'disc protrusion', r'annular tear', r'disc bulge'
    ],
    'spine_radiculopathy': [
        r'radiculopathy', r'radicular', r'dermatomal', r'myotome',
        r'nerve root', r'sciatica'
    ],
    'spine_facet': [
        r'facet joint', r'facet syndrome', r'zygapophyseal', r'facet pain'
    ],
    'spine_degeneration': [
        r'degenerative', r'spondylosis', r'ddd', r'degenerative disc',
        r'osteophyte', r'disc desiccation'
    ],
    'spine_whiplash': [
        r'whiplash', r'wad', r'cervical strain', r'neck strain',
        r'acceleration-deceleration'
    ],
    'spine_causation': [
        r'causation', r'bradford hill', r'causal', r'mechanism of injury'
    ],
    
    # TBI Categories
    'tbi_diagnosis': [
        r'tbi', r'traumatic brain', r'mtbi', r'mild traumatic',
        r'concussion', r'head injury', r'brain injury'
    ],
    'tbi_imaging': [
        r'mri brain', r'ct brain', r'dti', r'diffusion tensor',
        r'white matter', r'lesion', r'contusion', r'dai',
        r'diffuse axonal', r'hemosiderin'
    ],
    'tbi_cognitive': [
        r'cognitive', r'neuropsychological', r'memory', r'attention',
        r'executive function', r'mmse', r'moca'
    ],
    'tbi_ptsd': [
        r'ptsd', r'post-traumatic stress', r'anxiety', r'depression',
        r'psychiatric'
    ],
    'tbi_vestibular': [
        r'vestibular', r'dizziness', r'vertigo', r'balance',
        r'bppv', r'nystagmus'
    ],
    'tbi_vision': [
        r'visual', r'optic', r'convergence', r'oculomotor',
        r'pupil', r'iton', r'cranial nerve'
    ],
    'tbi_endocrine': [
        r'endocrine', r'pituitary', r'hypopituitarism', r'hormone',
        r'testosterone', r'cortisol', r'growth hormone'
    ],
    'tbi_prognosis': [
        r'prognosis', r'outcome', r'recovery', r'persistent',
        r'chronic', r'long-term'
    ],
    
    # Pain Categories
    'chronic_pain': [
        r'chronic pain', r'persistent pain', r'fibromyalgia',
        r'widespread pain', r'central sensitization'
    ],
    'pain_behavior': [
        r'pain behavior', r'waddell', r'malingering', r'non-organic',
        r'functional overlay'
    ],
    'crps': [
        r'crps', r'complex regional pain', r'rsd', r'reflex sympathetic',
        r'allodynia', r'hyperalgesia'
    ],
    
    # Examination Categories
    'range_of_motion': [
        r'range of motion', r'rom', r'goniometer', r'inclinometer',
        r'flexion', r'extension', r'rotation', r'lateral bending'
    ],
    'neurological_exam': [
        r'neurological exam', r'neuro exam', r'reflex', r'dtr',
        r'sensory', r'motor', r'strength'
    ],
    'special_tests': [
        r'spurling', r'slr', r'straight leg raise', r'lhermitte',
        r'hoffmann', r'babinski', r'romberg'
    ],
    
    # Other Categories
    'knee_injury': [
        r'knee', r'acl', r'mcl', r'meniscus', r'patella',
        r'ligament', r'arthroplasty'
    ],
    'shoulder_injury': [
        r'shoulder', r'rotator cuff', r'labrum', r'impingement'
    ],
    'imaging_general': [
        r'mri', r'ct scan', r'x-ray', r'imaging', r'radiology'
    ],
    'causation_analysis': [
        r'causation', r'causal', r'mechanism', r'etiology'
    ]
}

# Medical test/procedure patterns
MEDICAL_TEST_PATTERNS = {
    'cervical_rom': [r'cervical\s*(range of motion|rom)', r'neck\s*(rom|range)'],
    'lumbar_rom': [r'lumbar\s*(range of motion|rom)', r'(low back|lower back)\s*rom'],
    'thoracic_rom': [r'thoracic\s*(range of motion|rom)'],
    'goniometry': [r'goniometer', r'goniometry', r'angle\s*measur'],
    'inclinometry': [r'inclinometer', r'inclinometry', r'dual\s*inclinometer'],
    'reflex_testing': [r'deep tendon reflex', r'dtr', r'reflex\s*test', r'reflex\s*hammer'],
    'sensory_exam': [r'sensory\s*exam', r'light touch', r'pinprick', r'vibration\s*sense'],
    'motor_exam': [r'motor\s*exam', r'muscle\s*strength', r'manual\s*muscle', r'grip\s*strength'],
    'spurling_test': [r'spurling', r'foraminal\s*compression'],
    'slr_test': [r'straight leg raise', r'slr', r'las[eè]gue'],
    'romberg_test': [r'romberg', r'balance\s*test'],
    'tandem_gait': [r'tandem\s*gait', r'heel.to.toe'],
    'mmse': [r'mini.mental', r'mmse'],
    'moca': [r'montreal\s*cognitive', r'moca'],
    'cranial_nerve': [r'cranial\s*nerve', r'cn\s*(i{1,3}|iv|v|vi|vii|viii|ix|x|xi|xii)'],
    'pupil_exam': [r'pupil', r'perl', r'perrla'],
    'fundoscopy': [r'fundoscop', r'ophthalmoscop', r'retinal'],
    'babinski': [r'babinski', r'plantar\s*reflex', r'plantar\s*response'],
    'hoffmann': [r'hoffmann', r'hoffman'],
    'clonus': [r'clonus', r'ankle\s*clonus'],
    'palpation': [r'palpation', r'palpate', r'tender\s*point', r'trigger\s*point'],
    'waddell_signs': [r'waddell', r'non.organic\s*sign'],
    'crps_exam': [r'budapest\s*criteria', r'temperature\s*asymmetry', r'allodynia\s*test']
}


# ============================================================================
# PDF EXTRACTION FUNCTIONS
# ============================================================================

def extract_text_fitz(pdf_path: str) -> Tuple[str, int]:
    """Extract text using PyMuPDF."""
    doc = None
    try:
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        text_parts = []
        for page_num in range(page_count):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                text_parts.append(f"--- Page {page_num + 1} ---\n{text}")
        return "\n\n".join(text_parts), page_count
    except Exception as e:
        logger.error(f"PyMuPDF error for {pdf_path}: {e}")
        return "", 0
    finally:
        if doc:
            doc.close()


def extract_text_pdfplumber(pdf_path: str) -> Tuple[str, int]:
    """Extract text using pdfplumber."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text_parts = []
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    text_parts.append(f"--- Page {page_num + 1} ---\n{text}")
            return "\n\n".join(text_parts), len(pdf.pages)
    except Exception as e:
        logger.error(f"pdfplumber error for {pdf_path}: {e}")
        return "", 0


def extract_pdf_text(pdf_path: str) -> Tuple[str, int]:
    """Extract text from PDF using available library."""
    if HAS_FITZ:
        text, pages = extract_text_fitz(pdf_path)
        if text:
            return text, pages
    
    if HAS_PDFPLUMBER:
        return extract_text_pdfplumber(pdf_path)
    
    return "", 0


# ============================================================================
# CATEGORIZATION FUNCTIONS
# ============================================================================

def categorize_by_folder(folder_path: str) -> Dict[str, Any]:
    """Categorize document based on its folder path."""
    folder_lower = folder_path.lower()
    
    categories = {
        'primary_category': None,
        'subcategories': [],
        'folder_path': folder_path
    }
    
    # Check for Reference folders (Reference A - Y)
    ref_match = re.search(r'reference\s+([a-y])\s*-?\s*(.*?)(?:/|$)', folder_lower, re.IGNORECASE)
    if ref_match:
        ref_letter = ref_match.group(1).upper()
        ref_name = ref_match.group(2).strip()
        categories['primary_category'] = f'reference_{ref_letter}'
        categories['reference_id'] = f'Reference {ref_letter}'
        categories['reference_name'] = ref_name
        return categories
    
    # Check other folder patterns
    folder_category_map = {
        'spine': 'spine',
        'tbi': 'tbi',
        'traumatic brain': 'tbi',
        'knee': 'knee',
        'pain': 'pain',
        'redlined': 'evidence_exhibits',
        'neuropsych': 'neuropsych',
        'ortho exam': 'orthopedic_exam',
        'disc': 'disc_pathology',
        'whiplash': 'whiplash',
        'causation': 'causation',
        'radiculopathy': 'radiculopathy',
        'facet': 'facet',
        'imaging': 'imaging',
        'ptsd': 'ptsd',
        'vestibular': 'vestibular',
        'vision': 'vision',
        'endocrine': 'endocrine',
        'prognosis': 'prognosis',
        'delayed': 'delayed_onset',
        'dementia': 'dementia',
        'crps': 'crps',
        'rsd': 'crps'
    }
    
    for pattern, category in folder_category_map.items():
        if pattern in folder_lower:
            if not categories['primary_category']:
                categories['primary_category'] = category
            else:
                categories['subcategories'].append(category)
    
    if not categories['primary_category']:
        categories['primary_category'] = 'general'
    
    return categories


def categorize_by_content(text: str) -> Dict[str, List[str]]:
    """Categorize document based on its content."""
    text_lower = text.lower()
    
    categories_found = defaultdict(list)
    
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                categories_found['content_categories'].append(category)
                break
    
    # Detect specific medical tests mentioned
    tests_found = []
    for test_name, patterns in MEDICAL_TEST_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                tests_found.append(test_name)
                break
    
    categories_found['medical_tests'] = tests_found
    
    return dict(categories_found)


def extract_key_concepts(text: str) -> List[str]:
    """Extract key medical concepts from text."""
    text_lower = text.lower()
    concepts = set()
    
    concept_patterns = {
        # Anatomical
        'cervical spine': [r'cervical\s*spine', r'c-spine', r'neck'],
        'lumbar spine': [r'lumbar\s*spine', r'l-spine', r'low back', r'lower back'],
        'thoracic spine': [r'thoracic\s*spine', r't-spine'],
        
        # Pathology
        'disc herniation': [r'herniat', r'hnp', r'disc\s*extrusion'],
        'radiculopathy': [r'radiculopath'],
        'myelopathy': [r'myelopath'],
        'stenosis': [r'stenosis'],
        'spondylosis': [r'spondylosis'],
        'spondylolisthesis': [r'spondylolisthesis'],
        
        # TBI
        'traumatic brain injury': [r'traumatic brain injury', r'\btbi\b', r'mtbi'],
        'concussion': [r'concussion'],
        'diffuse axonal injury': [r'diffuse axonal', r'\bdai\b'],
        'post-concussion syndrome': [r'post.concussion', r'pcs'],
        
        # Examination
        'range of motion': [r'range of motion', r'\brom\b'],
        'goniometer': [r'goniometer'],
        'inclinometer': [r'inclinometer'],
        'reflex': [r'reflex'],
        
        # Pain
        'chronic pain': [r'chronic pain'],
        'fibromyalgia': [r'fibromyalgia'],
        'crps': [r'\bcrps\b', r'complex regional pain'],
        
        # Imaging
        'mri': [r'\bmri\b', r'magnetic resonance'],
        'ct scan': [r'\bct\b', r'computed tomography'],
        'dti': [r'\bdti\b', r'diffusion tensor'],
        
        # Causation
        'causation': [r'causation', r'causal'],
        'mechanism of injury': [r'mechanism of injury', r'moi'],
        
        # Tests
        'spurling test': [r'spurling'],
        'straight leg raise': [r'straight leg raise', r'\bslr\b'],
        'romberg test': [r'romberg'],
        'babinski': [r'babinski'],
        'hoffmann': [r'hoffmann'],
        'waddell': [r'waddell']
    }
    
    for concept, patterns in concept_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                concepts.add(concept)
                break
    
    return list(concepts)


def extract_citations(text: str) -> Dict[str, Any]:
    """Extract citation information from text."""
    citations = {}
    
    # DOI
    doi_match = re.search(r'doi[:\s]*([^\s]+)', text, re.IGNORECASE)
    if doi_match:
        citations['doi'] = doi_match.group(1)
    
    # Year
    year_match = re.search(r'\b(19[89]\d|20[0-2]\d)\b', text)
    if year_match:
        citations['year'] = year_match.group(1)
    
    # First author
    author_match = re.search(r'([A-Z][a-z]+)\s+(?:et al|and)', text)
    if author_match:
        citations['first_author'] = author_match.group(1)
    
    return citations


# ============================================================================
# MAIN PARSING FUNCTION
# ============================================================================

def parse_pdf(pdf_path: str) -> Dict[str, Any]:
    """Parse a single PDF and extract all relevant information."""
    
    result = {
        'filename': os.path.basename(pdf_path),
        'path': pdf_path,
        'parsed_at': datetime.now().isoformat(),
        'success': False
    }
    
    # Extract text
    text, page_count = extract_pdf_text(pdf_path)
    
    if not text:
        result['error'] = 'Failed to extract text'
        return result
    
    result['success'] = True
    result['page_count'] = page_count
    result['char_count'] = len(text)
    
    # Categorize by folder
    folder_categories = categorize_by_folder(os.path.dirname(pdf_path))
    result.update(folder_categories)
    
    # Categorize by content
    content_categories = categorize_by_content(text)
    result.update(content_categories)
    
    # Extract key concepts
    result['key_concepts'] = extract_key_concepts(text)
    
    # Extract citations
    result['citations'] = extract_citations(text)
    
    # Store summary (first 1000 chars)
    result['summary'] = text[:1000].strip()
    
    # Store full text hash (for deduplication)
    result['content_hash'] = hashlib.md5(text.encode()).hexdigest()
    
    return result


def find_all_pdfs(base_path: str) -> List[str]:
    """Find all PDF files recursively."""
    pdfs = []
    
    for root, dirs, files in os.walk(base_path):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            if file.lower().endswith('.pdf'):
                full_path = os.path.join(root, file)
                pdfs.append(full_path)
    
    return sorted(pdfs)


def build_knowledge_index(results: List[Dict]) -> Dict[str, Any]:
    """Build organized knowledge index from parsed results."""
    
    index = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'total_documents': len(results),
            'successful_parses': sum(1 for r in results if r.get('success')),
            'failed_parses': sum(1 for r in results if not r.get('success'))
        },
        
        # By category
        'by_category': defaultdict(list),
        
        # By medical test
        'by_medical_test': defaultdict(list),
        
        # By key concept
        'by_concept': defaultdict(list),
        
        # Reference materials (Reference A-Y)
        'reference_materials': {},
        
        # All medical tests found
        'all_medical_tests': set(),
        
        # All concepts found
        'all_concepts': set()
    }
    
    for result in results:
        if not result.get('success'):
            continue
        
        filename = result.get('filename', 'unknown')
        primary_cat = result.get('primary_category', 'general')
        
        # Index by category
        index['by_category'][primary_cat].append(filename)
        
        # Index by medical tests
        for test in result.get('medical_tests', []):
            index['by_medical_test'][test].append(filename)
            index['all_medical_tests'].add(test)
        
        # Index by concept
        for concept in result.get('key_concepts', []):
            index['by_concept'][concept].append(filename)
            index['all_concepts'].add(concept)
        
        # Build reference materials section
        ref_id = result.get('reference_id')
        if ref_id:
            if ref_id not in index['reference_materials']:
                index['reference_materials'][ref_id] = {
                    'name': result.get('reference_name', ''),
                    'documents': []
                }
            index['reference_materials'][ref_id]['documents'].append({
                'filename': filename,
                'key_concepts': result.get('key_concepts', []),
                'medical_tests': result.get('medical_tests', [])
            })
    
    # Convert sets to lists for JSON
    index['all_medical_tests'] = sorted(list(index['all_medical_tests']))
    index['all_concepts'] = sorted(list(index['all_concepts']))
    
    # Convert defaultdicts to regular dicts
    index['by_category'] = dict(index['by_category'])
    index['by_medical_test'] = dict(index['by_medical_test'])
    index['by_concept'] = dict(index['by_concept'])
    
    return index


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Parse ALL PDFs in CME Video Recordings')
    parser.add_argument('--output', default='cme_complete_knowledge_base.json',
                        help='Output JSON file')
    parser.add_argument('--log', default='cme_complete_parsing_log.json',
                        help='Parsing log file')
    parser.add_argument('--resume', action='store_true',
                        help='Resume from previous run')
    parser.add_argument('--limit', type=int, default=0,
                        help='Limit number of PDFs to process (0=all)')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("COMPREHENSIVE CME PDF PARSER")
    print("=" * 70)
    print(f"Base path: {BASE_PATH}")
    print()
    
    # Find all PDFs
    print("Scanning for PDFs...")
    all_pdfs = find_all_pdfs(BASE_PATH)
    print(f"Found {len(all_pdfs)} PDF files")
    
    # Load previous progress if resuming
    processed_paths = set()
    results = []
    
    if args.resume and os.path.exists(args.log):
        print(f"Loading previous progress from {args.log}...")
        with open(args.log, 'r') as f:
            log_data = json.load(f)
            results = log_data.get('results', [])
            processed_paths = {r['path'] for r in results}
            print(f"  Resuming from {len(results)} previously processed files")
    
    # Filter to unprocessed
    pdfs_to_process = [p for p in all_pdfs if p not in processed_paths]
    print(f"PDFs to process: {len(pdfs_to_process)}")
    
    if args.limit > 0:
        pdfs_to_process = pdfs_to_process[:args.limit]
        print(f"Limited to {args.limit} PDFs")
    
    # Process PDFs
    print()
    print("Processing PDFs...")
    print("-" * 70)
    
    for i, pdf_path in enumerate(pdfs_to_process):
        relative_path = pdf_path.replace(BASE_PATH, '').lstrip('/')
        print(f"[{i+1}/{len(pdfs_to_process)}] {relative_path[:60]}...", end=' ')
        
        try:
            result = parse_pdf(pdf_path)
            results.append(result)
            
            if result.get('success'):
                concepts_count = len(result.get('key_concepts', []))
                tests_count = len(result.get('medical_tests', []))
                print(f"✓ ({concepts_count} concepts, {tests_count} tests)")
            else:
                print(f"✗ ({result.get('error', 'Unknown error')})")
        
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                'filename': os.path.basename(pdf_path),
                'path': pdf_path,
                'success': False,
                'error': str(e)
            })
        
        # Save progress every 50 PDFs
        if (i + 1) % 50 == 0:
            print(f"\nSaving progress ({len(results)} processed)...")
            with open(args.log, 'w') as f:
                json.dump({
                    'total_pdfs': len(all_pdfs),
                    'processed': len(results),
                    'results': results
                }, f, indent=2)
    
    # Build knowledge index
    print()
    print("=" * 70)
    print("Building knowledge index...")
    knowledge_index = build_knowledge_index(results)
    
    # Save results
    print(f"\nSaving knowledge base to {args.output}...")
    with open(args.output, 'w') as f:
        json.dump(knowledge_index, f, indent=2)
    
    print(f"Saving parsing log to {args.log}...")
    with open(args.log, 'w') as f:
        json.dump({
            'total_pdfs': len(all_pdfs),
            'processed': len(results),
            'results': results
        }, f, indent=2)
    
    # Print summary
    print()
    print("=" * 70)
    print("PARSING COMPLETE")
    print("=" * 70)
    print(f"Total PDFs found: {len(all_pdfs)}")
    print(f"Successfully parsed: {knowledge_index['metadata']['successful_parses']}")
    print(f"Failed to parse: {knowledge_index['metadata']['failed_parses']}")
    print()
    print(f"Categories found: {len(knowledge_index['by_category'])}")
    print(f"Medical tests referenced: {len(knowledge_index['all_medical_tests'])}")
    print(f"Key concepts indexed: {len(knowledge_index['all_concepts'])}")
    print()
    print("Top categories by document count:")
    for cat, docs in sorted(knowledge_index['by_category'].items(), 
                           key=lambda x: len(x[1]), reverse=True)[:10]:
        print(f"  {cat}: {len(docs)} documents")
    print()
    print("Medical tests found:")
    for test in sorted(knowledge_index['all_medical_tests']):
        count = len(knowledge_index['by_medical_test'].get(test, []))
        print(f"  {test}: {count} documents")


if __name__ == '__main__':
    main()

