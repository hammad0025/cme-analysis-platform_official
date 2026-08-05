#!/usr/bin/env python3
"""
Comprehensive PDF Parser for CME Video Recordings Reference Materials

This script parses ALL PDFs in the CME Video Recordings folder, especially
the Reference A-Y folders, extracting full content to create a knowledge base
for CME video analysis.

Categories:
- Reference A: Palpation
- Reference B: Range of Motion (Spine)
- Reference C: Range of Motion (Limbs)
- Reference D: Motor Examination
- Reference E: Sensory Examination
- Reference F: Reflex Examination
- Reference G: Gait Examination
- Reference H: Romberg Test
- Reference I: Coordination Testing
- Reference J: Cranial Nerves
- Reference K: SLR Test
- Reference L: Orthopedic Exam Techniques
- Reference M: Mental Status
- Reference N: Neurologic Tests
- Reference O: Use of Interpreter
- Reference P: Peripheral Pulse Testing
- Reference Q: Cervical Dystonia
- Reference R: RSD/CRPS
- Reference S: AMA 6th Edition Diagnosis Based Impairment
- Reference T: Objective vs Subjective Findings
- Reference U: Waddell's Signs
- Reference V: Telemedicine Exam
- Reference W: Leg Length Discrepancy
- Reference X: Pain Behavior
- Reference Y: Saccades, Convergence, Head Thrust Test
"""

import os
import sys
import json
import logging
import time
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cme_reference_parsing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# PDF extraction libraries
try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False
    logger.warning("PyPDF2 not installed. Run: pip install PyPDF2")

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    logger.warning("pdfplumber not installed. Run: pip install pdfplumber")

