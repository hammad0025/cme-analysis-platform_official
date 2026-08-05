#!/usr/bin/env python3
"""
Wait for transcriptions to complete, then trigger the rest of the pipeline
"""
import sys
import boto3
import json
import time
import requests
from botocore.exceptions import ClientError

API_BASE_URL = "https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod"

def check_transcription_status(job_name):
    """Check if transcription job is complete"""
    transcribe = boto3.client('transcribe', region_name='us-east-1')
    
    try:
        response = transcribe.get_medical_transcription_job(MedicalTranscriptionJobName=job_name)
        job = response['MedicalTranscriptionJob']
        return job['TranscriptionJobStatus'], job.get('Transcript', {}).get('TranscriptFileUri')
    except ClientError as e:
        if e.response['Error']['Code'] == 'BadRequestException':
            # Try regular transcription
            try:
                response = transcribe.get_transcription_job(TranscriptionJobName=job_name)
                job = response['TranscriptionJob']
                return job['TranscriptionJobStatus'], job.get('Transcript', {}).get('TranscriptFileUri')
            except:
                return 'FAILED', None
        return 'FAILED', None

def wait_for_transcriptions(session_id, job_names, max_wait=3600):
    """Wait for all transcription jobs to complete"""
    print(f"\n⏳ Waiting for {len(job_names)} transcription jobs to complete...")
    print("   (This may take 10-30 minutes depending on video length)\n")
    
    start_time = time.time()
    completed = {}
    
    while len(completed) < len(job_names):
        for job_name in job_names:
            if job_name in completed:
                continue
                
            status, transcript_uri = check_transcription_status(job_name)
            
            if status == 'COMPLETED':
                print(f"✅ {job_name}: COMPLETED")
                completed[job_name] = transcript_uri
            elif status == 'FAILED':
                print(f"❌ {job_name}: FAILED")
                completed[job_name] = None
            else:
                elapsed = int(time.time() - start_time)
                print(f"⏳ {job_name}: {status} ({elapsed}s elapsed)", end='\r')
        
        if len(completed) < len(job_names):
            time.sleep(30)  # Check every 30 seconds
        
        # Check timeout
        if time.time() - start_time > max_wait:
            print(f"\n⏰ Timeout after {max_wait}s")
            break
    
    print(f"\n✅ All transcriptions checked: {len([v for v in completed.values() if v])}/{len(job_names)} completed")
    return completed

def trigger_nlp_processing(session_id):
    """Manually trigger NLP processing by calling the NLP processor Lambda"""
    print(f"\n🧠 Triggering NLP processing...")
    
    # Get session to find transcript URI
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('cme-sessions')
    
    item = table.get_item(Key={'session_id': session_id})
    if 'Item' not in item:
        print("❌ Session not found")
        return False
    
    session = item['Item']
    transcript_uri = session.get('transcript_uri')
    
    if not transcript_uri:
        print("❌ No transcript URI found")
        return False
    
    # Invoke NLP processor Lambda
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    payload = {
        'session_id': session_id,
        'transcript_uri': transcript_uri
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='cme-nlp-processor',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        print(f"✅ NLP processing triggered")
        return True
    except Exception as e:
        print(f"❌ Error triggering NLP: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 wait_and_continue_processing.py <session_id>")
        sys.exit(1)
    
    session_id = sys.argv[1]
    
    print("=" * 60)
    print("🔄 WAIT AND CONTINUE PROCESSING")
    print("=" * 60)
    print(f"Session ID: {session_id}\n")
    
    # Get transcription jobs from session
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('cme-sessions')
    
    item = table.get_item(Key={'session_id': session_id})
    if 'Item' not in item:
        print(f"❌ Session not found: {session_id}")
        sys.exit(1)
    
    session = item['Item']
    transcription_jobs = session.get('transcription_jobs', [])
    
    if not transcription_jobs:
        print("❌ No transcription jobs found in session")
        print("   Run start_transcriptions_manually.py first")
        sys.exit(1)
    
    job_names = [job.get('job_name') for job in transcription_jobs if job.get('job_name')]
    
    if not job_names:
        print("❌ No valid transcription job names found")
        sys.exit(1)
    
    # Wait for transcriptions
    completed = wait_for_transcriptions(session_id, job_names)
    
    # Check if we have completed transcriptions
    transcript_uris = [uri for uri in completed.values() if uri]
    
    if not transcript_uris:
        print("\n❌ No transcriptions completed successfully")
        sys.exit(1)
    
    # For multiple files, we need to combine transcripts first
    if len(transcript_uris) > 1:
        print(f"\n📝 Combining {len(transcript_uris)} transcripts...")
        # Invoke multi-file handler
        lambda_client = boto3.client('lambda', region_name='us-east-1')
        
        payload = {
            'session_id': session_id,
            'transcription_jobs': job_names,
            'transcript_uris': transcript_uris,
            'video_s3_keys': [rec.get('s3_key') for rec in session.get('recordings', [])]
        }
        
        try:
            response = lambda_client.invoke(
                FunctionName='multi-file-handler',
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            result = json.loads(response['Payload'].read())
            print(f"✅ Transcripts combined")
        except Exception as e:
            print(f"❌ Error combining transcripts: {e}")
            # Try to continue anyway with first transcript
            transcript_uri = transcript_uris[0]
    else:
        transcript_uri = transcript_uris[0]
    
    # Update session with transcript URI if not already set
    if not session.get('transcript_uri'):
        table.update_item(
            Key={'session_id': session_id},
            UpdateExpression='SET transcript_uri = :uri, processing_stage = :stage, updated_at = :updated',
            ExpressionAttributeValues={
                ':uri': transcript_uri if len(transcript_uris) == 1 else f"s3://cme-analysis-recordings-388846700527/cme-transcripts/{session_id}/combined.json",
                ':stage': 'transcription_complete',
                ':updated': int(time.time())
            }
        )
    
    # Trigger NLP processing
    trigger_nlp_processing(session_id)
    
    print(f"\n✅ Processing pipeline triggered!")
    print(f"   Check status: {API_BASE_URL}/cme/sessions/{session_id}")

if __name__ == "__main__":
    main()


