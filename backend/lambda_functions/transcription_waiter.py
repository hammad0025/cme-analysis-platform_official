"""
Transcription Waiter Lambda - Polls AWS Transcribe job status
Used by Step Functions to wait for transcription completion
"""

import json
import boto3
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

transcribe_client = boto3.client('transcribe')
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

CME_SESSIONS_TABLE = os.environ.get('CME_SESSIONS_TABLE', 'cme-sessions')


class TranscriptionInProgressError(Exception):
    """Raised when transcription is still in progress"""
    pass


def handler(event, context):
    """
    Check transcription job status and return results when complete
    
    Raises TranscriptionInProgressError if still processing (for Step Function retry)
    """
    try:
        session_id = event['session_id']
        job_name = event['transcription_job_name']
        
        logger.info(f"Checking transcription status for job: {job_name}")
        
        # Check if it's a medical or regular transcription job
        # Try medical first, then fall back to regular
        is_medical = False
        try:
            response = transcribe_client.get_medical_transcription_job(
                MedicalTranscriptionJobName=job_name
            )
            job = response['MedicalTranscriptionJob']
            status = job['TranscriptionJobStatus']
            is_medical = True
        except Exception as med_error:
            # Not a medical job or error, try regular transcription
            error_code = med_error.response.get('Error', {}).get('Code', '') if hasattr(med_error, 'response') else ''
            if error_code == 'BadRequestException' or 'not found' in str(med_error).lower():
                try:
                    response = transcribe_client.get_transcription_job(
                        TranscriptionJobName=job_name
                    )
                    job = response['TranscriptionJob']
                    status = job['TranscriptionJobStatus']
                    is_medical = False
                except Exception as e:
                    logger.error(f"Error getting transcription job: {str(e)}")
                    raise
            else:
                # Re-raise if it's a different error
                raise
        
        logger.info(f"Transcription job status: {status}")
        
        if status == 'IN_PROGRESS' or status == 'QUEUED':
            # Still processing - raise error for Step Function retry
            raise TranscriptionInProgressError(f"Transcription still {status}")
        
        elif status == 'COMPLETED':
            # Get transcript URI (different structure for medical vs regular)
            if is_medical:
                transcript_uri = job['Transcript']['TranscriptFileUri']
            else:
                transcript_uri = job['Transcript']['TranscriptFileUri']
            
            # Download and parse transcript
            transcript_data = download_transcript(transcript_uri)
            
            # Update session with transcript URI
            sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
            sessions_table.update_item(
                Key={'session_id': session_id},
                UpdateExpression='SET transcript_uri = :uri, processing_stage = :stage, updated_at = :updated',
                ExpressionAttributeValues={
                    ':uri': transcript_uri,
                    ':stage': 'nlp_analysis',
                    ':updated': int(time.time())
                }
            )
            
            return {
                'statusCode': 200,
                'session_id': session_id,
                'status': 'COMPLETED',
                'transcript_uri': transcript_uri,
                'transcript_data': transcript_data
            }
        
        elif status == 'FAILED':
            error_message = job.get('FailureReason', 'Unknown error')
            logger.error(f"Transcription failed: {error_message}")
            
            # Update session status to error
            sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
            sessions_table.update_item(
                Key={'session_id': session_id},
                UpdateExpression='SET #status = :error, processing_stage = :stage',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':error': 'error',
                    ':stage': f'transcription_failed: {error_message}'
                }
            )
            
            return {
                'statusCode': 500,
                'error': 'Transcription failed',
                'message': error_message
            }
        
        else:
            return {
                'statusCode': 500,
                'error': f'Unknown transcription status: {status}'
            }
    
    except TranscriptionInProgressError as e:
        # Re-raise for Step Function retry
        raise e
    
    except Exception as e:
        logger.error(f"Error checking transcription: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise e


def download_transcript(transcript_uri: str) -> dict:
    """Download and parse transcript JSON from S3"""
    try:
        # Parse S3 URI
        if transcript_uri.startswith('https://'):
            # It's an HTTPS URL - extract bucket and key
            import urllib.request
            with urllib.request.urlopen(transcript_uri) as response:
                transcript_json = response.read().decode('utf-8')
                return json.loads(transcript_json)
        
        elif transcript_uri.startswith('s3://'):
            # It's an S3 URI
            uri_parts = transcript_uri.replace('s3://', '').split('/', 1)
            bucket = uri_parts[0]
            key = uri_parts[1]
            
            response = s3_client.get_object(Bucket=bucket, Key=key)
            transcript_json = response['Body'].read().decode('utf-8')
            return json.loads(transcript_json)
        
        else:
            logger.error(f"Unknown transcript URI format: {transcript_uri}")
            return {}
    
    except Exception as e:
        logger.error(f"Error downloading transcript: {str(e)}")
        return {}


import time



