"""
Lambda handler for MediaConvert job completion
Triggers transcription automatically when MPEG conversion completes
"""

import json
import boto3
import logging
import os
from typing import Dict, Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
transcribe_client = boto3.client('transcribe')
mediaconvert_client = boto3.client('mediaconvert', region_name=os.environ.get('AWS_REGION', 'us-east-1'))

# Environment variables
CME_SESSIONS_TABLE = os.environ.get('CME_SESSIONS_TABLE', 'cme-sessions')
S3_BUCKET = os.environ.get('S3_BUCKET', 'cme-analysis-recordings-388846700527')


def _mark_session_error_for_job(job_id: str, *, stage: str, error: str) -> None:
    """Find the session owning this MediaConvert job and mark it failed."""
    import time
    try:
        sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
        response = sessions_table.scan(
            FilterExpression='conversion_job_id = :job_id',
            ExpressionAttributeValues={':job_id': job_id}
        )
        for session in response.get('Items', []):
            sessions_table.update_item(
                Key={'session_id': session['session_id']},
                UpdateExpression=(
                    'SET #status = :status, processing_stage = :stage, '
                    'last_error = :err, updated_at = :updated'
                ),
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'error',
                    ':stage': stage,
                    ':err': error[:500],
                    ':updated': int(time.time()),
                },
            )
            logger.error(f"Marked session {session['session_id']} failed: {error}")
    except Exception as e:
        logger.error(f"Failed to mark session error for job {job_id}: {e}")


def handler(event, context):
    """
    Handle MediaConvert job completion event
    Triggered by EventBridge when MediaConvert job status changes
    """
    try:
        logger.info(f"MediaConvert completion event: {json.dumps(event)}")
        
        # Extract job details from EventBridge event
        detail = event.get('detail', {})
        job_id = detail.get('jobId')
        status = detail.get('status')
        
        if not job_id:
            logger.error("No job ID in event")
            return {'statusCode': 400, 'body': 'Missing job ID'}
        
        logger.info(f"MediaConvert job {job_id} status: {status}")
        
        if status in ('ERROR', 'CANCELED'):
            # Terminal failure: mark the session so it does not sit in
            # 'converting'/'processing' forever with no way forward.
            _mark_session_error_for_job(
                job_id,
                stage='conversion_failed',
                error=f"MediaConvert job {job_id} ended with status {status}",
            )
            return {'statusCode': 200, 'body': f'Job {status}; session marked failed'}
        
        if status != 'COMPLETE':
            logger.info(f"Job {job_id} not complete yet (status: {status}), ignoring")
            return {'statusCode': 200, 'body': f'Job {status}, not triggering transcription'}
        
        # Extract output file path from EventBridge event (it's already in the event!)
        try:
            # The output file path is in the event detail
            output_group_details = detail.get('outputGroupDetails', [])
            if not output_group_details:
                logger.error(f"No output details in event for job {job_id}")
                return {'statusCode': 500, 'body': 'No output details in event'}
            
            output_file_paths = output_group_details[0].get('outputDetails', [{}])[0].get('outputFilePaths', [])
            if not output_file_paths:
                logger.error(f"No output file paths in event for job {job_id}")
                return {'statusCode': 500, 'body': 'No output file paths in event'}
            
            output_uri = output_file_paths[0]
            logger.info(f"Conversion complete! Output file: {output_uri}")
            
            # Extract S3 path
            if output_uri.startswith('s3://'):
                s3_path = output_uri.replace('s3://', '')
                bucket, converted_key = s3_path.split('/', 1)
            else:
                logger.error(f"Invalid output URI format: {output_uri}")
                return {'statusCode': 500, 'body': 'Invalid output URI'}
            
            # Find session by conversion_job_id
            sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
            
            # Scan for session with this conversion_job_id (not ideal but necessary)
            response = sessions_table.scan(
                FilterExpression='conversion_job_id = :job_id',
                ExpressionAttributeValues={':job_id': job_id}
            )
            
            if not response.get('Items'):
                logger.error(f"No session found with conversion_job_id: {job_id}")
                return {'statusCode': 404, 'body': 'Session not found'}
            
            session = response['Items'][0]
            session_id = session['session_id']
            
            logger.info(f"Found session {session_id} for conversion job {job_id}")
            
            # Update session with converted file path
            sessions_table.update_item(
                Key={'session_id': session_id},
                UpdateExpression='SET converted_video_uri = :uri, video_uri = :uri, processing_stage = :stage, updated_at = :updated',
                ExpressionAttributeValues={
                    ':uri': output_uri,
                    ':stage': 'conversion_complete',
                    ':updated': int(__import__('time').time())
                }
            )
            
            # Now trigger transcription on the converted file
            logger.info(f"Starting transcription for converted file: {output_uri}")
            
            # Call the API handler to start transcription (better than importing)
            import requests
            api_url = os.environ.get('API_URL', 'https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod')
            
            try:
                # Trigger processing which will start transcription
                response = requests.post(
                    f'{api_url}/cme/process',
                    json={'session_id': session_id},
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                
                if response.status_code == 200:
                    transcription_result = response.json()
                    logger.info(f"Transcription triggered: {transcription_result}")
                else:
                    logger.error(f"Failed to trigger transcription: {response.status_code} - {response.text}")
                    transcription_result = {'status': 'FAILED', 'error': f'API returned {response.status_code}'}
            except Exception as api_error:
                logger.error(f"Error calling API to start transcription: {str(api_error)}")
                transcription_result = {'status': 'FAILED', 'error': str(api_error)}
            
            if transcription_result.get('status') == 'FAILED':
                logger.error(f"Transcription failed: {transcription_result.get('error')}")
                sessions_table.update_item(
                    Key={'session_id': session_id},
                    UpdateExpression=(
                        'SET #status = :status, processing_stage = :stage, '
                        'last_error = :err, updated_at = :updated'
                    ),
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={
                        ':status': 'error',
                        ':stage': 'transcription_failed',
                        ':err': str(transcription_result.get('error') or 'transcription trigger failed')[:500],
                        ':updated': int(__import__('time').time())
                    }
                )
                return {'statusCode': 500, 'body': f"Transcription failed: {transcription_result.get('error')}"}
            
            logger.info(f"Transcription started successfully for session {session_id}")
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Conversion complete, transcription started',
                    'session_id': session_id,
                    'transcription_job': transcription_result.get('job_name')
                })
            }
            
        except Exception as e:
            logger.error(f"Error processing MediaConvert completion: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {'statusCode': 500, 'body': str(e)}
            
    except Exception as e:
        logger.error(f"Error in MediaConvert completion handler: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {'statusCode': 500, 'body': str(e)}

