"""
CME Analysis Platform - Handler for Compulsory Medical Examination Analysis
Implements the Florida happy-path workflow for AI-powered CME recording analysis
"""

import json
import boto3
import logging
from typing import Dict, Any, Optional, List
import os
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
transcribe_client = boto3.client('transcribe')
comprehend_client = boto3.client('comprehend')
bedrock_client = boto3.client('bedrock-runtime')
stepfunctions_client = boto3.client('stepfunctions')

# Environment variables
S3_BUCKET = os.environ.get('S3_BUCKET', 'eve-legal-documents')
CME_SESSIONS_TABLE = os.environ.get('CME_SESSIONS_TABLE', 'cme-sessions')
CME_STEPS_TABLE = os.environ.get('CME_STEPS_TABLE', 'cme-declared-steps')
CME_ACTIONS_TABLE = os.environ.get('CME_ACTIONS_TABLE', 'cme-observed-actions')
CME_DEMEANOR_TABLE = os.environ.get('CME_DEMEANOR_TABLE', 'cme-demeanor-flags')
CME_CONSENT_TABLE = os.environ.get('CME_CONSENT_TABLE', 'cme-consents')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# State configurations for recording permissions
STATE_RECORDING_RULES = {
    'FL': {'video': True, 'audio': True, 'mode': 'Full Record', 'rule': 'Rule 1.360'},
    'PA': {'video': False, 'audio': True, 'mode': 'Audio Only', 'rule': 'Pennsylvania law'},
    'CA': {'video': True, 'audio': True, 'mode': 'Full Record', 'rule': 'CCP §2032.320'},
    'TX': {'video': False, 'audio': False, 'mode': 'Ephemeral', 'rule': 'Texas Civil Practice'},
    # Default for states not explicitly configured
    'DEFAULT': {'video': False, 'audio': False, 'mode': 'Ephemeral', 'rule': 'Jurisdictional rules apply'}
}

# Medical test taxonomy for intent detection
TEST_TAXONOMY = {
    'spine': ['spine', 'spinal', 'vertebra', 'vertebrae', 'back'],
    'lumbar_rom': ['lumbar', 'lower back', 'range of motion', 'rom', 'flexion', 'extension'],
    'straight_leg_raise': ['straight leg', 'slr', 'leg raise', 'lasegue'],
    'waddells_signs': ['waddell', 'non-organic', 'behavioral'],
    'cervical_rom': ['cervical', 'neck', 'rotation', 'lateral flexion'],
    'gait': ['gait', 'walking', 'ambulation', 'mobility'],
    'neurological': ['reflex', 'reflexes', 'sensation', 'sensory', 'motor', 'strength'],
    'palpation': ['palpate', 'palpating', 'feel', 'touch', 'tender'],
    'orthopedic': ['orthopedic', 'musculoskeletal', 'joint'],
    'cognitive': ['memory', 'concentration', 'cognitive', 'mental status']
}


