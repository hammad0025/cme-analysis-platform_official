#!/usr/bin/env python3
"""
Generate PDF report from HTML report
Downloads HTML from S3 and converts to PDF using local tools
"""

import boto3
import json
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

API_URL = 'https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod'

def download_html_report(session_id):
    """Download HTML report from S3"""
    print(f"\n📥 DOWNLOADING HTML REPORT...")
    
    # Check if HTML file already exists locally
    html_path = project_root / f"cme_report_{session_id}.html"
    if html_path.exists():
        print(f"✅ Found existing HTML report: {html_path}")
        return str(html_path)
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    s3_client = boto3.client('s3', region_name='us-east-1')
    
    payload = {
        'session_id': session_id,
        'format': 'html'
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='cme-report-generator',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read().decode('utf-8'))
        
        if result.get('statusCode') == 200:
            report_key = result.get('report_key')
            s3_bucket = 'eve-legal-documents'  # Default bucket
            
            print(f"✅ HTML Report generated!")
            print(f"   S3 Key: {report_key}")
            
            # Download directly from S3 (avoids SSL issues)
            s3_client.download_file(s3_bucket, report_key, str(html_path))
            print(f"   ✅ Downloaded to: {html_path}")
            
            return str(html_path)
        else:
            print(f"❌ Error generating report: {result.get('error', 'Unknown error')}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def convert_html_to_pdf(html_path, pdf_path):
    """Convert HTML to PDF using available tool"""
    print(f"\n📄 CONVERTING HTML TO PDF...")
    
    # Try different methods in order of preference
    methods = [
        ('chrome_headless', convert_with_chrome),
        ('weasyprint', convert_with_weasyprint),
        ('wkhtmltopdf', convert_with_wkhtmltopdf),
    ]
    
    for method_name, converter_func in methods:
        try:
            print(f"   Trying {method_name}...")
            result = converter_func(html_path, pdf_path)
            if result:
                print(f"   ✅ Successfully converted using {method_name}!")
                return True
        except Exception as e:
            print(f"   ⚠️  {method_name} failed: {e}")
            continue
    
    print(f"\n❌ All conversion methods failed!")
    print(f"\n💡 ALTERNATIVE: Open the HTML file in your browser and print to PDF:")
    print(f"   1. Open: {html_path}")
    print(f"   2. Press Cmd+P (Mac) or Ctrl+P (Windows)")
    print(f"   3. Choose 'Save as PDF'")
    return False

def convert_with_chrome(html_path, pdf_path):
    """Convert using Chrome headless (best quality)"""
    import subprocess
    
    # Check if Chrome/Chromium is available
    chrome_paths = [
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/usr/bin/google-chrome',
        '/usr/bin/chromium-browser',
        'chrome',
        'chromium'
    ]
    
    chrome_cmd = None
    for path in chrome_paths:
        if os.path.exists(path) or subprocess.run(['which', path.split('/')[-1]], 
                                                   capture_output=True).returncode == 0:
            chrome_cmd = path
            break
    
    if not chrome_cmd:
        raise Exception("Chrome not found")
    
    # Convert HTML to PDF
    abs_html = os.path.abspath(html_path)
    abs_pdf = os.path.abspath(pdf_path)
    
    cmd = [
        chrome_cmd,
        '--headless',
        '--disable-gpu',
        '--print-to-pdf=' + abs_pdf,
        'file://' + abs_html
    ]
    
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode == 0 and os.path.exists(pdf_path):
        return True
    raise Exception(f"Chrome conversion failed: {result.stderr.decode()}")

def convert_with_weasyprint(html_path, pdf_path):
    """Convert using WeasyPrint"""
    from weasyprint import HTML
    HTML(filename=html_path).write_pdf(pdf_path)
    return os.path.exists(pdf_path)

def convert_with_wkhtmltopdf(html_path, pdf_path):
    """Convert using wkhtmltopdf"""
    import subprocess
    result = subprocess.run(
        ['wkhtmltopdf', html_path, pdf_path],
        capture_output=True,
        timeout=30
    )
    if result.returncode == 0 and os.path.exists(pdf_path):
        return True
    raise Exception(f"wkhtmltopdf failed: {result.stderr.decode()}")

def main():
    # Get session ID from command line or use default
    session_id = sys.argv[1] if len(sys.argv) > 1 else SESSION_ID
    output_pdf = sys.argv[2] if len(sys.argv) > 2 else str(project_root / f"cme_report_{session_id}.pdf")
    
    print("=" * 60)
    print("📄 GENERATING PDF REPORT FROM HTML")
    print("=" * 60)
    print(f"\nSession ID: {session_id}")
    
    # Download HTML report
    html_path = download_html_report(session_id)
    if not html_path:
        print("\n❌ Failed to download HTML report")
        return
    
    # Convert to PDF
    pdf_path = Path(output_pdf)
    success = convert_html_to_pdf(html_path, pdf_path)
    
    if success:
        print(f"\n🎉 SUCCESS!")
        print(f"   PDF Report: {pdf_path}")
        print(f"   File size: {os.path.getsize(pdf_path) / 1024:.1f} KB")
        print(f"\n📁 File Location:")
        print(f"   {pdf_path.absolute()}")
    else:
        print(f"\n📄 HTML Report available at:")
        print(f"   {os.path.abspath(html_path)}")
        print(f"\n   Use browser print function to convert to PDF")

if __name__ == "__main__":
    main()

