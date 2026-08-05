#!/usr/bin/env python3
"""
Manually start transcription jobs for all recordings in a session
"""
import sys
import boto3
import json
import time
from botocore.exceptions import ClientError

def start_transcription_for_recording(session_id: str, recording: dict, recording_index: int):
    """Start a transcription job for a single recording"""
    transcribe = boto3.client('transcribe', region_name='us-east-1')
    s3_bucket = 'cme-analysis-recordings-388846700527'
    
    # Get video URI
    video_uri = recording.get('uri', recording.get('s3_key', ''))
    if video_uri.startswith('s3://'):
        s3_path = video_uri.replace('s3://', '')
        bucket, key = s3_path.split('/', 1)
    else:
        bucket = s3_bucket
        key = video_uri
    
    filename = recording.get('filename', 'recording.mp4')
    job_name = f"cme-transcribe-{session_id}-{recording_index}-{int(time.time())}"
    
    # Output location
    output_key = f"cme-transcripts/{session_id}/transcript-{recording_index}.json"
    output_uri = f"s3://{s3_bucket}/{output_key}"
    
    print(f"\n📝 Starting transcription for {filename}...")
    print(f"   Job Name: {job_name}")
    print(f"   Input: s3://{bucket}/{key}")
    print(f"   Output: {output_uri}")
    
    try:
        response = transcribe.start_medical_transcription_job(
            MedicalTranscriptionJobName=job_name,
            Media={
                'MediaFileUri': f"s3://{bucket}/{key}"
            },
            OutputBucketName=s3_bucket,
            OutputKey=output_key,
            LanguageCode='en-US',
            Specialty='PRIMARYCARE',
            Type='CONVERSATION',
            Settings={
                'ShowSpeakerLabels': True,
                'MaxSpeakerLabels': 10,
                'ChannelIdentification': False
            }
        )
        
        print(f"   ✅ Transcription job started!")
        print(f"   Status: {response['MedicalTranscriptionJob']['TranscriptionJobStatus']}")
        return {
            'job_name': job_name,
            'status': response['MedicalTranscriptionJob']['TranscriptionJobStatus'],
            'output_uri': output_uri
        }
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ConflictException':
            print(f"   ⚠️  Job already exists: {job_name}")
            # Try to get existing job status
            try:
                existing = transcribe.get_medical_transcription_job(MedicalTranscriptionJobName=job_name)
                status = existing['MedicalTranscriptionJob']['TranscriptionJobStatus']
                print(f"   Status: {status}")
                return {
                    'job_name': job_name,
                    'status': status,
                    'output_uri': output_uri
                }
            except:
                pass
        print(f"   ❌ Error: {e}")
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 start_transcriptions_manually.py <session_id>")
        sys.exit(1)
    
    session_id = sys.argv[1]
    
    print("=" * 60)
    print("🎬 MANUAL TRANSCRIPTION STARTER")
    print("=" * 60)
    print(f"Session ID: {session_id}\n")
    
    # Get session from DynamoDB
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('cme-sessions')
    
    try:
        item = table.get_item(Key={'session_id': session_id})
        if 'Item' not in item:
            print(f"❌ Session not found: {session_id}")
            sys.exit(1)
        
        session = item['Item']
        recordings = session.get('recordings', [])
        
        if not recordings:
            print("❌ No recordings found in session")
            sys.exit(1)
        
        print(f"Found {len(recordings)} recordings\n")
        
        # Start transcription for each
        transcription_jobs = []
        for idx, recording in enumerate(recordings):
            job = start_transcription_for_recording(session_id, recording, idx)
            if job:
                transcription_jobs.append(job)
            time.sleep(1)  # Small delay between jobs
        
        # Update session with transcription jobs
        if transcription_jobs:
            table.update_item(
                Key={'session_id': session_id},
                UpdateExpression='SET transcription_jobs = :jobs, processing_stage = :stage, updated_at = :updated',
                ExpressionAttributeValues={
                    ':jobs': transcription_jobs,
                    ':stage': 'transcription',
                    ':updated': int(time.time())
                }
            )
            
            print(f"\n✅ Started {len(transcription_jobs)} transcription jobs!")
            print(f"\n⏳ Processing will take 10-30 minutes depending on video length")
            print(f"   Check status: https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod/cme/sessions/{session_id}")
        else:
            print("\n❌ Failed to start any transcription jobs")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