class CMEDataModel:
    """Data models for CME analysis"""
    
    @staticmethod
    def create_exam_session(
        patient_id: str,
        doctor_name: str,
        state: str,
        video_uri: Optional[str] = None,
        consent_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create ExamSession data model"""
        session_id = f"cme_{uuid.uuid4().hex[:12]}"
        timestamp = int(time.time())
        
        recording_rules = STATE_RECORDING_RULES.get(state.upper(), STATE_RECORDING_RULES['DEFAULT'])
        
        return {
            'session_id': session_id,
            'patient_id': patient_id,
            'doctor_name': doctor_name,
            'state': state.upper(),
            'mode': recording_rules['mode'],
            'recording_allowed': recording_rules,
            'video_uri': video_uri or '',
            'transcript_uri': '',
            'consent_hash': consent_hash or '',
            'status': 'created',
            'created_at': timestamp,
            'updated_at': timestamp,
            'processing_stage': 'session_setup',
            'metadata': {}
        }
    
    @staticmethod
    def create_declared_step(
        session_id: str,
        timestamp: float,
        label: str,
        transcript_text: str,
        confidence: float = 0.0
    ) -> Dict[str, Any]:
        """Create DeclaredStep data model"""
        step_id = f"step_{uuid.uuid4().hex[:12]}"
        
        return {
            'declared_step_id': step_id,
            'session_id': session_id,
            'timestamp': Decimal(str(timestamp)),
            'label': label,
            'transcript_text': transcript_text,
            'confidence': Decimal(str(confidence)),
            'video_snippet_uri': '',
            'created_at': int(time.time())
        }
    
    @staticmethod
    def create_observed_action(
        declared_step_id: str,
        motion_present: str,
        pose_match: str,
        confidence_score: float
    ) -> Dict[str, Any]:
        """Create ObservedAction data model"""
        action_id = f"action_{uuid.uuid4().hex[:12]}"
        
        return {
            'observed_action_id': action_id,
            'declared_step_id': declared_step_id,
            'motion_present': motion_present,  # 'performed', 'brief', 'not_observed'
            'pose_match': pose_match,  # 'full_match', 'partial', 'no_match'
            'confidence_score': Decimal(str(confidence_score)),
            'analysis_details': {},
            'created_at': int(time.time())
        }
    
    @staticmethod
    def create_demeanor_flag(
        session_id: str,
        timestamp: float,
        flag_type: str,
        transcript_excerpt: str,
        severity: str = 'low'
    ) -> Dict[str, Any]:
        """Create DemeanorFlag data model"""
        flag_id = f"flag_{uuid.uuid4().hex[:12]}"
        
        return {
            'flag_id': flag_id,
            'session_id': session_id,
            'timestamp': Decimal(str(timestamp)),
            'flag_type': flag_type,  # 'negative_tone', 'interruption', 'dismissive', 'aggressive'
            'transcript_excerpt': transcript_excerpt,
            'severity': severity,  # 'low', 'medium', 'high'
            'created_at': int(time.time())
        }
    
    @staticmethod
    def create_consent_record(
        session_id: str,
        participant_role: str,
        signature: str,
        consent_text: str
    ) -> Dict[str, Any]:
        """Create ConsentRecord data model"""
        consent_id = f"consent_{uuid.uuid4().hex[:12]}"
        timestamp = int(time.time())
        
        return {
            'consent_id': consent_id,
            'session_id': session_id,
            'participant_role': participant_role,  # 'patient', 'examiner', 'attorney'
            'signature': signature,
            'consent_text': consent_text,
            'timestamp': timestamp,
            'ip_address': '',
            'created_at': timestamp
        }


def handle_create_cme_session(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 1: Session Setup & Consent
    Create a new CME analysis session with state-aware recording permissions
    """
    try:
        # Extract session parameters
        patient_id = body.get('patient_id')
        patient_name = body.get('patient_name')
        doctor_name = body.get('doctor_name')
        state = body.get('state', 'FL')  # Default to Florida
        exam_date = body.get('exam_date', datetime.now().strftime('%Y-%m-%d'))
        case_id = body.get('case_id')
        attorney_name = body.get('attorney_name')
        
        if not all([patient_id, doctor_name]):
            return create_response(400, {
                'error': 'Missing required fields',
                'required': ['patient_id', 'doctor_name']
            })
        
        # Get recording rules for the state
        state_upper = state.upper()
        recording_rules = STATE_RECORDING_RULES.get(state_upper, STATE_RECORDING_RULES['DEFAULT'])
        
        logger.info(f"Creating CME session for state: {state_upper}, mode: {recording_rules['mode']}")
        
        # Create session data model
        session_data = CMEDataModel.create_exam_session(
            patient_id=patient_id,
            doctor_name=doctor_name,
            state=state_upper
        )
        
        # Add additional metadata
        session_data['patient_name'] = patient_name or ''
        session_data['exam_date'] = exam_date
        session_data['case_id'] = case_id or ''
        session_data['attorney_name'] = attorney_name or ''
        
        # Store session in DynamoDB
        sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
        sessions_table.put_item(Item=session_data)
        
        logger.info(f"CME session created: {session_data['session_id']}")
        
        # Generate consent form text based on state
        consent_text = generate_consent_text(state_upper, recording_rules)
        
        return create_response(201, {
            'session_id': session_data['session_id'],
            'state': state_upper,
            'recording_mode': recording_rules['mode'],
            'recording_allowed': {
                'video': recording_rules['video'],
                'audio': recording_rules['audio']
            },
            'legal_basis': recording_rules['rule'],
            'consent_required': True,
            'consent_text': consent_text,
            'message': f"CME session created in {recording_rules['mode']} mode for {state_upper}",
            'session': session_data
        })
        
    except Exception as e:
        logger.error(f"Error creating CME session: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return create_response(500, {'error': f'Error creating CME session: {str(e)}'})


def handle_submit_consent(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Submit digital consent for CME recording
    """
    try:
        session_id = body.get('session_id')
        participant_role = body.get('participant_role')  # 'patient', 'examiner', 'attorney'
        signature = body.get('signature')
        consent_text = body.get('consent_text')
        ip_address = body.get('ip_address', '')
        
        if not all([session_id, participant_role, signature]):
            return create_response(400, {
                'error': 'Missing required fields',
                'required': ['session_id', 'participant_role', 'signature']
            })
        
        # Create consent record
        consent_data = CMEDataModel.create_consent_record(
            session_id=session_id,
            participant_role=participant_role,
            signature=signature,
            consent_text=consent_text or ''
        )
        consent_data['ip_address'] = ip_address
        
        # Store consent in DynamoDB
        consent_table = dynamodb.Table(CME_CONSENT_TABLE)
        consent_table.put_item(Item=consent_data)
        
        # Update session with consent hash
        sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
        sessions_table.update_item(
            Key={'session_id': session_id},
            UpdateExpression='SET consent_hash = :hash, updated_at = :updated',
            ExpressionAttributeValues={
                ':hash': consent_data['consent_id'],
                ':updated': int(time.time())
            }
        )
        
        logger.info(f"Consent submitted for session {session_id} by {participant_role}")
        
        return create_response(200, {
            'consent_id': consent_data['consent_id'],
            'session_id': session_id,
            'participant_role': participant_role,
            'timestamp': consent_data['timestamp'],
            'message': 'Consent recorded successfully'
        })
        
    except Exception as e:
        logger.error(f"Error submitting consent: {str(e)}")
        return create_response(500, {'error': f'Error submitting consent: {str(e)}'})


def handle_upload_cme_recording(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 2: Data Ingestion & Storage
    Generate presigned URL for CME recording upload (video/audio)
    """
    try:
        session_id = body.get('session_id')
        filename = body.get('filename', 'recording.mp4')
        content_type = body.get('content_type', 'video/mp4')
        file_size = body.get('file_size', 0)
        
        if not session_id:
            return create_response(400, {'error': 'session_id is required'})
        
        # Verify session exists
        sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
        session_response = sessions_table.get_item(Key={'session_id': session_id})
        session = session_response.get('Item')
        
        if not session:
            return create_response(404, {'error': 'CME session not found'})
        
        # Determine file type and validate against state rules
        is_video = content_type.startswith('video/')
        is_audio = content_type.startswith('audio/')
        
        recording_rules = session.get('recording_allowed', {})
        
        if is_video and not recording_rules.get('video'):
            return create_response(403, {
                'error': f"Video recording not permitted in {session.get('state')}",
                'allowed': recording_rules
            })
        
        if not is_video and not is_audio:
            return create_response(400, {'error': 'File must be video or audio format'})
        
        # Generate S3 key
        file_extension = filename.split('.')[-1] if '.' in filename else 'mp4'
        s3_key = f"cme-recordings/{session_id}/recording.{file_extension}"
        
        # Generate presigned URL for upload (valid for 2 hours for large files)
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': S3_BUCKET,
                'Key': s3_key,
                'ContentType': content_type
            },
            ExpiresIn=7200  # 2 hours
        )
        
        # Update session with recording URI
        sessions_table.update_item(
            Key={'session_id': session_id},
            UpdateExpression='SET video_uri = :uri, status = :status, updated_at = :updated, processing_stage = :stage',
            ExpressionAttributeValues={
                ':uri': f"s3://{S3_BUCKET}/{s3_key}",
                ':status': 'recording_uploaded',
                ':updated': int(time.time()),
                ':stage': 'ingestion'
            }
        )
        
        logger.info(f"Generated upload URL for CME recording: {session_id}")
        
        return create_response(200, {
            'session_id': session_id,
            'upload_url': presigned_url,
            's3_key': s3_key,
            'expires_in': 7200,
            'message': 'Upload recording to this URL, then processing will begin automatically'
        })
        
    except Exception as e:
        logger.error(f"Error creating CME recording upload URL: {str(e)}")
        return create_response(500, {'error': f'Error creating upload URL: {str(e)}'})


def handle_start_cme_processing(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trigger CME processing pipeline after recording upload
    This initiates Steps 3-8: Transcription, NLP, CV, Demeanor Analysis, Report
    """
    try:
        session_id = body.get('session_id')
        
        if not session_id:
            return create_response(400, {'error': 'session_id is required'})
        
        # Get session details
        sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
        session_response = sessions_table.get_item(Key={'session_id': session_id})
        session = session_response.get('Item')
        
        if not session:
            return create_response(404, {'error': 'CME session not found'})
        
        if not session.get('video_uri'):
            return create_response(400, {'error': 'No recording uploaded for this session'})
        
        # Update session status
        sessions_table.update_item(
            Key={'session_id': session_id},
            UpdateExpression='SET status = :status, processing_stage = :stage, updated_at = :updated',
            ExpressionAttributeValues={
                ':status': 'processing',
                ':stage': 'transcription',
                ':updated': int(time.time())
            }
        )
        
        # Start Step 3: Speech-to-Text & Diarization
        transcription_job = start_transcription_job(session)
        
        logger.info(f"Started CME processing for session: {session_id}")
        
        return create_response(200, {
            'session_id': session_id,
            'status': 'processing',
            'stage': 'transcription',
            'transcription_job': transcription_job,
            'message': 'CME analysis processing started',
            'estimated_time': 'Processing time depends on recording length (typically 5-15 minutes)'
        })
        
    except Exception as e:
        logger.error(f"Error starting CME processing: {str(e)}")
        return create_response(500, {'error': f'Error starting processing: {str(e)}'})


def start_transcription_job(session: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 3: Speech-to-Text & Speaker Diarization
    Start AWS Transcribe Medical job with speaker identification
    """
    try:
        session_id = session['session_id']
        video_uri = session['video_uri']
        
        # Extract S3 bucket and key from URI
        if video_uri.startswith('s3://'):
            s3_path = video_uri.replace('s3://', '')
            bucket, key = s3_path.split('/', 1)
        else:
            bucket = S3_BUCKET
            key = video_uri
        
        job_name = f"cme-transcribe-{session_id}-{int(time.time())}"
        
        # Start transcription job with medical vocabulary and speaker diarization
        response = transcribe_client.start_medical_transcription_job(
            MedicalTranscriptionJobName=job_name,
            LanguageCode='en-US',
            MediaFormat='mp4',  # Or detect from file extension
            Media={
                'MediaFileUri': f"s3://{bucket}/{key}"
            },
            OutputBucketName=bucket,
            OutputKey=f"cme-transcripts/{session_id}/transcript.json",
            Settings={
                'ShowSpeakerLabels': True,
                'MaxSpeakerLabels': 5,  # Examiner, patient, and possibly observers
                'ChannelIdentification': False
            },
            Specialty='PRIMARYCARE',
            Type='CONVERSATION'
        )
        
        logger.info(f"Started transcription job: {job_name}")
        
        return {
            'job_name': job_name,
            'status': 'IN_PROGRESS',
            'output_uri': f"s3://{bucket}/cme-transcripts/{session_id}/transcript.json"
        }
        
    except Exception as e:
        logger.error(f"Error starting transcription: {str(e)}")
        return {'error': str(e)}


def generate_consent_text(state: str, recording_rules: Dict[str, Any]) -> str:
    """Generate state-specific consent form text"""
    
    if state == 'FL':
        return f"""FLORIDA CME RECORDING CONSENT

Under Florida Rules of Civil Procedure {recording_rules['rule']}, the injured party has the right to record this Compulsory Medical Examination (CME).

By signing below, you acknowledge:

1. This examination is being recorded (video and audio) by the plaintiff or their legal representative.
2. The recording is the property of the plaintiff and their attorney.
3. The recording is protected from discovery unless used as impeachment material or if work-product privilege is waived.
4. The examiner may not interfere with the plaintiff's right to record this examination.
5. This recording may be used for legal purposes including case analysis, trial preparation, and expert consultation.

Recording Mode: {recording_rules['mode']}
Video Recording: {"Permitted" if recording_rules['video'] else "Not Permitted"}
Audio Recording: {"Permitted" if recording_rules['audio'] else "Not Permitted"}

Legal Basis: Florida Rules of Civil Procedure Rule 1.360 and 19th Judicial Circuit guidelines.

By providing your signature, you consent to being recorded during this CME and acknowledge the above terms."""
    
    else:
        return f"""CME RECORDING CONSENT - {state}

This Compulsory Medical Examination may be recorded in accordance with applicable state law.

Recording Mode: {recording_rules['mode']}
Video Recording: {"Permitted" if recording_rules['video'] else "Not Permitted"}
Audio Recording: {"Permitted" if recording_rules['audio'] else "Not Permitted"}

Legal Basis: {recording_rules['rule']}

By providing your signature, you consent to any permitted recording of this examination."""


def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create API Gateway response with CORS headers"""
    # Convert Decimal types to float for JSON serialization
    def decimal_default(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps(body, default=decimal_default)
    }


def handler(event, context):
    """Main Lambda handler for CME operations"""
    try:
        logger.info(f"CME Handler - Event: {json.dumps(event)}")
        
        # Parse request
        http_method = event.get('httpMethod', 'POST')
        path = event.get('path', '/')
        body = json.loads(event.get('body', '{}')) if event.get('body') else {}
        
        # Handle OPTIONS for CORS
        if http_method == 'OPTIONS':
            return create_response(200, {})
        
        # Route to appropriate handler
        if path.endswith('/cme/sessions') and http_method == 'POST':
            return handle_create_cme_session(body)
        elif path.endswith('/cme/consent') and http_method == 'POST':
            return handle_submit_consent(body)
        elif path.endswith('/cme/upload') and http_method == 'POST':
            return handle_upload_cme_recording(body)
        elif path.endswith('/cme/process') and http_method == 'POST':
            return handle_start_cme_processing(body)
        else:
            return create_response(404, {'error': 'Endpoint not found'})
    
    except Exception as e:
        logger.error(f"Error in CME handler: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return create_response(500, {'error': str(e)})