# Reference category mappings
REFERENCE_CATEGORIES = {
    'Reference A': {
        'name': 'Palpation',
        'exam_type': 'physical_examination',
        'description': 'Palpation techniques, tender points, and fibromyalgia assessment',
        'related_tests': ['palpation', 'tender_points', 'trigger_points', 'fibromyalgia_assessment']
    },
    'Reference B': {
        'name': 'Range of Motion - Spine',
        'exam_type': 'range_of_motion',
        'description': 'Cervical, thoracic, and lumbar spine ROM testing including inclinometry',
        'related_tests': ['cervical_rom', 'thoracic_rom', 'lumbar_rom', 'inclinometry', 'goniometry']
    },
    'Reference C': {
        'name': 'Range of Motion - Limbs',
        'exam_type': 'range_of_motion',
        'description': 'Upper and lower extremity joint ROM testing',
        'related_tests': ['shoulder_rom', 'elbow_rom', 'wrist_rom', 'hip_rom', 'knee_rom', 'ankle_rom']
    },
    'Reference D': {
        'name': 'Motor Examination',
        'exam_type': 'neurological',
        'description': 'Muscle strength testing, grip strength, manual muscle testing (MMT)',
        'related_tests': ['manual_muscle_testing', 'grip_strength', 'muscle_grading', 'motor_assessment']
    },
    'Reference E': {
        'name': 'Sensory Examination',
        'exam_type': 'neurological',
        'description': 'Light touch, pinprick, vibration, proprioception testing',
        'related_tests': ['light_touch', 'pinprick', 'vibration_sense', 'proprioception', 'two_point_discrimination']
    },
    'Reference F': {
        'name': 'Reflex Examination',
        'exam_type': 'neurological',
        'description': 'Deep tendon reflexes, pathological reflexes (Babinski, Hoffman)',
        'related_tests': ['deep_tendon_reflexes', 'babinski', 'hoffman', 'clonus', 'jaw_jerk']
    },
    'Reference G': {
        'name': 'Gait Examination',
        'exam_type': 'functional',
        'description': 'Gait observation, tandem gait, heel/toe walking',
        'related_tests': ['gait_observation', 'tandem_gait', 'heel_walking', 'toe_walking', 'ten_step_gait']
    },
    'Reference H': {
        'name': 'Romberg Test',
        'exam_type': 'neurological',
        'description': 'Balance and proprioception testing',
        'related_tests': ['romberg', 'sharpened_romberg', 'balance_testing']
    },
    'Reference I': {
        'name': 'Coordination Testing',
        'exam_type': 'neurological',
        'description': 'Finger-to-nose, heel-to-shin, rapid alternating movements',
        'related_tests': ['finger_to_nose', 'heel_to_shin', 'rapid_alternating_movements', 'bess_test', 'dysdiadochokinesia']
    },
    'Reference J': {
        'name': 'Cranial Nerves',
        'exam_type': 'neurological',
        'description': 'All 12 cranial nerve assessments',
        'related_tests': ['cranial_nerve_exam', 'pupillary_response', 'facial_nerve', 'extraocular_movements']
    },
    'Reference K': {
        'name': 'SLR Test',
        'exam_type': 'orthopedic',
        'description': 'Straight leg raise test for lumbar radiculopathy',
        'related_tests': ['straight_leg_raise', 'slr', 'lasegue', 'seated_slr', 'crossed_slr']
    },
    'Reference L': {
        'name': 'Orthopedic Exam Techniques',
        'exam_type': 'orthopedic',
        'description': 'Special orthopedic tests for joints and ligaments',
        'related_tests': ['lachman', 'mcmurray', 'shoulder_tests', 'knee_tests', 'hip_tests']
    },
    'Reference M': {
        'name': 'Mental Status',
        'exam_type': 'cognitive',
        'description': 'MMSE, MoCA, mental status examination',
        'related_tests': ['mmse', 'moca', 'mental_status_exam', 'orientation', 'memory_testing']
    },
    'Reference N': {
        'name': 'Neurologic Tests',
        'exam_type': 'neurological',
        'description': 'Spurling, Lhermitte, Phalen, and other neurologic tests',
        'related_tests': ['spurling', 'lhermitte', 'phalen', 'tinel', 'myelopathy_test']
    },
    'Reference O': {
        'name': 'Use of Interpreter',
        'exam_type': 'procedural',
        'description': 'Guidelines for medical examination with interpreter',
        'related_tests': ['interpreter_use', 'language_assessment']
    },
    'Reference P': {
        'name': 'Peripheral Pulse Testing',
        'exam_type': 'vascular',
        'description': 'Peripheral vascular examination and pulse assessment',
        'related_tests': ['pulse_testing', 'capillary_refill', 'vascular_assessment']
    },
    'Reference Q': {
        'name': 'Cervical Dystonia',
        'exam_type': 'movement_disorder',
        'description': 'Assessment of cervical dystonia and torticollis',
        'related_tests': ['cervical_dystonia', 'torticollis_assessment']
    },
    'Reference R': {
        'name': 'RSD/CRPS',
        'exam_type': 'pain_syndrome',
        'description': 'Complex Regional Pain Syndrome diagnosis and Budapest criteria',
        'related_tests': ['crps_assessment', 'budapest_criteria', 'thermography', 'allodynia_testing']
    },
    'Reference S': {
        'name': 'AMA 6th Edition DBI',
        'exam_type': 'impairment',
        'description': 'AMA Guides 6th Edition Diagnosis-Based Impairment grids',
        'related_tests': ['impairment_rating', 'dbi_assessment', 'ama_guides']
    },
    'Reference T': {
        'name': 'Objective vs Subjective Findings',
        'exam_type': 'assessment',
        'description': 'Distinguishing objective from subjective examination findings',
        'related_tests': ['objective_findings', 'subjective_findings', 'clinical_correlation']
    },
    'Reference U': {
        'name': "Waddell's Signs",
        'exam_type': 'behavioral',
        'description': 'Non-organic signs in low back pain assessment',
        'related_tests': ['waddell_signs', 'non_organic_signs', 'symptom_magnification']
    },
    'Reference V': {
        'name': 'Telemedicine Exam',
        'exam_type': 'procedural',
        'description': 'Neurologic examination via telemedicine',
        'related_tests': ['telemedicine_neuro', 'virtual_examination']
    },
    'Reference W': {
        'name': 'Leg Length Discrepancy',
        'exam_type': 'orthopedic',
        'description': 'Assessment of leg length difference',
        'related_tests': ['leg_length_measurement', 'pelvic_obliquity']
    },
    'Reference X': {
        'name': 'Pain Behavior',
        'exam_type': 'behavioral',
        'description': 'Assessment of pain behaviors and illness behavior',
        'related_tests': ['pain_behavior', 'illness_behavior', 'pain_assessment']
    },
    'Reference Y': {
        'name': 'Saccades, Convergence, Head Thrust',
        'exam_type': 'vestibular_ocular',
        'description': 'Eye movement testing, vestibular function',
        'related_tests': ['saccades', 'convergence_testing', 'head_thrust', 'vestibular_exam']
    }
}

