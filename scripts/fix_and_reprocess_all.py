#!/usr/bin/env python3
"""
FIX EVERYTHING AND RE-PROCESS
1. Deploy fixed Lambda functions
2. Re-process video for all declared tests
3. Verify sentiment analysis is working
4. Regenerate report
"""

import boto3
import json
import time
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

SESSION_ID = 'cme_7285456d8748'
REGION = 'us-east-1'

def deploy_lambda_functions():
    """Deploy updated Lambda functions"""
    print("\n" + "="*60)
    print("🚀 DEPLOYING FIXED LAMBDA FUNCTIONS")
    print("="*60)
    
    lambda_client = boto3.client('lambda', region_name=REGION)
    
    # Functions to update
    functions = [
        'cme-nlp-processor',
        'cme-video-processor', 
        'cme-report-generator'
    ]
    
    for func_name in functions:
        print(f"\n📦 Updating {func_name}...")
        try:
            # Get function code location
            lambda_dir = project_root / 'backend' / 'lambda_functions'
            
            # Create deployment package
            import zipfile
            import tempfile
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
                zip_path = tmp.name
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add all Python files
                for py_file in lambda_dir.glob('*.py'):
                    zipf.write(py_file, py_file.name)
                
                # Add requirements if exists
                req_file = project_root / 'backend' / 'requirements.txt'
                if req_file.exists():
                    zipf.write(req_file, 'requirements.txt')
            
            # Update function code
            with open(zip_path, 'rb') as f:
                lambda_client.update_function_code(
                    FunctionName=func_name,
                    ZipFile=f.read()
                )
            
            # Wait for update to complete
            print(f"   ⏳ Waiting for update to complete...")
            waiter = lambda_client.get_waiter('function_updated')
            waiter.wait(FunctionName=func_name)
            
            print(f"   ✅ {func_name} updated successfully!")
            os.unlink(zip_path)
            
        except Exception as e:
            print(f"   ❌ Error updating {func_name}: {e}")
            import traceback
            traceback.print_exc()

def get_declared_tests(session_id):
    """Get all declared tests from DynamoDB"""
    print(f"\n📋 GETTING DECLARED TESTS...")
    
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    steps_table = dynamodb.Table('cme-declared-steps')
    
    response = steps_table.scan(
        FilterExpression='session_id = :sid',
        ExpressionAttributeValues={':sid': session_id}
    )
    
    tests = response.get('Items', [])
    print(f"   ✅ Found {len(tests)} declared tests")
    
    return tests

