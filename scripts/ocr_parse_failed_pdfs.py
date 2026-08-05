#!/usr/bin/env python3
"""
OCR Parser for Failed PDFs
Uses Tesseract OCR to extract text from scanned PDFs that failed regular parsing.
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# OCR imports
try:
    import pytesseract
    from pdf2image import convert_from_path
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    print("ERROR: Need pytesseract and pdf2image")
    print("Install with: pip install pytesseract pdf2image")
    sys.exit(1)

# Also try PyMuPDF for hybrid approach
try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_PATH = "/Users/hammadhaque/Documents/cme-analysis-platform"


def ocr_pdf(pdf_path: str, max_pages: int = 50) -> str:
    """Extract text from PDF using OCR"""
    try:
        # Convert PDF to images
        images = convert_from_path(pdf_path, dpi=200, first_page=1, last_page=max_pages)
        
        text_parts = []
        for i, image in enumerate(images):
            # Run OCR on each page
            page_text = pytesseract.image_to_string(image)
            if page_text.strip():
                text_parts.append(f"--- Page {i+1} ---\n{page_text}")
        
        return "\n\n".join(text_parts)
    except Exception as e:
        logger.error(f"OCR error for {pdf_path}: {e}")
        return ""


def parse_with_ocr(pdf_path: str) -> Dict[str, Any]:
    """Parse a PDF using OCR and return structured data"""
    filename = os.path.basename(pdf_path)
    logger.info(f"OCR parsing: {filename}")
    
    try:
        text = ocr_pdf(pdf_path)
        
        if not text or len(text) < 50:
            return {
                'filename': filename,
                'path': pdf_path,
                'success': False,
                'error': 'OCR produced no text',
                'char_count': 0
            }
        
        # Determine category from filename/path
        category = 'general'
        path_lower = pdf_path.lower()
        
        if 'ama' in path_lower or 'inclinometry' in path_lower:
            category = 'ama_guides'
        elif 'aaos' in path_lower:
            category = 'aaos_guidelines'
        elif 'tbi' in path_lower or 'brain' in path_lower:
            category = 'tbi'
        elif 'spine' in path_lower or 'lumbar' in path_lower or 'cervical' in path_lower:
            category = 'spine'
        elif 'ghd' in path_lower or 'pituitary' in path_lower or 'hormone' in path_lower:
            category = 'neuroendocrine'
        elif 'cranial' in path_lower or 'cn injury' in path_lower:
            category = 'cranial_nerve'
        
        return {
            'filename': filename,
            'path': pdf_path,
            'success': True,
            'char_count': len(text),
            'category': category,
            'content': text[:50000],  # Limit content size
            'parsed_at': datetime.now().isoformat(),
            'method': 'ocr'
        }
        
    except Exception as e:
        logger.error(f"Failed to OCR parse {filename}: {e}")
        return {
            'filename': filename,
            'path': pdf_path,
            'success': False,
            'error': str(e)
        }


def main():
    """Parse all failed PDFs with OCR"""
    
    # Load existing parsing log
    log_path = os.path.join(BASE_PATH, 'cme_complete_parsing_log.json')
    with open(log_path, 'r') as f:
        log = json.load(f)
    
    # Get failed PDFs
    failures = [r for r in log.get('results', []) if not r.get('success', True)]
    
    # Deduplicate by path
    seen_paths = set()
    unique_failures = []
    for f in failures:
        path = f.get('path', '')
        if path and path not in seen_paths:
            seen_paths.add(path)
            unique_failures.append(f)
    
    logger.info(f"Found {len(unique_failures)} unique failed PDFs to OCR parse")
    
    # Parse each with OCR
    ocr_results = []
    success_count = 0
    
    for i, failure in enumerate(unique_failures):
        pdf_path = failure.get('path', '')
        if not pdf_path or not os.path.exists(pdf_path):
            logger.warning(f"Path not found: {pdf_path}")
            continue
        
        logger.info(f"[{i+1}/{len(unique_failures)}] Processing: {os.path.basename(pdf_path)}")
        result = parse_with_ocr(pdf_path)
        ocr_results.append(result)
        
        if result.get('success'):
            success_count += 1
            logger.info(f"  ✓ Success: {result.get('char_count', 0)} chars")
        else:
            logger.warning(f"  ✗ Failed: {result.get('error', 'unknown')}")
    
    # Save OCR results
    ocr_output_path = os.path.join(BASE_PATH, 'cme_ocr_parsed.json')
    with open(ocr_output_path, 'w') as f:
        json.dump({
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'total_processed': len(ocr_results),
                'successful': success_count,
                'failed': len(ocr_results) - success_count
            },
            'results': ocr_results
        }, f, indent=2)
    
    logger.info(f"\n=== OCR PARSING COMPLETE ===")
    logger.info(f"Processed: {len(ocr_results)}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {len(ocr_results) - success_count}")
    logger.info(f"Results saved to: {ocr_output_path}")
    
    # Update knowledge base with OCR results
    kb_path = os.path.join(BASE_PATH, 'cme_complete_knowledge_base.json')
    with open(kb_path, 'r') as f:
        kb = json.load(f)
    
    # Add OCR parsed content
    for result in ocr_results:
        if result.get('success') and result.get('content'):
            category = result.get('category', 'general')
            if category not in kb.get('by_category', {}):
                kb['by_category'][category] = []
            kb['by_category'][category].append(result.get('filename'))
            
            # Update counts
            kb['metadata']['successful_parses'] = kb['metadata'].get('successful_parses', 0) + 1
            kb['metadata']['failed_parses'] = max(0, kb['metadata'].get('failed_parses', 0) - 1)
    
    with open(kb_path, 'w') as f:
        json.dump(kb, f, indent=2)
    
    logger.info(f"Updated knowledge base: {kb_path}")


if __name__ == '__main__':
    main()