# Subject area categories
SUBJECT_CATEGORIES = {
    'knee': {
        'name': 'Knee Injuries and Pathology',
        'description': 'ACL, meniscus, patella, knee examination'
    },
    'spine': {
        'name': 'Spine Pathology',
        'description': 'Disc herniation, radiculopathy, facet joints, causation'
    },
    'tbi': {
        'name': 'Traumatic Brain Injury',
        'description': 'TBI diagnosis, prognosis, imaging, sequelae'
    },
    'pain': {
        'name': 'Pain Syndromes',
        'description': 'Chronic pain, fibromyalgia, central sensitization'
    },
    'ortho': {
        'name': 'Orthopedic Examination',
        'description': 'General orthopedic examination techniques'
    },
    'neuropsych': {
        'name': 'Neuropsychology',
        'description': 'Neuropsychological assessment after TBI'
    }
}


def extract_text_pypdf2(pdf_path: Path, max_pages: int = 100) -> Tuple[str, int]:
    """Extract text using PyPDF2"""
    text_parts = []
    page_count = 0
    
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            page_count = len(reader.pages)
            for i, page in enumerate(reader.pages[:max_pages]):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"\n--- Page {i+1} ---\n{page_text}")
                except Exception as e:
                    logger.debug(f"Error on page {i}: {e}")
                    continue
    except Exception as e:
        logger.error(f"PyPDF2 error on {pdf_path.name}: {e}")
    
    return '\n'.join(text_parts), page_count


def extract_text_pdfplumber(pdf_path: Path, max_pages: int = 100) -> Tuple[str, int]:
    """Extract text using pdfplumber (better quality)"""
    text_parts = []
    page_count = 0
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            for i, page in enumerate(pdf.pages[:max_pages]):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"\n--- Page {i+1} ---\n{page_text}")
                    
                    # Also try to extract tables
                    tables = page.extract_tables()
                    for table in tables:
                        if table:
                            table_text = '\n'.join([' | '.join([str(cell) if cell else '' for cell in row]) for row in table if row])
                            if table_text.strip():
                                text_parts.append(f"\n[TABLE]\n{table_text}\n[/TABLE]")
                except Exception as e:
                    logger.debug(f"Error on page {i}: {e}")
                    continue
    except Exception as e:
        logger.error(f"pdfplumber error on {pdf_path.name}: {e}")
    
    return '\n'.join(text_parts), page_count


def extract_text_from_pdf(pdf_path: Path, max_pages: int = 100) -> Dict[str, Any]:
    """Extract text from PDF using best available method"""
    text = ""
    page_count = 0
    method = "none"
    
    # Try pdfplumber first (better quality)
    if HAS_PDFPLUMBER:
        text, page_count = extract_text_pdfplumber(pdf_path, max_pages)
        if text and len(text) > 100:
            method = "pdfplumber"
    
    # Fallback to PyPDF2 if needed
    if (not text or len(text) < 100) and HAS_PYPDF2:
        text, page_count = extract_text_pypdf2(pdf_path, max_pages)
        if text:
            method = "pypdf2"
    
    return {
        'text': text,
        'page_count': page_count,
        'extraction_method': method,
        'char_count': len(text) if text else 0
    }


def determine_reference_category(path: Path) -> Optional[Dict[str, Any]]:
    """Determine which reference category (A-Y) a file belongs to"""
    path_str = str(path)
    
    for ref_key, ref_data in REFERENCE_CATEGORIES.items():
        if ref_key.lower().replace(' ', '') in path_str.lower().replace(' ', ''):
            return {
                'reference_id': ref_key,
                **ref_data
            }
    
    # Check by letter in folder name
    folder_match = re.search(r'Reference\s+([A-Y])\s*[-–]', path_str, re.IGNORECASE)
    if folder_match:
        letter = folder_match.group(1).upper()
        ref_key = f'Reference {letter}'
        if ref_key in REFERENCE_CATEGORIES:
            return {
                'reference_id': ref_key,
                **REFERENCE_CATEGORIES[ref_key]
            }
    
    return None


def determine_subject_category(path: Path) -> Optional[Dict[str, Any]]:
    """Determine subject category for non-reference PDFs"""
    path_str = str(path).lower()
    
    for subject_key, subject_data in SUBJECT_CATEGORIES.items():
        if subject_key in path_str:
            return {
                'subject_id': subject_key,
                **subject_data
            }
    
    return None


