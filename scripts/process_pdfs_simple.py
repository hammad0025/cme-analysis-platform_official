#!/usr/bin/env python3
"""
Process PDFs - Show extracted text and basic pattern matching
Works without AWS Bedrock
"""

import json
import re
from pathlib import Path
import pdfplumber

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF"""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"Error extracting from {pdf_path}: {e}")
    return text

def find_test_names_in_text(text: str) -> list:
    """Basic pattern matching to find test names"""
    test_patterns = [
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+test',
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+maneuver',
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+sign',
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+examination',
    ]
    
    found_tests = set()
    for pattern in test_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                match = ' '.join(match)
            if len(match) > 3 and len(match) < 50:  # Reasonable length
                found_tests.add(match.strip())
    
    return sorted(list(found_tests))

def find_keywords_in_text(text: str) -> dict:
    """Find medical keywords"""
    keywords = {
        'test_names': [],
        'anatomical_terms': [],
        'abbreviations': []
    }
    
    # Common test keywords
    test_keywords = [
        'straight leg raise', 'slr', 'lasegue', 'lachman', 'mcmurray',
        'rom', 'range of motion', 'reflex', 'gait', 'palpation',
        'neurological', 'sensation', 'motor', 'strength'
    ]
    
    text_lower = text.lower()
    for keyword in test_keywords:
        if keyword in text_lower:
            keywords['test_names'].append(keyword)
    
    # Find abbreviations (2-5 uppercase letters)
    abbrevs = re.findall(r'\b[A-Z]{2,5}\b', text)
    keywords['abbreviations'] = list(set(abbrevs[:20]))  # Limit to 20
    
    return keywords

def process_pdf(pdf_path: str, domain: str):
    """Process a single PDF"""
    print(f"\n{'='*60}")
    print(f"Processing: {Path(pdf_path).name}")
    print(f"Domain: {domain}")
    print('='*60)
    
    # Extract text
    text = extract_text_from_pdf(pdf_path)
    
    if not text or len(text.strip()) < 100:
        print("❌ Insufficient text extracted")
        return None
    
    print(f"✅ Extracted {len(text):,} characters")
    print(f"✅ Extracted {len(text.split())} words")
    
    # Show text preview
    print(f"\n📄 Text Preview (first 1000 chars):")
    print("-" * 60)
    print(text[:1000])
    print("...")
    
    # Find test names
    test_names = find_test_names_in_text(text)
    if test_names:
        print(f"\n🔍 Test Names Found ({len(test_names)}):")
        for test in test_names[:10]:  # Show first 10
            print(f"  - {test}")
    
    # Find keywords
    keywords = find_keywords_in_text(text)
    if keywords['test_names']:
        print(f"\n📝 Medical Keywords Found:")
        print(f"  Test-related: {', '.join(keywords['test_names'][:10])}")
    if keywords['abbreviations']:
        print(f"  Abbreviations: {', '.join(keywords['abbreviations'][:10])}")
    
    return {
        'filename': Path(pdf_path).name,
        'domain': domain,
        'text_length': len(text),
        'word_count': len(text.split()),
        'test_names': test_names,
        'keywords': keywords,
        'text_preview': text[:2000]
    }

def main():
    base_dir = Path(__file__).parent.parent
    
    # Process the AAOS herniated disc PDF specifically
    target_pdf = base_dir / "Spine Imaging/File requests/CME Video Recordings/temp Oregon Hunter/Spine imaging/AAOS - herniated disc low back.pdf"
    
    if target_pdf.exists():
        print("🎯 Processing: AAOS - herniated disc low back.pdf")
        result = process_pdf(str(target_pdf), 'spine')
        
        if result:
            # Save result
            output_file = base_dir / 'aaos_extraction_result.json'
            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\n✅ Results saved to: {output_file}")
    else:
        print(f"❌ File not found: {target_pdf}")

if __name__ == '__main__':
    main()











