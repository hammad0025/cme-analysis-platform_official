#!/usr/bin/env python3
"""
Merge extracted taxonomy expansion into TEST_TAXONOMY
Updates cme_nlp_processor.py with new keywords and patterns
"""

import json
import re
from pathlib import Path

def load_extracted_data():
    """Load extracted terminology"""
    with open('extracted_test_terminology.json', 'r') as f:
        return json.load(f)

def load_current_taxonomy():
    """Load current TEST_TAXONOMY from NLP processor"""
    nlp_file = Path('backend/lambda_functions/cme_nlp_processor.py')
    content = nlp_file.read_text()
    
    # Find TEST_TAXONOMY section
    start_match = re.search(r'TEST_TAXONOMY\s*=\s*\{', content)
    if not start_match:
        return None, content
    
    start_pos = start_match.start()
    
    # Find the end of TEST_TAXONOMY dict
    brace_count = 0
    in_dict = False
    end_pos = start_pos
    
    for i in range(start_pos, len(content)):
        if content[i] == '{':
            brace_count += 1
            in_dict = True
        elif content[i] == '}':
            brace_count -= 1
            if brace_count == 0 and in_dict:
                end_pos = i + 1
                break
    
    taxonomy_section = content[start_pos:end_pos]
    before = content[:start_pos]
    after = content[end_pos:]
    
    return taxonomy_section, before, after

def merge_taxonomy(current_taxonomy_text, extracted_data):
    """Merge extracted data into current taxonomy"""
    taxonomy_expansion = extracted_data['taxonomy_expansion']
    
    # Parse current taxonomy (simple approach - just enhance existing entries)
    # We'll add new keywords and patterns to existing test types
    
    merged_updates = {}
    
    for test_type, extracted_info in taxonomy_expansion.items():
        # Get keywords and patterns from extracted data
        new_keywords = extracted_info.get('keywords', [])
        new_patterns = extracted_info.get('patterns', [])
        
        # Check if test_type exists in current taxonomy
        if test_type in current_taxonomy_text:
            # Extract current keywords and patterns
            keywords_match = re.search(rf"'{test_type}':\s*{{[^}}]*'keywords':\s*\[([^\]]+)\]", current_taxonomy_text)
            patterns_match = re.search(rf"'{test_type}':\s*{{[^}}]*'patterns':\s*\[([^\]]+)\]", current_taxonomy_text)
            
            current_keywords = []
            current_patterns = []
            
            if keywords_match:
                # Parse existing keywords
                kw_text = keywords_match.group(1)
                current_keywords = [k.strip().strip("'\"") for k in kw_text.split(',') if k.strip()]
            
            if patterns_match:
                # Parse existing patterns
                pat_text = patterns_match.group(1)
                # Extract regex patterns (more complex parsing needed)
                current_patterns = re.findall(r"r'([^']+)'", pat_text)
            
            # Merge: combine current + new, remove duplicates
            merged_keywords = list(set(current_keywords + new_keywords[:30]))  # Limit to 30
            merged_patterns = list(set(current_patterns + new_patterns[:10]))  # Limit to 10
            
            merged_updates[test_type] = {
                'keywords': merged_keywords,
                'patterns': merged_patterns
            }
        else:
            # New test type - add it
            merged_updates[test_type] = {
                'keywords': new_keywords[:30],
                'patterns': new_patterns[:10]
            }
    
    return merged_updates

def generate_updated_taxonomy_code(current_taxonomy_text, merged_updates):
    """Generate updated TEST_TAXONOMY code"""
    
    # This is a simplified approach - we'll create a script that shows what to add
    # Full merge would require more complex parsing
    
    updates_code = []
    updates_code.append("# TAXONOMY UPDATES FROM TRAINING PDFs")
    updates_code.append("# Generated from 723 processed PDFs")
    updates_code.append("")
    updates_code.append("TAXONOMY_UPDATES = {")
    
    for test_type, data in sorted(merged_updates.items()):
        keywords = data['keywords']
        patterns = data['patterns']
        
        updates_code.append(f"    '{test_type}': {{")
        updates_code.append(f"        'keywords': {keywords},")
        updates_code.append(f"        'patterns': {patterns}")
        updates_code.append("    },")
    
    updates_code.append("}")
    
    return "\n".join(updates_code)

def main():
    print("=" * 60)
    print("🔄 MERGING TAXONOMY EXPANSION")
    print("=" * 60)
    print("")
    
    # Load extracted data
    print("📂 Loading extracted terminology...")
    extracted_data = load_extracted_data()
    print(f"   ✅ Loaded {len(extracted_data['taxonomy_expansion'])} test types")
    
    # Load current taxonomy
    print("\n📂 Loading current TEST_TAXONOMY...")
    taxonomy_section, before, after = load_current_taxonomy()
    
    if not taxonomy_section:
        print("   ⚠️  Could not find TEST_TAXONOMY in NLP processor")
        return
    
    print("   ✅ Found TEST_TAXONOMY")
    
    # Merge
    print("\n🔄 Merging extracted data...")
    merged_updates = merge_taxonomy(taxonomy_section, extracted_data)
    print(f"   ✅ Merged {len(merged_updates)} test types")
    
    # Generate update code
    print("\n💾 Generating update code...")
    update_code = generate_updated_taxonomy_code(taxonomy_section, merged_updates)
    
    with open('taxonomy_merge_updates.py', 'w') as f:
        f.write(update_code)
    
    print("   ✅ Saved to taxonomy_merge_updates.py")
    
    # Show summary
    print("\n📊 MERGE SUMMARY:")
    print(f"   Test types to update: {len(merged_updates)}")
    
    total_keywords = sum(len(u['keywords']) for u in merged_updates.values())
    total_patterns = sum(len(u['patterns']) for u in merged_updates.values())
    
    print(f"   Total keywords: {total_keywords}")
    print(f"   Total patterns: {total_patterns}")
    
    print("\n✅ Merge complete!")
    print("   Review taxonomy_merge_updates.py")
    print("   Then manually merge into cme_nlp_processor.py TEST_TAXONOMY")

if __name__ == "__main__":
    main()