def extract_key_concepts(text: str) -> List[str]:
    """Extract key medical concepts from text"""
    concepts = []
    
    # Medical examination terms
    exam_patterns = [
        r'range\s+of\s+motion',
        r'deep\s+tendon\s+reflex',
        r'manual\s+muscle\s+test',
        r'sensory\s+exam',
        r'cranial\s+nerve',
        r'gait\s+analysis',
        r'romberg\s+test',
        r'straight\s+leg\s+raise',
        r'palpation',
        r'inclinometer',
        r'goniometer',
        r'grip\s+strength',
        r'spurling\s+test',
        r'lhermitte',
        r'babinski',
        r'hoffman',
        r'moca',
        r'mmse',
        r'waddell',
        r'crps',
        r'radiculopathy',
        r'myelopathy',
        r'dermatome',
        r'myotome'
    ]
    
    text_lower = text.lower()
    for pattern in exam_patterns:
        if re.search(pattern, text_lower):
            concepts.append(pattern.replace(r'\s+', ' '))
    
    return list(set(concepts))


def extract_citation_info(text: str) -> Dict[str, Any]:
    """Extract citation information from academic PDFs"""
    citation = {}
    
    # Try to find DOI
    doi_match = re.search(r'10\.\d{4,}/[^\s]+', text)
    if doi_match:
        citation['doi'] = doi_match.group(0)
    
    # Try to find year
    year_match = re.search(r'(?:19|20)\d{2}', text[:2000])
    if year_match:
        citation['year'] = year_match.group(0)
    
    # Try to find author (first author)
    author_patterns = [
        r'([A-Z][a-z]+(?:\s[A-Z]\.?)*)\s+et\s+al',
        r'Author[s]?:\s*([A-Z][a-z]+)',
    ]
    for pattern in author_patterns:
        match = re.search(pattern, text[:3000])
        if match:
            citation['first_author'] = match.group(1)
            break
    
    return citation


def process_pdf(pdf_path: Path) -> Dict[str, Any]:
    """Process a single PDF file"""
    logger.info(f"Processing: {pdf_path.name}")
    
    result = {
        'filename': pdf_path.name,
        'path': str(pdf_path),
        'relative_path': str(pdf_path.relative_to(pdf_path.parts[0])) if len(pdf_path.parts) > 1 else str(pdf_path),
        'processed_at': datetime.now().isoformat(),
        'reference_category': None,
        'subject_category': None,
        'content': None,
        'metadata': {},
        'error': None
    }
    
    # Determine categories
    ref_cat = determine_reference_category(pdf_path)
    if ref_cat:
        result['reference_category'] = ref_cat
    
    subj_cat = determine_subject_category(pdf_path)
    if subj_cat:
        result['subject_category'] = subj_cat
    
    # Extract text
    try:
        extraction = extract_text_from_pdf(pdf_path)
        
        if extraction['text'] and len(extraction['text']) > 50:
            result['content'] = {
                'text': extraction['text'],
                'page_count': extraction['page_count'],
                'char_count': extraction['char_count'],
                'extraction_method': extraction['extraction_method']
            }
            
            # Extract key concepts
            result['metadata']['key_concepts'] = extract_key_concepts(extraction['text'])
            
            # Extract citation info
            result['metadata']['citation'] = extract_citation_info(extraction['text'])
            
            # Extract summary (first 500 chars after any header)
            text_clean = re.sub(r'^.*?abstract', '', extraction['text'][:5000], flags=re.IGNORECASE | re.DOTALL)
            if not text_clean:
                text_clean = extraction['text']
            result['metadata']['summary'] = text_clean[:1000].strip()
            
        else:
            result['error'] = 'No text extracted or text too short'
            
    except Exception as e:
        result['error'] = str(e)
        logger.error(f"Error processing {pdf_path.name}: {e}")
    
    return result


def find_all_pdfs(base_path: Path) -> List[Path]:
    """Find all PDF files in the CME Video Recordings folder"""
    pdfs = []
    
    for pdf_file in base_path.rglob('*.pdf'):
        # Skip any system files
        if pdf_file.name.startswith('.'):
            continue
        pdfs.append(pdf_file)
    
    # Also check for .PDF (uppercase)
    for pdf_file in base_path.rglob('*.PDF'):
        if pdf_file.name.startswith('.'):
            continue
        if pdf_file not in pdfs:
            pdfs.append(pdf_file)
    
    return sorted(pdfs, key=lambda p: str(p))