def get_video_s3_key(session_id):
    """Get video S3 key for session"""
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    sessions_table = dynamodb.Table('cme-sessions')
    
    response = sessions_table.get_item(Key={'session_id': session_id})
    session = response.get('Item', {})
    
    # Get video URI
    video_uri = session.get('video_uri', '')
    if video_uri.startswith('s3://'):
        # Extract bucket and key
        parts = video_uri.replace('s3://', '').split('/', 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ''
        return bucket, key
    
    # Try recordings list
    recordings = session.get('recordings', [])
    if recordings:
        rec = recordings[0]
        uri = rec.get('uri', rec.get('s3_key', ''))
        if uri.startswith('s3://'):
            parts = uri.replace('s3://', '').split('/', 1)
            return parts[0], parts[1] if len(parts) > 1 else ''
    
    return 'eve-legal-documents', ''

def process_video_for_all_tests(session_id, declared_tests):
    """Process video analysis for all declared tests"""
    print(f"\n" + "="*60)
    print("🎥 PROCESSING VIDEO ANALYSIS FOR ALL TESTS")
    print("="*60)
    
    lambda_client = boto3.client('lambda', region_name=REGION)
    s3_bucket, video_s3_key = get_video_s3_key(session_id)
    
    if not video_s3_key:
        print("   ❌ Could not find video S3 key!")
        return
    
    print(f"   Video: s3://{s3_bucket}/{video_s3_key}")
    print(f"   Processing {len(declared_tests)} tests...\n")
    
    processed = 0
    failed = 0
    
    for i, test in enumerate(declared_tests, 1):
        test_label = test.get('label', 'unknown')
        test_timestamp = float(test.get('timestamp', 0))
        declared_step_id = test.get('declared_step_id', '')
        
        print(f"[{i}/{len(declared_tests)}] Processing: {test_label} at {test_timestamp:.1f}s...", end=' ')
        
        # Prepare payload
        payload = {
            'session_id': session_id,
            'declared_test': {
                'declared_step_id': declared_step_id,
                'label': test_label,
                'timestamp': test_timestamp,
                'transcript_text': test.get('transcript_text', '')
            },
            'video_s3_key': video_s3_key
        }
        
        try:
            # Invoke video processor
            response = lambda_client.invoke(
                FunctionName='cme-video-processor',
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            result = json.loads(response['Payload'].read().decode('utf-8'))
            
            if result.get('statusCode') == 200:
                motion = result.get('motion_present', 'unknown')
                print(f"✅ {motion}")
                processed += 1
            else:
                print(f"❌ Error: {result.get('error', 'Unknown')}")
                failed += 1
            
            # Small delay to avoid throttling
            time.sleep(0.5)
            
        except Exception as e:
            print(f"❌ Exception: {e}")
            failed += 1
    
    print(f"\n   ✅ Processed: {processed}")
    print(f"   ❌ Failed: {failed}")

def verify_sentiment_analysis(session_id):
    """Verify sentiment analysis is working"""
    print(f"\n" + "="*60)
    print("😊 VERIFYING SENTIMENT ANALYSIS")
    print("="*60)
    
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    demeanor_table = dynamodb.Table('cme-demeanor-flags')
    
    response = demeanor_table.scan(
        FilterExpression='session_id = :sid',
        ExpressionAttributeValues={':sid': session_id}
    )
    
    flags = response.get('Items', [])
    print(f"   ✅ Found {len(flags)} demeanor flags")
    
    if flags:
        print(f"\n   Sample flags:")
        for flag in flags[:5]:
            flag_type = flag.get('flag_type', 'unknown')
            severity = flag.get('severity', 'low')
            excerpt = flag.get('transcript_excerpt', '')[:100]
            print(f"   - {flag_type} ({severity}): {excerpt}...")
    else:
        print(f"   ⚠️  No demeanor flags found - sentiment analysis may not have run")

def regenerate_report(session_id):
    """Regenerate the report"""
    print(f"\n" + "="*60)
    print("📄 REGENERATING REPORT")
    print("="*60)
    
    lambda_client = boto3.client('lambda', region_name=REGION)
    
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
            report_key = result.get('report_key', '')
            print(f"   ✅ Report generated: {report_key}")
            
            # Download HTML report
            s3_client = boto3.client('s3', region_name=REGION)
            bucket = 'eve-legal-documents'
            html_path = project_root / f"cme_report_{session_id}.html"
            
            s3_client.download_file(bucket, report_key, str(html_path))
            print(f"   ✅ Downloaded to: {html_path}")
            
            return str(html_path)
        else:
            print(f"   ❌ Error: {result.get('error', 'Unknown')}")
            return None
            
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print("="*60)
    print("🔧 FIXING AND RE-PROCESSING EVERYTHING")
    print("="*60)
    print(f"\nSession ID: {SESSION_ID}\n")
    
    # Step 1: Deploy fixes
    deploy_lambda_functions()
    
    # Step 2: Get declared tests
    declared_tests = get_declared_tests(SESSION_ID)
    
    if not declared_tests:
        print("\n❌ No declared tests found! Run NLP processing first.")
        return
    
    # Step 3: Process video for all tests
    process_video_for_all_tests(SESSION_ID, declared_tests)
    
    # Step 4: Verify sentiment
    verify_sentiment_analysis(SESSION_ID)
    
    # Step 5: Regenerate report
    html_path = regenerate_report(SESSION_ID)
    
    if html_path:
        print(f"\n🎉 SUCCESS!")
        print(f"   Report: {html_path}")
        print(f"\n   Next: Run generate_pdf_from_html.py to create PDF")

if __name__ == "__main__":
    main()

