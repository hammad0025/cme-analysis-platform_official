"""
Transcription Combiner - Combines multiple transcript files into one unified transcript
Handles multiple recordings per CME session
"""

import json
import boto3
import logging
import os
from typing import Dict, Any, List
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')

def combine_transcripts(transcript_uris: List[str], s3_bucket: str) -> Dict[str, Any]:
    """
    Combine multiple transcript files into one unified transcript
    
    Args:
        transcript_uris: List of S3 URIs for transcript files
        s3_bucket: S3 bucket name
        
    Returns:
        Combined transcript in AWS Transcribe format
    """
    try:
        all_items = []
        all_speakers = set()
        total_duration = 0.0
        
        # Load and combine all transcripts
        for idx, transcript_uri in enumerate(transcript_uris):
            logger.info(f"Loading transcript {idx + 1}/{len(transcript_uris)}: {transcript_uri}")
            
            # Extract S3 key from URI
            if transcript_uri.startswith('s3://'):
                key = transcript_uri.replace(f's3://{s3_bucket}/', '')
            elif transcript_uri.startswith('https://'):
                # Parse presigned URL or extract key
                key = transcript_uri.split(f'{s3_bucket}/')[-1].split('?')[0]
            else:
                key = transcript_uri
            
            # Download transcript
            response = s3_client.get_object(Bucket=s3_bucket, Key=key)
            transcript_json = response['Body'].read().decode('utf-8')
            transcript_data = json.loads(transcript_json)
            
            # Extract items and adjust timestamps
            items = transcript_data.get('results', {}).get('items', [])
            
            # Get transcript duration to offset next transcript
            job_status = transcript_data.get('jobStatus', {})
            if 'transcript' in transcript_data:
                # Medical Transcribe format
                transcript_file = transcript_data['transcript']
                if isinstance(transcript_file, str):
                    transcript_file = json.loads(transcript_file)
                transcript_duration = transcript_file.get('results', {}).get('transcripts', [{}])[0].get('transcript', '')
            else:
                # Regular Transcribe format
                transcript_duration = transcript_data.get('results', {}).get('transcripts', [{}])[0].get('transcript', '')
            
            # Calculate duration from last item
            if items:
                last_item = items[-1]
                if 'end_time' in last_item:
                    transcript_end_time = float(last_item['end_time'])
                elif 'endTime' in last_item:
                    transcript_end_time = float(last_item['endTime'])
                else:
                    transcript_end_time = 0.0
                
                # Offset timestamps by previous total duration
                for item in items:
                    if 'start_time' in item:
                        item['start_time'] = str(float(item['start_time']) + total_duration)
                    if 'end_time' in item:
                        item['end_time'] = str(float(item['end_time']) + total_duration)
                    if 'startTime' in item:
                        item['startTime'] = str(float(item['startTime']) + total_duration)
                    if 'endTime' in item:
                        item['endTime'] = str(float(item['endTime']) + total_duration)
                    
                    # Track speakers
                    if 'speaker_label' in item:
                        all_speakers.add(item['speaker_label'])
                    if 'speakerLabel' in item:
                        all_speakers.add(item['speakerLabel'])
                
                total_duration += transcript_end_time
                all_items.extend(items)
        
        # Create combined transcript structure
        combined_transcript = {
            'jobName': 'combined-transcript',
            'accountId': transcript_data.get('accountId', ''),
            'results': {
                'transcripts': [{
                    'transcript': ' '.join([
                        item.get('alternatives', [{}])[0].get('content', '') or 
                        item.get('alternatives', [{}])[0].get('transcript', '')
                        for item in all_items if item.get('type') == 'pronunciation'
                    ])
                }],
                'items': all_items,
                'speaker_labels': {
                    'speakers': len(all_speakers),
                    'segments': _create_speaker_segments(all_items)
                }
            },
            'status': 'COMPLETED',
            'total_duration': total_duration,
            'source_count': len(transcript_uris)
        }
        
        logger.info(f"Combined {len(transcript_uris)} transcripts into one with {len(all_items)} items, {len(all_speakers)} speakers")
        
        return combined_transcript
        
    except Exception as e:
        logger.error(f"Error combining transcripts: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise e

def _create_speaker_segments(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create speaker segments from items"""
    segments = []
    current_speaker = None
    current_start = None
    
    for item in items:
        speaker = item.get('speaker_label') or item.get('speakerLabel')
        start_time = float(item.get('start_time') or item.get('startTime') or 0)
        end_time = float(item.get('end_time') or item.get('endTime') or 0)
        
        if speaker != current_speaker:
            if current_speaker is not None:
                segments.append({
                    'start_time': str(current_start),
                    'end_time': str(end_time),
                    'speaker_label': current_speaker
                })
            current_speaker = speaker
            current_start = start_time
    
    # Add final segment
    if current_speaker is not None:
        segments.append({
            'start_time': str(current_start),
            'end_time': str(items[-1].get('end_time') or items[-1].get('endTime') or 0),
            'speaker_label': current_speaker
        })
    
    return segments

def handler(event, context):
    """
    Lambda handler to combine multiple transcripts
    """
    try:
        logger.info(f"Transcription Combiner invoked: {json.dumps(event)}")
        
        transcript_uris = event.get('transcript_uris', [])
        s3_bucket = event.get('s3_bucket', os.environ.get('S3_BUCKET', 'cme-analysis-recordings-388846700527'))
        session_id = event.get('session_id')
        
        if not transcript_uris:
            return {
                'statusCode': 400,
                'error': 'No transcript URIs provided'
            }
        
        # Combine transcripts
        combined_transcript = combine_transcripts(transcript_uris, s3_bucket)
        
        # Save combined transcript to S3
        if session_id:
            combined_key = f"cme-transcripts/{session_id}/transcript_combined.json"
            s3_client.put_object(
                Bucket=s3_bucket,
                Key=combined_key,
                Body=json.dumps(combined_transcript, default=str).encode('utf-8'),
                ContentType='application/json'
            )
            
            combined_uri = f"s3://{s3_bucket}/{combined_key}"
            logger.info(f"Saved combined transcript to {combined_uri}")
        else:
            combined_uri = None
        
        return {
            'statusCode': 200,
            'transcript_uri': combined_uri,
            'transcript_data': combined_transcript,
            'source_count': len(transcript_uris),
            'total_items': len(combined_transcript.get('results', {}).get('items', []))
        }
        
    except Exception as e:
        logger.error(f"Error in transcription combiner: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'statusCode': 500,
            'error': str(e)
        }