def generate_knowledge_base(results: List[Dict], output_path: Path):
    """Generate structured knowledge base from processed PDFs"""
    
    knowledge_base = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'total_pdfs_processed': len(results),
            'successful_extractions': sum(1 for r in results if r.get('content')),
            'failed_extractions': sum(1 for r in results if r.get('error'))
        },
        'reference_materials': {},  # Organized by Reference A-Y
        'subject_materials': {},    # Organized by subject area
        'exam_techniques': {},      # Extracted examination techniques
        'medical_tests': {},        # Specific medical test information
    }
    
    # Organize by reference category
    for ref_id in REFERENCE_CATEGORIES.keys():
        knowledge_base['reference_materials'][ref_id] = {
            **REFERENCE_CATEGORIES[ref_id],
            'documents': []
        }
    
    # Organize by subject category
    for subj_id in SUBJECT_CATEGORIES.keys():
        knowledge_base['subject_materials'][subj_id] = {
            **SUBJECT_CATEGORIES[subj_id],
            'documents': []
        }
    
    # Populate from results
    for result in results:
        if result.get('error') and not result.get('content'):
            continue
        
        doc_entry = {
            'filename': result['filename'],
            'path': result['path'],
            'summary': result.get('metadata', {}).get('summary', ''),
            'key_concepts': result.get('metadata', {}).get('key_concepts', []),
            'citation': result.get('metadata', {}).get('citation', {}),
            'page_count': result.get('content', {}).get('page_count', 0),
            'char_count': result.get('content', {}).get('char_count', 0)
        }
        
        # Add to reference category if applicable
        if result.get('reference_category'):
            ref_id = result['reference_category']['reference_id']
            if ref_id in knowledge_base['reference_materials']:
                knowledge_base['reference_materials'][ref_id]['documents'].append(doc_entry)
        
        # Add to subject category if applicable
        if result.get('subject_category'):
            subj_id = result['subject_category']['subject_id']
            if subj_id in knowledge_base['subject_materials']:
                knowledge_base['subject_materials'][subj_id]['documents'].append(doc_entry)
        
        # Extract and aggregate exam techniques
        for concept in result.get('metadata', {}).get('key_concepts', []):
            if concept not in knowledge_base['exam_techniques']:
                knowledge_base['exam_techniques'][concept] = {
                    'name': concept.replace('\\s+', ' ').title(),
                    'sources': []
                }
            knowledge_base['exam_techniques'][concept]['sources'].append(result['filename'])
    
    # Calculate statistics
    knowledge_base['statistics'] = {
        'reference_categories_populated': sum(1 for ref in knowledge_base['reference_materials'].values() if ref['documents']),
        'subject_categories_populated': sum(1 for subj in knowledge_base['subject_materials'].values() if subj['documents']),
        'total_exam_techniques': len(knowledge_base['exam_techniques']),
        'documents_by_category': {
            ref_id: len(data['documents']) 
            for ref_id, data in knowledge_base['reference_materials'].items()
        }
    }
    
    # Save knowledge base
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(knowledge_base, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Knowledge base saved to {output_path}")
    return knowledge_base


def main():
    """Main processing function"""
    print("=" * 70)
    print("🏥 CME VIDEO RECORDINGS - COMPREHENSIVE PDF PARSER")
    print("=" * 70)
    print("")
    
    # Define paths
    base_path = Path("/Users/hammadhaque/Documents/cme-analysis-platform/CME Video Recordings")
    output_dir = Path("/Users/hammadhaque/Documents/cme-analysis-platform")
    
    if not base_path.exists():
        logger.error(f"Base path does not exist: {base_path}")
        sys.exit(1)
    
    # Check for PDF libraries
    if not HAS_PYPDF2 and not HAS_PDFPLUMBER:
        logger.error("No PDF extraction library available. Install PyPDF2 or pdfplumber.")
        print("\nInstall required libraries:")
        print("  pip install PyPDF2 pdfplumber")
        sys.exit(1)
    
    print(f"📁 Base path: {base_path}")
    print(f"📚 PDF libraries: PyPDF2={HAS_PYPDF2}, pdfplumber={HAS_PDFPLUMBER}")
    print("")
    
    # Find all PDFs
    print("🔍 Scanning for PDF files...")
    all_pdfs = find_all_pdfs(base_path)
    print(f"   Found {len(all_pdfs)} PDF files")
    print("")
    
    # Categorize PDFs
    reference_pdfs = []
    subject_pdfs = []
    other_pdfs = []
    
    for pdf in all_pdfs:
        ref_cat = determine_reference_category(pdf)
        subj_cat = determine_subject_category(pdf)
        
        if ref_cat:
            reference_pdfs.append((pdf, ref_cat))
        elif subj_cat:
            subject_pdfs.append((pdf, subj_cat))
        else:
            other_pdfs.append(pdf)
    
    print("📊 PDF Distribution:")
    print(f"   Reference A-Y: {len(reference_pdfs)} PDFs")
    print(f"   Subject Areas: {len(subject_pdfs)} PDFs")
    print(f"   Other/Root:    {len(other_pdfs)} PDFs")
    print("")
    
    # Load existing progress if available
    progress_file = output_dir / "cme_reference_parsing_progress.json"
    results = []
    processed_paths = set()
    
    if progress_file.exists():
        try:
            with open(progress_file, 'r') as f:
                progress_data = json.load(f)
                results = progress_data.get('results', [])
                processed_paths = {r['path'] for r in results}
                print(f"📂 Resuming from previous run: {len(results)} already processed")
        except Exception as e:
            logger.warning(f"Could not load progress file: {e}")
    
    # Filter out already processed
    pdfs_to_process = [p for p in all_pdfs if str(p) not in processed_paths]
    print(f"🎯 PDFs to process: {len(pdfs_to_process)}")
    print("")
    
    if not pdfs_to_process:
        print("✅ All PDFs already processed!")
    else:
        # Process PDFs
        total = len(pdfs_to_process)
        chunk_size = 25
        
        for i, pdf_path in enumerate(pdfs_to_process):
            try:
                result = process_pdf(pdf_path)
                results.append(result)
                
                status = "✅" if result.get('content') else "⚠️"
                ref_id = result.get('reference_category', {}).get('reference_id', '')
                print(f"  [{i+1}/{total}] {status} {pdf_path.name[:50]} {ref_id}")
                
            except Exception as e:
                logger.error(f"Failed to process {pdf_path.name}: {e}")
                results.append({
                    'filename': pdf_path.name,
                    'path': str(pdf_path),
                    'error': str(e)
                })
            
            # Save progress every chunk_size PDFs
            if (i + 1) % chunk_size == 0:
                progress_data = {
                    'total_pdfs': len(all_pdfs),
                    'processed_pdfs': len(results),
                    'last_updated': datetime.now().isoformat(),
                    'results': results
                }
                with open(progress_file, 'w', encoding='utf-8') as f:
                    json.dump(progress_data, f, indent=2, ensure_ascii=False)
                print(f"\n💾 Progress saved: {len(results)}/{len(all_pdfs)} PDFs\n")
    
    # Save final progress
    progress_data = {
        'total_pdfs': len(all_pdfs),
        'processed_pdfs': len(results),
        'completed_at': datetime.now().isoformat(),
        'results': results
    }
    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(progress_data, f, indent=2, ensure_ascii=False)
    
    # Generate knowledge base
    print("")
    print("=" * 70)
    print("📚 GENERATING KNOWLEDGE BASE")
    print("=" * 70)
    
    kb_output = output_dir / "cme_reference_knowledge_base.json"
    knowledge_base = generate_knowledge_base(results, kb_output)
    
    # Print summary
    print("")
    print("=" * 70)
    print("📊 PROCESSING SUMMARY")
    print("=" * 70)
    print(f"  Total PDFs found:          {len(all_pdfs)}")
    print(f"  Successfully processed:    {knowledge_base['metadata']['successful_extractions']}")
    print(f"  Failed extractions:        {knowledge_base['metadata']['failed_extractions']}")
    print(f"  Reference categories:      {knowledge_base['statistics']['reference_categories_populated']}/25")
    print(f"  Exam techniques found:     {knowledge_base['statistics']['total_exam_techniques']}")
    print("")
    print("📁 Output files:")
    print(f"   - {progress_file}")
    print(f"   - {kb_output}")
    print("")
    print("🎉 Processing complete!")
    
    return results, knowledge_base


if __name__ == "__main__":
    main()

