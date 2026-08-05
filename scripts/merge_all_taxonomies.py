#!/usr/bin/env python3
"""
Merge original training taxonomy + comprehensive PDF taxonomy
and generate updated TEST_TAXONOMY code
"""

import json
from pathlib import Path
from collections import defaultdict

def load_taxonomy(file_path):
    """Load taxonomy from JSON file"""
    with open(file_path, 'r') as f:
        data = json.load(f)
    return data.get('taxonomy_expansion', {})

def merge_taxonomies(orig_taxonomy, comp_taxonomy):
    """Merge two taxonomies, combining keywords and patterns"""
    merged = defaultdict(lambda: {
        'keywords': set(),
        'patterns': set(),
        'source_count': 0,
        'domains': set()
    })
    
    # Add original taxonomy
    for test_type, data in orig_taxonomy.items():
        merged[test_type]['keywords'].update(data.get('keywords', []))
        merged[test_type]['patterns'].update(data.get('patterns', []))
        merged[test_type]['source_count'] += data.get('source_count', 0)
        merged[test_type]['domains'].update(data.get('domains', []))
    
    # Add comprehensive taxonomy
    for test_type, data in comp_taxonomy.items():
        merged[test_type]['keywords'].update(data.get('keywords', []))
        merged[test_type]['patterns'].update(data.get('patterns', []))
        merged[test_type]['source_count'] += data.get('source_count', 0)
        merged[test_type]['domains'].update(data.get('domains', []))
    
    # Convert sets to lists
    final_merged = {}
    for test_type, data in merged.items():
        final_merged[test_type] = {
            'keywords': sorted(list(data['keywords']))[:100],  # Limit to 100 keywords
            'patterns': sorted(list(data['patterns'])),
            'source_count': data['source_count'],
            'domains': sorted(list(data['domains']))
        }
    
    return final_merged

def generate_taxonomy_code(merged_taxonomy):
    """Generate Python code for TEST_TAXONOMY"""
    
    code_lines = [
        "# Merged TEST_TAXONOMY from original training + comprehensive PDF processing",
        "# Generated from 2,282 PDFs (723 original + 1,559 comprehensive)",
        "",
        "TEST_TAXONOMY_UPDATES = {"
    ]
    
    for test_type in sorted(merged_taxonomy.keys()):
        data = merged_taxonomy[test_type]
        keywords = data['keywords']
        patterns = data['patterns']
        sources = data['source_count']
        
        code_lines.append(f"    '{test_type}': {{")
        code_lines.append(f"        # Sources: {sources} PDFs")
        code_lines.append(f"        'keywords': {keywords},")
        code_lines.append(f"        'patterns': {patterns},")
        code_lines.append(f"        'source_count': {sources}")
        code_lines.append("    },")
        code_lines.append("")
    
    code_lines.append("}")
    
    return "\n".join(code_lines)

def main():
    print("=" * 60)
    print("🔄 MERGING ALL TAXONOMIES")
    print("=" * 60)
    print("")
    
    # Load taxonomies
    print("📂 Loading taxonomies...")
    orig_taxonomy = load_taxonomy('extracted_test_terminology.json')
    comp_taxonomy = load_taxonomy('comprehensive_pdf_extraction.json')
    
    print(f"   ✅ Original: {len(orig_taxonomy)} test types")
    print(f"   ✅ Comprehensive: {len(comp_taxonomy)} test types")
    
    # Merge
    print("\n🔄 Merging...")
    merged = merge_taxonomies(orig_taxonomy, comp_taxonomy)
    print(f"   ✅ Merged: {len(merged)} test types")
    
    # Stats
    total_keywords = sum(len(t['keywords']) for t in merged.values())
    total_patterns = sum(len(t['patterns']) for t in merged.values())
    total_sources = sum(t['source_count'] for t in merged.values())
    
    print(f"\n📊 MERGED STATS:")
    print(f"   Test types: {len(merged)}")
    print(f"   Total keywords: {total_keywords}")
    print(f"   Total patterns: {total_patterns}")
    print(f"   Total sources: {total_sources} PDFs")
    
    # Generate code
    print("\n💾 Generating taxonomy code...")
    taxonomy_code = generate_taxonomy_code(merged)
    
    with open('merged_taxonomy_expansion.py', 'w') as f:
        f.write(taxonomy_code)
    
    print("   ✅ Saved to merged_taxonomy_expansion.py")
    
    # Show top test types
    print("\n🏆 TOP 10 TEST TYPES BY SOURCES:")
    sorted_types = sorted(merged.items(), key=lambda x: x[1]['source_count'], reverse=True)
    for i, (test_type, data) in enumerate(sorted_types[:10], 1):
        print(f"   {i:2d}. {test_type:30s} {data['source_count']:4d} sources, {len(data['keywords']):3d} keywords")
    
    print("\n✅ Merge complete!")
    print("   Review merged_taxonomy_expansion.py")
    print("   Then update TEST_TAXONOMY in cme_nlp_processor.py")

if __name__ == "__main__":
    main()

