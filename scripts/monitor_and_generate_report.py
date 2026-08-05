#!/usr/bin/env python3
"""
Monitor CME session processing and generate PDF report when complete
"""
import sys
import requests
import time
import json
from pathlib import Path

from cme_api_auth import auth_headers

API_BASE_URL = "https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod"

def get_session_status(session_id: str):
    """Get current session status"""
    response = requests.get(f"{API_BASE_URL}/cme/sessions/{session_id}", headers=auth_headers())
    if response.status_code == 200:
        data = response.json()
        return data.get('session', data)
    return None

def generate_pdf_report(session_id: str, output_path: str = None):
    """Generate PDF report for completed session"""
    if not output_path:
        output_path = f"cme_report_{session_id}.pdf"
    
    # First get HTML report
    html_url = f"{API_BASE_URL}/cme/sessions/{session_id}/report?format=html"
    print(f"\n📄 Generating PDF report...")
    print(f"   HTML URL: {html_url}")
    
    # Use the existing PDF generation script
    import subprocess
    result = subprocess.run(
        ['python3', 'scripts/generate_pdf_from_html.py', session_id, output_path],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f"✅ PDF Report generated: {output_path}")
        return output_path
    else:
        print(f"❌ Failed to generate PDF:")
        print(result.stderr)
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 monitor_and_generate_report.py <session_id>")
        sys.exit(1)
    
    session_id = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    print("=" * 60)
    print("🔍 MONITORING CME SESSION PROCESSING")
    print("=" * 60)
    print(f"Session ID: {session_id}\n")
    
    max_wait_time = 3600  # 1 hour max
    check_interval = 30  # Check every 30 seconds
    start_time = time.time()
    last_status = None
    
    while True:
        session = get_session_status(session_id)
        
        if not session:
            print("❌ Failed to get session status")
            sys.exit(1)
        
        status = session.get('status')
        stage = session.get('processing_stage', 'N/A')
        
        # Show status if it changed
        if status != last_status:
            print(f"\n📊 Status: {status}")
            print(f"   Stage: {stage}")
            
            # Show recording info
            recordings = session.get('recordings', [])
            if recordings:
                print(f"   Recordings: {len(recordings)}")
            
            # Show declared tests if available
            declared_tests = session.get('declared_tests', [])
            if declared_tests:
                print(f"   Declared Tests: {len(declared_tests)}")
            
            # Show observed actions if available
            observed_actions = session.get('observed_actions', [])
            if observed_actions:
                performed = sum(1 for a in observed_actions if a.get('motion_present') == 'performed')
                print(f"   Observed Actions: {len(observed_actions)}")
                print(f"   Performed: {performed}")
        
        last_status = status
        
        # Check if complete
        if status == 'completed':
            print("\n✅ Processing complete!")
            
            # Generate report
            pdf_path = generate_pdf_report(session_id, output_path)
            
            if pdf_path:
                file_size = Path(pdf_path).stat().st_size / (1024 * 1024)
                print(f"\n📄 PDF Report Location:")
                print(f"   {Path(pdf_path).absolute()}")
                print(f"   Size: {file_size:.2f} MB")
            
            break
        
        # Check timeout
        elapsed = time.time() - start_time
        if elapsed > max_wait_time:
            print(f"\n⏰ Timeout after {max_wait_time}s")
            print("   Processing may still be running. Check manually:")
            print(f"   {API_BASE_URL}/cme/sessions/{session_id}")
            break
        
        # Wait before next check
        time.sleep(check_interval)
        print(".", end="", flush=True)

if __name__ == "__main__":
    main()

