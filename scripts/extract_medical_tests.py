#!/usr/bin/env python3
"""
Proof of Concept: Extract Medical Tests from Dr. Hunter's PDFs
This script demonstrates HOW we'll interpret the PDF data
"""

import json
import re
import boto3
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize AWS clients
bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
textract_client = boto3.client('textract', region_name='us-east-1')


class MedicalTestExtractor:
    """
    Extracts medical test information from PDFs using multi-stage approach:
    1. Text extraction (Textract or PyPDF2)
    2. AI-assisted interpretation (Claude)
    3. Structured data output
    """
    
    def __init__(self):
        self.extracted_tests = {}
        self.terminology = {
            'orthopedic': set(),
            'spine': set(),
            'tbi': set(),
            'neurological': set()
        }
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Stage 1: Extract raw text from PDF
        Uses AWS Textract for complex PDFs, PyPDF2 for simple ones
        """
        try:
            # Try Textract first (better quality)
            with open(pdf_path, 'rb') as pdf_file:
                pdf_bytes = pdf_file.read()
            
            # For proof of concept, we'll use a simple approach
            # In production, use Textract for complex PDFs
            try:
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(pdf_path)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
            except Exception as e:
                logger.warning(f"PyPDF2 failed, would use Textract: {e}")
                # In production, fallback to Textract
                return ""
        except Exception as e:
            logger.error(f"Error extracting text from {pdf_path}: {e}")
            return ""
    
    def extract_tests_with_ai(self, text: str, domain: str) -> List[Dict[str, Any]]:
        """
        Stage 2: Use AI to intelligently extract test information
        This is the KEY part - AI interprets the dense medical text
        """
        if not text or len(text) < 100:
            return []
        
        # Truncate text if too long (Claude has token limits)
        text_sample = text[:8000]  # First 8000 chars
        
        prompt = f"""You are analyzing medical literature to extract test names, procedures, and terminology.

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
    "test_name": "Lachman Test",
    "alternative_names": ["Lachman's test"],
    "category": "orthopedic",
    "keywords": ["lachman", "acl", "anterior translation", "knee"],
    "procedure_description": "Patient supine, knee flexed 20-30 degrees, apply anterior force to tibia",
    "when_indicated": "Suspected ACL injury"
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
            
            # Parse JSON response
            tests = json.loads(ai_result)
            return tests
            
        except Exception as e:
            logger.error(f"Error in AI extraction: {e}")
            return []
    
    def extract_terminology_with_ai(self, text: str, domain: str) -> Dict[str, List[str]]:
        """
        Extract medical terminology specific to the domain
        """
        if not text or len(text) < 100:
            return {}
        
        text_sample = text[:6000]
        
        prompt = f"""Extract medical terminology from this {domain} literature.

TEXT:
{text_sample}

Return JSON with terminology organized by category:
{{
  "test_names": ["list of test names"],
  "anatomical_terms": ["list of anatomical terms"],
  "procedural_terms": ["list of procedural terms"],
  "abbreviations": ["list of abbreviations"],
  "common_phrases": ["list of common phrases used in examinations"]
}}

Return ONLY JSON, no additional text."""

        try:
            response = bedrock_client.invoke_model(
                modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 2000,
                    "messages": [{
                        "role": "user",
                        "content": prompt
                    }]
                })
            )
            
            response_body = json.loads(response['body'].read())
            ai_result = response_body.get('content', [{}])[0].get('text', '{}')
            
            terminology = json.loads(ai_result)
            return terminology
            
        except Exception as e:
            logger.error(f"Error extracting terminology: {e}")
            return {}
    
    def process_pdf(self, pdf_path: str, domain: str) -> Dict[str, Any]:
        """
        Main processing function for a single PDF
        """
        logger.info(f"Processing: {pdf_path}")
        
        # Stage 1: Extract text
        text = self.extract_text_from_pdf(pdf_path)
        if not text:
            logger.warning(f"No text extracted from {pdf_path}")
            return {}
        
        # Stage 2: Extract tests with AI
        tests = self.extract_tests_with_ai(text, domain)
        
        # Stage 3: Extract terminology
        terminology = self.extract_terminology_with_ai(text, domain)
        
        return {
            'filename': Path(pdf_path).name,
            'domain': domain,
            'tests': tests,
            'terminology': terminology,
            'text_length': len(text)
        }
    
    def consolidate_results(self, all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Consolidate extracted data from all PDFs
        Merge duplicates, combine keywords, etc.
        """
        consolidated_tests = {}
        consolidated_terminology = {
            'orthopedic': set(),
            'spine': set(),
            'tbi': set(),
            'neurological': set()
        }
        
        for result in all_results:
            # Consolidate tests
            for test in result.get('tests', []):
                test_name = test.get('test_name', '').lower().strip()
                if not test_name:
                    continue
                
                if test_name not in consolidated_tests:
                    consolidated_tests[test_name] = {
                        'test_name': test.get('test_name'),
                        'alternative_names': set(test.get('alternative_names', [])),
                        'categories': set([test.get('category', 'unknown')]),
                        'keywords': set(test.get('keywords', [])),
                        'sources': [result['filename']],
                        'procedure_description': test.get('procedure_description', ''),
                        'when_indicated': test.get('when_indicated', '')
                    }
                else:
                    # Merge: combine keywords, alternative names, sources
                    consolidated_tests[test_name]['alternative_names'].update(
                        test.get('alternative_names', [])
                    )
                    consolidated_tests[test_name]['categories'].add(
                        test.get('category', 'unknown')
                    )
                    consolidated_tests[test_name]['keywords'].update(
                        test.get('keywords', [])
                    )
                    consolidated_tests[test_name]['sources'].append(result['filename'])
            
            # Consolidate terminology
            term_data = result.get('terminology', {})
            for category, terms in term_data.items():
                if isinstance(terms, list):
                    consolidated_terminology[result['domain']].update(terms)
        
        # Convert sets to lists for JSON serialization
        final_tests = {}
        for test_name, test_data in consolidated_tests.items():
            final_tests[test_name] = {
                'test_name': test_data['test_name'],
                'alternative_names': list(test_data['alternative_names']),
                'categories': list(test_data['categories']),
                'keywords': list(test_data['keywords']),
                'sources': test_data['sources'],
                'procedure_description': test_data['procedure_description'],
                'when_indicated': test_data['when_indicated']
            }
        
        final_terminology = {
            domain: list(terms) 
            for domain, terms in consolidated_terminology.items()
        }
        
        return {
            'tests': final_tests,
            'terminology': final_terminology,
            'total_pdfs_processed': len(all_results)
        }


def main():
    """
    Proof of concept: Process a few sample PDFs
    """
    extractor = MedicalTestExtractor()
    
    # Sample PDFs to process (proof of concept)
    sample_pdfs = [
        {
            'path': 'ortho exam Oregon Hunter/File requests/CME Video Recordings/ortho exam Oregon Hunter/Clinical_Orthopedic_Examination_Findings.pdf',
            'domain': 'orthopedic'
        },
        {
            'path': 'ortho exam Oregon Hunter/File requests/CME Video Recordings/ortho exam Oregon Hunter/Orthopedic_Examination_A_step_by_step_gu.pdf',
            'domain': 'orthopedic'
        }
    ]
    
    results = []
    for pdf_info in sample_pdfs:
        pdf_path = Path(pdf_info['path'])
        if pdf_path.exists():
            result = extractor.process_pdf(str(pdf_path), pdf_info['domain'])
            results.append(result)
        else:
            logger.warning(f"PDF not found: {pdf_path}")
    
    # Consolidate results
    consolidated = extractor.consolidate_results(results)
    
    # Output results
    output_file = 'extracted_tests_poc.json'
    with open(output_file, 'w') as f:
        json.dump(consolidated, f, indent=2)
    
    logger.info(f"Extracted {len(consolidated['tests'])} unique tests")
    logger.info(f"Results saved to {output_file}")
    
    # Print summary
    print("\n" + "="*60)
    print("EXTRACTION SUMMARY")
    print("="*60)
    print(f"PDFs Processed: {consolidated['total_pdfs_processed']}")
    print(f"Unique Tests Found: {len(consolidated['tests'])}")
    print("\nSample Tests:")
    for i, (test_name, test_data) in enumerate(list(consolidated['tests'].items())[:5]):
        print(f"\n{i+1}. {test_data['test_name']}")
        print(f"   Categories: {', '.join(test_data['categories'])}")
        print(f"   Keywords: {', '.join(test_data['keywords'][:5])}")
        print(f"   Sources: {len(test_data['sources'])} PDF(s)")


if __name__ == '__main__':
    main()











