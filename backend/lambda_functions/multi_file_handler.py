"""
Multi-File Handler - Orchestrates processing of multiple CME recordings
Waits for all transcriptions, combines them, and processes the unified transcript
"""

import json
import boto3
import logging
import os
import time
from typing import Dict, Any, List

logger = logging.getLogger()
logger.setLevel(logging.INFO)

transcribe_client = boto3.client('transcribe')
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

def wait_for_all_transcriptions(session_id: str, transcription_jobs: List[str]) -> List[str]:
    """
    Wait for all transcription jobs to complete and return transcript URIs
    
    Returns:
        List of transcript URIs (S3 paths)
    """
    transcript_uris = []
    
    for job_name in transcription_jobs:
        logger.info(f"Waiting for transcription job: {job_name}")
        
        # Poll until complete
        max_wait = 1800  # 30 minutes max per job
        waited = 0
        
        while waited < max_wait:
            # Try medical first
            try:
                response = transcribe_client.get_medical_transcription_job(
                    MedicalTranscriptionJobName=job_name
                )
                job = response['MedicalTranscriptionJob']
                status = job['TranscriptionJobStatus']
            except:
                # Try regular transcription
                try:
                    response = transcribe_client.get_transcription_job(
                        TranscriptionJobName=job_name
                    )
                    job = response['TranscriptionJob']
                    status = job['TranscriptionJobStatus']
                except Exception as e:
                    logger.error(f"Error checking job {job_name}: {str(e)}")
                    break
            
            if status == 'COMPLETED':
                transcript_uri = job['Transcript']['TranscriptFileUri']
                transcript_uris.append(transcript_uri)
                logger.info(f"Transcription {job_name} completed: {transcript_uri}")
                break
            elif status == 'FAILED':
                logger.error(f"Transcription {job_name} failed: {job.get('FailureReason', 'Unknown')}")
                break
            elif status in ['IN_PROGRESS', 'QUEUED']:
                time.sleep(30)  # Wait 30 seconds before checking again
                waited += 30
            else:
                logger.warning(f"Unknown status for {job_name}: {status}")
                break
    
    return transcript_uris

def combine_and_process_transcripts(
    session_id: str,
    transcript_uris: List[str],
    s3_bucket: str
) -> Dict[str, Any]:
    """
    Combine multiple transcripts and return combined transcript data
    """
    from transcription_combiner import combine_transcripts
    
    logger.info(f"Combining {len(transcript_uris)} transcripts for session {session_id}")
    
    # Combine transcripts
    combined_transcript = combine_transcripts(transcript_uris, s3_bucket)
    
    # Save combined transcript
    combined_key = f"cme-transcripts/{session_id}/transcript_combined.json"
    s3_client.put_object(
        Bucket=s3_bucket,
        Key=combined_key,
        Body=json.dumps(combined_transcript, default=str).encode('utf-8'),
        ContentType='application/json'
    )
    
    combined_uri = f"s3://{s3_bucket}/{combined_key}"
    
    logger.info(f"Combined transcript saved to {combined_uri}")
    
    return {
        'transcript_uri': combined_uri,
        'transcript_data': combined_transcript
    }

def handler(event, context):
    """
    Main handler for multi-file processing
    """
    try:
        logger.info(f"Multi-file handler invoked: {json.dumps(event)}")
        
        session_id = event.get('session_id')
        transcription_jobs = event.get('transcription_jobs', [])
        video_s3_keys = event.get('video_s3_keys', [])
        s3_bucket = os.environ.get('S3_BUCKET', 'cme-analysis-recordings-388846700527')
        
        if not session_id or not transcription_jobs:
            return {
                'statusCode': 400,
                'error': 'Missing session_id or transcription_jobs'
            }
        
        # Step 1: Wait for all transcriptions
        logger.info(f"Waiting for {len(transcription_jobs)} transcription jobs...")
        transcript_uris = wait_for_all_transcriptions(session_id, transcription_jobs)
        
        if len(transcript_uris) != len(transcription_jobs):
            logger.warning(f"Only {len(transcript_uris)}/{len(transcription_jobs)} transcriptions completed")
        
        if not transcript_uris:
            return {
                'statusCode': 500,
                'error': 'No transcriptions completed successfully'
            }
        
        # Step 2: Combine transcripts
        combined_result = combine_and_process_transcripts(
            session_id,
            transcript_uris,
            s3_bucket
        )
        
        # Step 3: Update session
        sessions_table = dynamodb.Table(os.environ.get('CME_SESSIONS_TABLE', 'cme-sessions'))
        sessions_table.update_item(
            Key={'session_id': session_id},
            UpdateExpression='SET transcript_uri = :uri, processing_stage = :stage, updated_at = :updated',
            ExpressionAttributeValues={
                ':uri': combined_result['transcript_uri'],
                ':stage': 'transcription_complete',
                ':updated': int(time.time())
            }
        )
        
        return {
            'statusCode': 200,
            'session_id': session_id,
            'transcript_uri': combined_result['transcript_uri'],
            'transcript_data': combined_result['transcript_data'],
            'source_transcript_count': len(transcript_uris),
            'video_s3_keys': video_s3_keys,
            'message': f'Successfully combined {len(transcript_uris)} transcripts'
        }
        
    except Exception as e:
        logger.error(f"Error in multi-file handler: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'statusCode': 500,
            'error': str(e)
        }

