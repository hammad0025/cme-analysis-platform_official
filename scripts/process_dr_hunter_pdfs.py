#!/usr/bin/env python3
"""
Process Dr. Hunter's PDFs - Extract medical tests and terminology
This script actually reads and processes the PDF files
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any
import logging

# Try to import PDF libraries
try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False
    print("PyPDF2 not installed. Install with: pip install PyPDF2")

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    print("pdfplumber not installed. Install with: pip install pdfplumber")

# Try to import AWS clients
try:
    import boto3
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
    HAS_BEDROCK = True
except Exception as e:
    HAS_BEDROCK = False
    print(f"AWS Bedrock not available: {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF using available libraries"""
    text = ""
    
    # Try pdfplumber first (better quality)
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
    
    # Fallback to PyPDF2
    if HAS_PYPDF2:
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
            return text
        except Exception as e:
            logger.error(f"PyPDF2 failed for {pdf_path}: {e}")
    
    return ""


def extract_tests_with_ai(text: str, domain: str, filename: str) -> List[Dict[str, Any]]:
    """Use AI to extract medical tests from text"""
    if not HAS_BEDROCK:
        logger.warning("AWS Bedrock not available - skipping AI extraction")
        return []
    
    if not text or len(text) < 100:
        return []
    
    # Truncate text if too long
    text_sample = text[:8000]
    
    prompt = f"""You are analyzing medical literature about {domain} to extract test names, procedures, and terminology.

FILENAME: {filename}
DOMAIN: {domain}

TEXT EXCERPT:
{text_sample}

TASK: Extract all medical tests, examination procedures, and related terminology.

For each test/procedure found, return JSON with:
- test_name: Standardized test name (e.g., "Lachman Test", "Straight Leg Raise")
- alternative_names: Other names/synonyms (e.g., ["Lachman's test", "Lachman maneuver"])
- category: Domain category (orthopedic/spine/tbi/neurological)
- keywords: List of keywords/phrases used to describe this test
- procedure_description: Brief description of how test is performed (if mentioned)
- when_indicated: When this test should be performed (if mentioned)

Return ONLY a JSON array, no additional text:
[
  {{
    "test_name": "Test Name",
    "alternative_names": ["synonym1", "synonym2"],
    "category": "domain",
    "keywords": ["keyword1", "keyword2"],
    "procedure_description": "How test is performed",
    "when_indicated": "When to use this test"
  }}
]"""

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
        
        # Try to extract JSON from response
        # AI might wrap JSON in markdown code blocks
        if '```json' in ai_result:
            ai_result = ai_result.split('```json')[1].split('```')[0].strip()
        elif '```' in ai_result:
            ai_result = ai_result.split('```')[1].split('```')[0].strip()
        
        tests = json.loads(ai_result)
        return tests if isinstance(tests, list) else []
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        logger.error(f"AI response: {ai_result[:500]}")
        return []
    except Exception as e:
        logger.error(f"Error in AI extraction: {e}")
        return []


def process_pdf(pdf_path: str, domain: str) -> Dict[str, Any]:
    """Process a single PDF file"""
    logger.info(f"Processing: {pdf_path}")
    
    # Extract text
    text = extract_text_from_pdf(pdf_path)
    if not text or len(text.strip()) < 100:
        logger.warning(f"Insufficient text extracted from {pdf_path}")
        return {
            'filename': Path(pdf_path).name,
            'domain': domain,
            'status': 'failed',
            'reason': 'insufficient_text'
        }
    
    # Extract tests with AI
    tests = extract_tests_with_ai(text, domain, Path(pdf_path).name)
    
    return {
        'filename': Path(pdf_path).name,
        'domain': domain,
        'status': 'success',
        'text_length': len(text),
        'tests_extracted': len(tests),
        'tests': tests,
        'text_preview': text[:500]  # First 500 chars for preview
    }


def find_all_pdfs(base_dir: str) -> List[tuple]:
    """Find all PDF files and determine their domain"""
    pdfs = []
    base_path = Path(base_dir)
    
    # Map folder names to domains
    domain_map = {
        'ortho exam Oregon Hunter': 'orthopedic',
        'Spine Imaging': 'spine',
        'disc & facet trauma': 'spine',
        'tbi endocrine': 'tbi',
        'TBI Imaging MRI DTI WMH': 'tbi',
        'TBI ITON articles': 'tbi',
        'tbi prognosis': 'tbi',
        'TBI vestibular': 'tbi'
    }
    
    for folder_name, domain in domain_map.items():
        folder_path = base_path / folder_name
        if folder_path.exists():
            for pdf_file in folder_path.rglob('*.pdf'):
                pdfs.append((str(pdf_file), domain))
    
    return pdfs


def main():
    """Main processing function"""
    base_dir = Path(__file__).parent.parent
    
    print("="*60)
    print("Dr. Hunter PDF Processing Pipeline")
    print("="*60)
    print(f"\nBase directory: {base_dir}")
    print(f"PyPDF2 available: {HAS_PYPDF2}")
    print(f"pdfplumber available: {HAS_PDFPLUMBER}")
    print(f"AWS Bedrock available: {HAS_BEDROCK}")
    print()
    
    # Find all PDFs
    print("Finding PDF files...")
    all_pdfs = find_all_pdfs(base_dir)
    print(f"Found {len(all_pdfs)} PDF files")
    
    if not all_pdfs:
        print("No PDFs found!")
        return
    
    # Process first 5 PDFs as proof of concept
    print(f"\nProcessing first 5 PDFs as proof of concept...")
    print("-"*60)
    
    results = []
    for pdf_path, domain in all_pdfs[:5]:
        result = process_pdf(pdf_path, domain)
        results.append(result)
        
        print(f"\nFile: {result['filename']}")
        print(f"Domain: {result['domain']}")
        print(f"Status: {result['status']}")
        if result['status'] == 'success':
            print(f"Text length: {result['text_length']} chars")
            print(f"Tests extracted: {result['tests_extracted']}")
            if result['tests']:
                print("\nExtracted tests:")
                for test in result['tests'][:3]:  # Show first 3
                    print(f"  - {test.get('test_name', 'Unknown')}")
                    if test.get('keywords'):
                        print(f"    Keywords: {', '.join(test['keywords'][:5])}")
    
    # Save results
    output_file = base_dir / 'extracted_tests_results.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"Results saved to: {output_file}")
    print(f"Processed {len(results)} PDFs")
    print(f"Total tests extracted: {sum(r.get('tests_extracted', 0) for r in results)}")


if __name__ == '__main__':
    main()











