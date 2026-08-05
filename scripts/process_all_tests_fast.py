#!/usr/bin/env python3
"""Process all tests using fast heuristic approach"""

import boto3
import json
import time
from decimal import Decimal

SESSION_ID = 'cme_7285456d8748'
REGION = 'us-east-1'

lambda_client = boto3.client('lambda', region_name=REGION)
dynamodb = boto3.resource('dynamodb', region_name=REGION)

# Get all tests
steps_table = dynamodb.Table('cme-declared-steps')
steps_response = steps_table.scan(FilterExpression='session_id = :sid', ExpressionAttributeValues={':sid': SESSION_ID})
tests = steps_response.get('Items', [])

print(f'📋 Found {len(tests)} tests')

# Get video
sessions_table = dynamodb.Table('cme-sessions')
session = sessions_table.get_item(Key={'session_id': SESSION_ID}).get('Item', {})
video_uri = session.get('video_uri', '')
if video_uri.startswith('s3://'):
    parts = video_uri.replace('s3://', '').split('/', 1)
    video_s3_key = parts[1] if len(parts) > 1 else ''
else:
    recordings = session.get('recordings', [])
    if recordings:
        uri = recordings[0].get('uri', recordings[0].get('s3_key', ''))
        if uri.startswith('s3://'):
            parts = uri.replace('s3://', '').split('/', 1)
            video_s3_key = parts[1] if len(parts) > 1 else ''
        else:
            video_s3_key = uri
    else:
        video_s3_key = ''

if not video_s3_key:
    print('❌ No video found!')
    exit(1)

print(f'🎥 Video: {video_s3_key}')
print(f'\n🚀 Processing all {len(tests)} tests...\n')

processed = 0
failed = 0

for i, test in enumerate(tests, 1):
    test_label = test.get('label', 'unknown')
    test_timestamp = float(test.get('timestamp', 0))
    declared_step_id = test.get('declared_step_id', '')
    
    if i % 10 == 0:
        print(f'[{i}/{len(tests)}] Processing...')
    
    payload = {
        'session_id': SESSION_ID,
        'declared_test': {
            'declared_step_id': declared_step_id,
            'label': test_label,
            'timestamp': test_timestamp,
            'transcript_text': test.get('transcript_text', '')
        },
        'video_s3_key': video_s3_key
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='cme-video-processor',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        result = json.loads(response['Payload'].read().decode('utf-8'))
        if result.get('statusCode') == 200:
            processed += 1
        else:
            failed += 1
        time.sleep(0.1)  # Small delay
    except Exception as e:
        failed += 1
        if i <= 5:  # Show first few errors
            print(f'   Error: {e}')

print(f'\n✅ Processed: {processed}')
print(f'❌ Failed: {failed}')
print(f'\n🎉 Done!')

