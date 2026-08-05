#!/usr/bin/env python3
"""
Update TEST_TAXONOMY in cme_nlp_processor.py with merged taxonomy
Enhances existing test types with new keywords and patterns
"""

import json
import re
from pathlib import Path
from collections import defaultdict

def load_merged_taxonomy():
    """Load and merge taxonomies"""
    with open('extracted_test_terminology.json', 'r') as f:
        orig = json.load(f)
    
    with open('comprehensive_pdf_extraction.json', 'r') as f:
        comp = json.load(f)
    
    merged = defaultdict(lambda: {'keywords': set(), 'patterns': set()})
    
    for test_type, data in orig.get('taxonomy_expansion', {}).items():
        merged[test_type]['keywords'].update(data.get('keywords', []))
        merged[test_type]['patterns'].update(data.get('patterns', []))
    
    for test_type, data in comp.get('taxonomy_expansion', {}).items():
        merged[test_type]['keywords'].update(data.get('keywords', []))
        merged[test_type]['patterns'].update(data.get('patterns', []))
    
    # Convert sets to lists
    final = {}
    for test_type, data in merged.items():
        # Filter keywords (remove single characters, numbers, etc.)
        keywords = [k for k in data['keywords'] if len(k) > 2 and not k.isdigit()]
        final[test_type] = {
            'keywords': sorted(keywords)[:50],  # Limit to 50 best keywords
            'patterns': sorted(list(data['patterns']))
        }
    
    return final

def update_test_type_in_code(test_type, merged_data, current_code):
    """Update a single test type in the code"""
    # Find the test type definition
    pattern = rf"'{re.escape(test_type)}':\s*\{{(.*?)(?=\n\s*'(?:\w+|range_of_motion|gait_observation)'|\n\s*\}})"
    
    match = re.search(pattern, current_code, re.DOTALL)
    if not match:
        return current_code
    
    test_block = match.group(0)
    test_content = match.group(1)
    
    # Extract current keywords
    keywords_match = re.search(r"'keywords':\s*\[(.*?)\]", test_content, re.DOTALL)
    current_keywords = []
    if keywords_match:
        kw_text = keywords_match.group(1)
        current_keywords = [k.strip().strip("'\"") for k in re.findall(r"['\"]([^'\"]+)['\"]", kw_text)]
    
    # Extract current patterns
    patterns_match = re.search(r"'patterns':\s*\[(.*?)\]", test_content, re.DOTALL)
    current_patterns = []
    if patterns_match:
        pat_text = patterns_match.group(1)
        current_patterns = re.findall(r"r['\"]([^'\"]+)['\"]", pat_text)
    
    # Merge keywords (keep existing, add new unique ones)
    merged_keywords = list(set(current_keywords + merged_data['keywords']))[:60]
    
    # Merge patterns (keep existing, add new unique ones)
    merged_patterns = list(set(current_patterns + merged_data['patterns']))[:20]
    
    # Rebuild keywords list
    keywords_str = ",\n            ".join([f"'{kw}'" for kw in sorted(merged_keywords)])
    
    # Rebuild patterns list
    patterns_str = ",\n            ".join([f"r'{pat}'" for pat in sorted(merged_patterns)])
    
    # Replace keywords
    if keywords_match:
        new_keywords_block = f"'keywords': [\n            {keywords_str}\n        ]"
        test_content = re.sub(r"'keywords':\s*\[.*?\]", new_keywords_block, test_content, flags=re.DOTALL)
    else:
        # Insert keywords after opening brace
        test_content = test_content.replace('{', f"{{\n        'keywords': [\n            {keywords_str}\n        ],", 1)
    
    # Replace patterns
    if patterns_match:
        new_patterns_block = f"'patterns': [\n            {patterns_str}\n        ]"
        test_content = re.sub(r"'patterns':\s*\[.*?\]", new_patterns_block, test_content, flags=re.DOTALL)
    else:
        # Insert patterns after keywords
        test_content = test_content.replace("],", f"],\n        'patterns': [\n            {patterns_str}\n        ],", 1)
    
    # Rebuild test block
    new_test_block = f"'{test_type}': {{{test_content}\n    }}"
    
    # Replace in code
    updated_code = current_code.replace(test_block, new_test_block)
    
    return updated_code

def main():
    print("=" * 60)
    print("🔄 UPDATING TEST_TAXONOMY IN NLP PROCESSOR")
    print("=" * 60)
    print("")
    
    # Load merged taxonomy
    print("📂 Loading merged taxonomy...")
    merged_taxonomy = load_merged_taxonomy()
    print(f"   ✅ Loaded {len(merged_taxonomy)} test types")
    
    # Read NLP processor
    print("\n📂 Reading NLP processor...")
    nlp_file = Path('backend/lambda_functions/cme_nlp_processor.py')
    nlp_content = nlp_file.read_text()
    
    # Find existing test types
    existing_types = re.findall(r"'(\w+)':\s*\{", nlp_content)
    print(f"   ✅ Found {len(existing_types)} existing test types")
    
    # Find overlap
    overlap = set(existing_types) & set(merged_taxonomy.keys())
    print(f"\n🔄 Updating {len(overlap)} test types...")
    
    updated_count = 0
    for test_type in sorted(overlap):
        try:
            nlp_content = update_test_type_in_code(test_type, merged_taxonomy[test_type], nlp_content)
            updated_count += 1
            print(f"   ✅ Updated {test_type}")
        except Exception as e:
            print(f"   ⚠️  Failed to update {test_type}: {e}")
    
    # Save updated file
    print(f"\n💾 Saving updated NLP processor...")
    nlp_file.write_text(nlp_content)
    print(f"   ✅ Updated {updated_count} test types")
    
    print("\n✅ Update complete!")
    print("   Review backend/lambda_functions/cme_nlp_processor.py")

if __name__ == "__main__":
    main()

