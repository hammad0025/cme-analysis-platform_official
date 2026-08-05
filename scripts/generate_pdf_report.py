#!/usr/bin/env python3
"""
Generate PDF report for CME session
Waits for processing to complete, then generates formatted PDF report
"""

import boto3
import json
import time
import requests
from datetime import datetime

from cme_api_auth import auth_headers

API_URL = 'https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod'
SESSION_ID = 'cme_7285456d8748'

def check_processing_status(session_id):
    """Check if processing is complete"""
    try:
        response = requests.get(f"{API_URL}/cme/sessions/{session_id}", headers=auth_headers())
        if response.status_code == 200:
            data = response.json()
            status = data.get('status', 'unknown')
            stage = data.get('processing_stage', 'unknown')
            return status, stage
    except Exception as e:
        print(f"Error checking status: {e}")
    return None, None

def generate_pdf_report(session_id):
    """Generate PDF report"""
    print(f"\n📄 GENERATING PDF REPORT...")
    
    # Invoke report generator Lambda directly
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    payload = {
        'session_id': session_id,
        'format': 'pdf'
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='cme-report-generator',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read().decode('utf-8'))
        
        if result.get('statusCode') == 200:
            download_url = result.get('download_url')
            report_key = result.get('report_key')
            
            print(f"✅ PDF Report generated!")
            print(f"   S3 Key: {report_key}")
            print(f"   Download URL: {download_url}")
            
            # Download the PDF
            import urllib.request
            pdf_path = f"cme_report_{session_id}.pdf"
            urllib.request.urlretrieve(download_url, pdf_path)
            print(f"   ✅ Downloaded to: {pdf_path}")
            
            return pdf_path
        else:
            print(f"❌ Error generating report: {result.get('error', 'Unknown error')}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print("=" * 60)
    print("🔄 MONITORING PROCESSING & GENERATING PDF REPORT")
    print("=" * 60)
    print(f"\nSession ID: {SESSION_ID}")
    print("Waiting for processing to complete...")
    print("")
    
    max_wait = 600  # 10 minutes
    check_interval = 30  # Check every 30 seconds
    elapsed = 0
    
    while elapsed < max_wait:
        status, stage = check_processing_status(SESSION_ID)
        
        if status:
            print(f"⏳ Status: {status} | Stage: {stage} | Elapsed: {elapsed}s")
            
            if status == 'completed' or status == 'report_generated':
                print("\n✅ Processing complete!")
                break
            elif status == 'error' or status == 'failed':
                print("\n❌ Processing failed!")
                return
        else:
            print(f"⏳ Checking... ({elapsed}s)")
        
        time.sleep(check_interval)
        elapsed += check_interval
    
    if elapsed >= max_wait:
        print("\n⚠️  Timeout waiting for processing")
        print("   Generating report anyway...")
    
    # Generate PDF report
    pdf_path = generate_pdf_report(SESSION_ID)
    
    if pdf_path:
        print(f"\n🎉 SUCCESS!")
        print(f"   PDF Report: {pdf_path}")
        print(f"   Open it to view the formatted report")
    else:
        print("\n❌ Failed to generate PDF report")

if __name__ == "__main__":
    main()

