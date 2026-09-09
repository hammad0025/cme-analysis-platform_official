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
lambda_client = boto3.client('lambda')

# Environment variables
S3_BUCKET = os.environ.get('S3_BUCKET', 'cme-analysis-recordings-388846700527')
CME_SESSIONS_TABLE = os.environ.get('CME_SESSIONS_TABLE', 'cme-sessions')
CME_STEPS_TABLE = os.environ.get('CME_STEPS_TABLE', 'cme-declared-steps')
CME_ACTIONS_TABLE = os.environ.get('CME_ACTIONS_TABLE', 'cme-observed-actions')
CME_DEMEANOR_TABLE = os.environ.get('CME_DEMEANOR_TABLE', 'cme-demeanor-flags')
CME_CONSENT_TABLE = os.environ.get('CME_CONSENT_TABLE', 'cme-consents')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
STEP_FUNCTION_ARN = os.environ.get('STEP_FUNCTION_ARN', '')
NLP_PROCESSOR_FUNCTION = os.environ.get('NLP_PROCESSOR_FUNCTION', 'cme-nlp-processor')
REPORT_GENERATOR_FUNCTION = os.environ.get('REPORT_GENERATOR_FUNCTION', 'cme-report-generator')

# If a session sits in the same stage longer than this, the GET-poll
# fallback re-invokes the next pipeline step instead of waiting forever.
STUCK_STAGE_RETRY_SEC = 15 * 60

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


def handle_list_cme_sessions() -> Dict[str, Any]:
    """
    GET /cme/sessions - List all CME sessions
    """
    try:
        sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
        
        # Scan all sessions
        response = sessions_table.scan()
        sessions = response.get('Items', [])
        
        # Convert Decimal to float for JSON serialization
        for session in sessions:
            if 'created_at' in session:
                session['created_at'] = int(session['created_at'])
            if 'updated_at' in session:
                session['updated_at'] = int(session['updated_at'])
            if session.get('status') == 'completed':
                session = _attach_artifact_urls(session)

        return create_response(200, {'sessions': sessions})
    
    except Exception as e:
        logger.error(f"Error listing sessions: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return create_response(500, {'error': str(e)})


def _presign_s3_key(key: str, expires: int = 86400, bucket: Optional[str] = None) -> str:
    """Return a presigned GET URL for an object in the CME recordings bucket."""
    return s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket or S3_BUCKET, 'Key': key},
        ExpiresIn=expires,
    )


def _parse_s3_https_url(uri: str) -> Optional[tuple]:
    """Parse an https S3 URL (path-style or virtual-hosted) into (bucket, key)."""
    from urllib.parse import urlparse, unquote
    try:
        parsed = urlparse(uri)
    except Exception:
        return None
    host = (parsed.netloc or '').lower()
    path = unquote(parsed.path or '').lstrip('/')
    if not host.endswith('.amazonaws.com'):
        return None
    # Path-style: s3.amazonaws.com/bucket/key or s3.<region>.amazonaws.com/bucket/key
    if host == 's3.amazonaws.com' or host.startswith('s3.') or host.startswith('s3-'):
        parts = path.split('/', 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            return parts[0], parts[1]
        return None
    # Virtual-hosted style: <bucket>.s3.<region>.amazonaws.com/key
    if '.s3.' in host or '.s3-' in host:
        bucket = host.split('.s3.', 1)[0] if '.s3.' in host else host.split('.s3-', 1)[0]
        if bucket and path:
            return bucket, path
    return None


def _s3_bucket_key_from_uri(uri: str) -> Optional[tuple]:
    """Resolve any stored URI form (s3://, https S3 URL, bare key) to (bucket, key)."""
    if not uri:
        return None
    if uri.startswith('s3://'):
        parts = uri.replace('s3://', '').split('/', 1)
        return (parts[0], parts[1]) if len(parts) > 1 else None
    if uri.startswith('https://') or uri.startswith('http://'):
        return _parse_s3_https_url(uri)
    return (S3_BUCKET, uri)


def _s3_key_from_uri(uri: str) -> Optional[str]:
    """Extract object key from s3://bucket/key, https S3 URL, or bare key."""
    parsed = _s3_bucket_key_from_uri(uri)
    return parsed[1] if parsed else None


def _normalize_s3_uri(uri: str) -> str:
    """Normalize an https S3 URL to s3://bucket/key for stable storage."""
    if uri and (uri.startswith('https://') or uri.startswith('http://')):
        parsed = _parse_s3_https_url(uri)
        if parsed:
            return f"s3://{parsed[0]}/{parsed[1]}"
    return uri


def _attach_playback_urls(session: Dict[str, Any]) -> Dict[str, Any]:
    """Presign recording and transcript URLs for browser playback."""
    recordings = session.get('recordings')
    if not isinstance(recordings, list):
        recordings = []
    if not recordings and session.get('video_uri'):
        recordings = [{
            'uri': session.get('video_uri'),
            'filename': 'recording.mp4',
            'display_label': 'Video 1',
            'recording_slot': 1,
        }]

    enriched: List[Dict[str, Any]] = []
    for rec in recordings:
        if not isinstance(rec, dict):
            continue
        entry = dict(rec)
        key = entry.get('s3_key') or _s3_key_from_uri(entry.get('uri') or '')
        if key:
            try:
                entry['video_playback_url'] = _presign_s3_key(key)
            except Exception as exc:
                logger.warning(f"Could not presign recording {key}: {exc}")
        enriched.append(entry)
    if enriched:
        session['recordings'] = enriched
        if enriched[0].get('video_playback_url'):
            session['video_playback_url'] = enriched[0]['video_playback_url']

    transcript_uri = (session.get('transcript_uri') or '').strip()
    transcript_loc = _s3_bucket_key_from_uri(transcript_uri)
    if transcript_loc:
        transcript_bucket, transcript_key = transcript_loc
        try:
            session['transcript_url'] = _presign_s3_key(transcript_key, bucket=transcript_bucket)
        except Exception as exc:
            logger.warning(f"Could not presign transcript {transcript_key}: {exc}")

    return session


def _attach_doctor_report_url(session: Dict[str, Any]) -> Dict[str, Any]:
    """Presign the defense examiner's uploaded doctor report for download/view."""
    dr = session.get('doctor_report')
    if not isinstance(dr, dict):
        return session
    key = dr.get('s3_key') or _s3_key_from_uri(dr.get('uri') or '')
    if not key:
        return session
    try:
        enriched = dict(dr)
        enriched['download_url'] = _presign_s3_key(key)
        session['doctor_report'] = enriched
    except Exception as exc:
        logger.warning(f"Could not presign doctor report {key}: {exc}")
    return session


def _attach_artifact_urls(session: Dict[str, Any]) -> Dict[str, Any]:
    """Refresh presigned URLs for backfilled or completed analysis artifacts."""
    artifacts = session.get('analysis_artifacts')
    if isinstance(artifacts, dict) and artifacts:
        urls: Dict[str, str] = {}
        for label, key in artifacts.items():
            if isinstance(key, str) and key:
                try:
                    urls[label] = _presign_s3_key(key)
                except Exception as exc:
                    logger.warning(f"Could not presign {key}: {exc}")
        if urls:
            session['artifact_urls'] = urls

    session = _attach_playback_urls(session)
    return session


def handle_get_cme_report(session_id: str, query: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    GET /cme/sessions/{session_id}/report — presigned download for linked or generated report.
    Does not invoke vision/Bedrock; uses pre-uploaded S3 objects when present.
    """
    try:
        sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
        response = sessions_table.get_item(Key={'session_id': session_id})
        if 'Item' not in response:
            return create_response(404, {'error': 'Session not found'})

        session = response['Item']
        fmt = (query or {}).get('format', 'pdf').lower()
        artifacts = session.get('analysis_artifacts') or {}

        key_by_format = {
            'html': artifacts.get('standard_report_html') or artifacts.get('report_html')
            or f"cme-reports/{session_id}/report.html",
            'pdf': artifacts.get('standard_report_pdf') or artifacts.get('report_pdf')
            or f"cme-reports/{session_id}/standard_report.pdf",
        }

        def _object_exists(k: str) -> bool:
            try:
                s3_client.head_object(Bucket=S3_BUCKET, Key=k)
                return True
            except Exception:
                return False

        key = key_by_format['pdf'] if fmt == 'pdf' else key_by_format['html']
        resolved_fmt = fmt
        if not _object_exists(key):
            # Cloud pipeline only writes report.html; fall back so PDF requests
            # still return a usable report instead of 404.
            fallback_fmt = 'html' if fmt == 'pdf' else 'pdf'
            fallback_key = key_by_format[fallback_fmt]
            if _object_exists(fallback_key):
                key = fallback_key
                resolved_fmt = fallback_fmt
            else:
                return create_response(404, {
                    'error': 'Report not found in storage',
                    'hint': 'Link a completed local analysis run to this session first.',
                })

        download_url = _presign_s3_key(key, expires=86400)
        return create_response(200, {
            'session_id': session_id,
            'format': resolved_fmt,
            'requested_format': fmt,
            'report_key': key,
            'download_url': download_url,
        })
    except Exception as e:
        logger.error(f"Error getting report for {session_id}: {e}")
        return create_response(500, {'error': str(e)})


def handle_get_cme_session(session_id: str) -> Dict[str, Any]:
    """
    GET /cme/sessions/{session_id} - Get single CME session
    """
    try:
        sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
        response = sessions_table.get_item(Key={'session_id': session_id})
        
        if 'Item' not in response:
            return create_response(404, {'error': 'Session not found'})
        
        session = response['Item']
        
        # Convert Decimal to int for timestamps
        if 'created_at' in session:
            session['created_at'] = int(session['created_at'])
        if 'updated_at' in session:
            session['updated_at'] = int(session['updated_at'])
        if 'completed_at' in session:
            session['completed_at'] = int(session['completed_at'])

        if session.get('status') in ('completed', 'completed_with_warnings'):
            session = _attach_artifact_urls(session)
        else:
            session = _attach_playback_urls(session)

        session = _attach_doctor_report_url(session)

        session = maybe_advance_processing_pipeline(session_id, session)
        
        return create_response(200, {'session': session})
    
    except Exception as e:
        logger.error(f"Error getting session: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return create_response(500, {'error': str(e)})


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
        session_data['date_of_injury'] = body.get('date_of_injury') or ''
        session_data['date_of_birth'] = body.get('date_of_birth') or ''
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


_VIDEO_AUDIO_CONTENT_TYPES = {
    '.mp4': 'video/mp4',
    '.m4v': 'video/mp4',
    '.mov': 'video/quicktime',
    '.webm': 'video/webm',
    '.mp3': 'audio/mpeg',
    '.m4a': 'audio/mp4',
    '.wav': 'audio/wav',
    '.flac': 'audio/flac',
    '.ogg': 'audio/ogg',
    '.amr': 'audio/amr',
}

SUPPORTED_RECORDING_CONTENT_TYPES = {
    'video/mp4',
    'video/quicktime',
    'video/webm',
    'audio/mpeg',
    'audio/mp3',
    'audio/mp4',
    'audio/x-m4a',
    'audio/wav',
    'audio/wave',
    'audio/x-wav',
    'audio/flac',
    'audio/ogg',
    'audio/amr',
}

UNSUPPORTED_RECORDING_EXTENSIONS = ('.mpg', '.mpeg', '.avi', '.mkv', '.wmv', '.flv')


def _infer_content_type(filename: str, content_type: str) -> str:
    if content_type:
        return content_type
    lower = (filename or '').lower()
    if lower.endswith('.pdf'):
        return 'application/pdf'
    if lower.endswith('.docx'):
        return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    if lower.endswith('.doc'):
        return 'application/msword'
    # Browsers frequently report an empty MIME type; infer from extensions
    # that are supported by both the upload flow and AWS Transcribe.
    for ext, inferred in _VIDEO_AUDIO_CONTENT_TYPES.items():
        if lower.endswith(ext):
            return inferred
    return content_type or 'application/octet-stream'


def _unsupported_recording_reason(filename: str, content_type: str) -> Optional[str]:
    lower = (filename or '').lower()
    if lower.endswith(UNSUPPORTED_RECORDING_EXTENSIONS):
        return 'MPEG, AVI, MKV, WMV, and FLV require a conversion worker that is not enabled for production uploads yet.'
    if content_type not in SUPPORTED_RECORDING_CONTENT_TYPES:
        return f'Unsupported media type: {content_type}'
    return None


def _recording_slot_as_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _safe_storage_filename(filename: str, max_len: int = 80) -> str:
    """Sanitize filename for S3 keys; preserve extension when truncating."""
    cleaned = (filename or 'recording').replace(' ', '_').replace('/', '_')
    stem, ext = os.path.splitext(cleaned)
    if not ext:
        return cleaned[:max_len]
    max_stem = max_len - len(ext)
    if max_stem < 1:
        return ext[:max_len]
    return f"{stem[:max_stem]}{ext}"


def _get_transcription_job_status(job_name: str) -> Dict[str, Any]:
    """Return status and transcript URI for a medical or regular Transcribe job."""
    try:
        response = transcribe_client.get_medical_transcription_job(
            MedicalTranscriptionJobName=job_name
        )
        job = response['MedicalTranscriptionJob']
        return {
            'status': job['TranscriptionJobStatus'],
            'transcript_uri': job.get('Transcript', {}).get('TranscriptFileUri', ''),
        }
    except Exception as med_error:
        error_code = (
            med_error.response.get('Error', {}).get('Code', '')
            if hasattr(med_error, 'response') and med_error.response
            else ''
        )
        if error_code not in ('BadRequestException',) and 'not found' not in str(med_error).lower():
            raise
        response = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
        job = response['TranscriptionJob']
        return {
            'status': job['TranscriptionJobStatus'],
            'transcript_uri': job.get('Transcript', {}).get('TranscriptFileUri', ''),
        }


def maybe_advance_processing_pipeline(session_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
    """
    When Step Functions orchestration is unavailable, poll Transcribe on session GET
    and asynchronously invoke NLP once transcription completes.
    """
    stage = session.get('processing_stage') or ''
    if stage not in ('transcription', 'transcription_complete', 'video_analysis'):
        return session

    def _stage_age_sec() -> int:
        try:
            return int(time.time()) - int(session.get('updated_at') or 0)
        except (TypeError, ValueError):
            return 0

    fallback_mode = (session.get('orchestration_mode') or '') == 'fallback_polling'

    # Fallback orchestration: nothing drives the pipeline past NLP without
    # Step Functions, so kick report generation once video_analysis is reached.
    if stage == 'video_analysis':
        if not fallback_mode:
            return session
        try:
            lambda_client.invoke(
                FunctionName=REPORT_GENERATOR_FUNCTION,
                InvocationType='Event',
                Payload=json.dumps({'session_id': session_id, 'format': 'html'}),
            )
            sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
            now_ts = int(time.time())
            sessions_table.update_item(
                Key={'session_id': session_id},
                UpdateExpression='SET processing_stage = :stage, updated_at = :updated',
                ExpressionAttributeValues={':stage': 'report_generation', ':updated': now_ts},
            )
            session['processing_stage'] = 'report_generation'
            session['updated_at'] = now_ts
            logger.info(f"Fallback: invoked {REPORT_GENERATOR_FUNCTION} for session {session_id}")
        except Exception as invoke_err:
            logger.error(f"Failed to invoke report generator: {invoke_err}")
        return session

    transcript_uri = (session.get('transcript_uri') or '').strip()
    if transcript_uri and stage == 'transcription_complete':
        # NLP was already invoked when the stage flipped. If the session has
        # been stuck here past the retry window, the invoke was likely lost —
        # re-invoke instead of leaving the session stuck forever.
        if _stage_age_sec() >= STUCK_STAGE_RETRY_SEC:
            try:
                lambda_client.invoke(
                    FunctionName=NLP_PROCESSOR_FUNCTION,
                    InvocationType='Event',
                    Payload=json.dumps({
                        'session_id': session_id,
                        'transcript_uri': transcript_uri,
                    }),
                )
                sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
                now_ts = int(time.time())
                sessions_table.update_item(
                    Key={'session_id': session_id},
                    UpdateExpression='SET updated_at = :updated',
                    ExpressionAttributeValues={':updated': now_ts},
                )
                session['updated_at'] = now_ts
                logger.info(f"Re-invoked stuck NLP processor for session {session_id}")
            except Exception as invoke_err:
                logger.error(f"Failed to re-invoke NLP processor: {invoke_err}")
        return session

    jobs = session.get('transcription_jobs') or []
    job_names = [j.get('job_name') for j in jobs if isinstance(j, dict) and j.get('job_name')]
    if not job_names:
        return session

    transcript_uris: List[str] = []
    for job_name in job_names:
        info = _get_transcription_job_status(job_name)
        status = info['status']
        if status in ('IN_PROGRESS', 'QUEUED'):
            return session
        if status == 'FAILED':
            sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
            sessions_table.update_item(
                Key={'session_id': session_id},
                UpdateExpression='SET #status = :error, processing_stage = :stage, updated_at = :updated',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':error': 'error',
                    ':stage': 'transcription_failed',
                    ':updated': int(time.time()),
                },
            )
            session['status'] = 'error'
            session['processing_stage'] = 'transcription_failed'
            return session
        if status == 'COMPLETED' and info.get('transcript_uri'):
            transcript_uris.append(info['transcript_uri'])

    if len(transcript_uris) != len(job_names):
        return session

    primary_uri = _normalize_s3_uri(transcript_uris[0])
    now_ts = int(time.time())
    completed_jobs = [
        {**j, 'status': 'COMPLETED'} if isinstance(j, dict) else j
        for j in jobs
    ]
    sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
    sessions_table.update_item(
        Key={'session_id': session_id},
        UpdateExpression=(
            'SET transcript_uri = :uri, processing_stage = :stage, '
            '#status = :status, updated_at = :updated, transcription_jobs = :jobs'
        ),
        ExpressionAttributeNames={'#status': 'status'},
        ExpressionAttributeValues={
            ':uri': primary_uri,
            ':stage': 'transcription_complete',
            ':status': 'processing',
            ':updated': now_ts,
            ':jobs': completed_jobs,
        },
    )
    session['transcript_uri'] = primary_uri
    session['transcription_jobs'] = completed_jobs
    session['processing_stage'] = 'transcription_complete'
    session['updated_at'] = now_ts

    try:
        lambda_client.invoke(
            FunctionName=NLP_PROCESSOR_FUNCTION,
            InvocationType='Event',
            Payload=json.dumps({
                'session_id': session_id,
                'transcript_uri': primary_uri,
            }),
        )
        logger.info(f"Invoked {NLP_PROCESSOR_FUNCTION} for session {session_id}")
    except Exception as invoke_err:
        logger.error(f"Failed to invoke NLP processor: {invoke_err}")

    return session


def handle_upload_cme_recording(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 2: Data Ingestion & Storage
    Presigned PUT for exam video/audio, or doctor-written report (PDF/DOC/DOCX).
    """
    try:
        session_id = body.get('session_id')
        upload_kind = (body.get('upload_kind') or body.get('upload_type') or 'recording').lower()
        filename = body.get('filename', 'recording.mp4')
        content_type = _infer_content_type(filename, (body.get('content_type') or '').strip()).lower()
        file_size = body.get('file_size', 0)
        recording_slot_raw = body.get('recording_slot')

        if not session_id:
            return create_response(400, {'error': 'session_id is required'})

        sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
        session_response = sessions_table.get_item(Key={'session_id': session_id})
        session = session_response.get('Item')

        if not session:
            return create_response(404, {'error': 'CME session not found'})

        current_status = str(session.get('status') or '').lower()
        if current_status == 'processing':
            return create_response(409, {
                'error': 'Processing is already running for this session. Refresh the case page for live status.',
            })
        if current_status in ('completed', 'completed_with_warnings'):
            return create_response(409, {
                'error': 'This session already has a completed report. Create a new case to run another analysis.',
            })
        if current_status == 'cancelled':
            return create_response(409, {
                'error': 'This session was cancelled and cannot be restarted. Create a new case to continue.',
            })

        unique_id = str(uuid.uuid4())[:8]
        safe_filename = _safe_storage_filename(filename)
        now_ts = int(time.time())

        if upload_kind in ('doctor_report', 'report', 'examiner_report'):
            allowed_report_types = (
                'application/pdf',
                'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            )
            if content_type not in allowed_report_types:
                return create_response(400, {
                    'error': 'Doctor report must be PDF or Word (.pdf, .doc, .docx)',
                    'content_type': content_type,
                })
            s3_key = f"cme-doctor-reports/{session_id}/{unique_id}_{safe_filename}"
            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': S3_BUCKET,
                    'Key': s3_key,
                    'ContentType': content_type,
                },
                ExpiresIn=7200,
            )
            report_meta = {
                'uri': f"s3://{S3_BUCKET}/{s3_key}",
                's3_key': s3_key,
                'filename': filename,
                'content_type': content_type,
                'file_size': file_size,
                'uploaded_at': now_ts,
            }
            sessions_table.update_item(
                Key={'session_id': session_id},
                UpdateExpression='SET doctor_report = :dr, updated_at = :updated',
                ExpressionAttributeValues={
                    ':dr': report_meta,
                    ':updated': now_ts,
                },
            )
            logger.info(f"Doctor report presign for session {session_id}")
            return create_response(200, {
                'session_id': session_id,
                'upload_url': presigned_url,
                's3_key': s3_key,
                'filename': filename,
                'upload_kind': 'doctor_report',
                'expires_in': 7200,
                'message': 'Upload the doctor report to this URL.',
            })

        is_video = content_type.startswith('video/')
        is_audio = content_type.startswith('audio/')

        recording_rules = session.get('recording_allowed', {})

        unsupported_reason = _unsupported_recording_reason(filename, content_type)
        if unsupported_reason:
            return create_response(415, {
                'error': (
                    f'{unsupported_reason} Please convert the recording to MP4, MOV, M4V, WEBM, '
                    'or upload supported audio (MP3, M4A, WAV, FLAC, OGG, AMR).'
                ),
                'content_type': content_type,
            })

        if is_video and not recording_rules.get('video'):
            return create_response(403, {
                'error': f"Video recording not permitted in {session.get('state')}",
                'allowed': recording_rules,
            })

        if not is_video and not is_audio:
            return create_response(400, {'error': 'File must be video or audio format'})

        s3_key = f"cme-recordings/{session_id}/{unique_id}_{safe_filename}"

        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': S3_BUCKET,
                'Key': s3_key,
                'ContentType': content_type,
            },
            ExpiresIn=7200,
        )

        session_recordings = session.get('recordings', [])
        if not isinstance(session_recordings, list):
            if session.get('video_uri'):
                session_recordings = [{
                    'uri': session.get('video_uri'),
                    'filename': 'recording.mp4',
                    'uploaded_at': session.get('updated_at', int(time.time())),
                }]
            else:
                session_recordings = []

        used_slots = {
            s for s in (_recording_slot_as_int(r.get('recording_slot')) for r in session_recordings)
            if s is not None
        }

        if recording_slot_raw is not None and recording_slot_raw != '':
            try:
                recording_slot = int(recording_slot_raw)
            except (TypeError, ValueError):
                return create_response(400, {'error': 'recording_slot must be 1'})
            if recording_slot != 1:
                return create_response(400, {
                    'error': 'Only one recording is supported per live case right now. Use recording_slot=1.',
                })
            if recording_slot in used_slots:
                # Idempotent replace: slots are registered at presign time, so a
                # failed/retried browser upload re-requests the same slot. Drop
                # the stale entry and hand out a fresh URL instead of rejecting.
                session_recordings = [
                    r for r in session_recordings
                    if _recording_slot_as_int(r.get('recording_slot')) != recording_slot
                ]
                logger.info(
                    f"Replacing recording slot {recording_slot} for session {session_id}"
                )
            elif session_recordings:
                return create_response(409, {
                    'error': 'Only one recording is supported per live case right now. Replace Video 1 or create a new case.',
                })
        else:
            if session_recordings:
                return create_response(409, {
                    'error': 'Only one recording is supported per live case right now. Replace Video 1 or create a new case.',
                })
            recording_slot = 1

        new_recording = {
            'uri': f"s3://{S3_BUCKET}/{s3_key}",
            's3_key': s3_key,
            'filename': filename,
            'content_type': content_type,
            'file_size': file_size,
            'uploaded_at': now_ts,
            'recording_slot': recording_slot,
            'display_label': f'Video {recording_slot}',
        }
        session_recordings.append(new_recording)

        update_expr = (
            'SET recordings = :recordings, video_uri = :uri, #status = :status, '
            'updated_at = :updated, processing_stage = :stage'
        )
        sessions_table.update_item(
            Key={'session_id': session_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':recordings': session_recordings,
                ':uri': new_recording['uri'],
                ':status': 'recording_uploaded',
                ':updated': now_ts,
                ':stage': 'ingestion',
            },
        )

        logger.info(f"Recording presign session={session_id} slot={recording_slot}")

        return create_response(200, {
            'session_id': session_id,
            'upload_url': presigned_url,
            's3_key': s3_key,
            'filename': filename,
            'upload_kind': 'recording',
            'recording_slot': recording_slot,
            'display_label': new_recording['display_label'],
            'recording_index': len(session_recordings) - 1,
            'total_recordings': len(session_recordings),
            'expires_in': 7200,
            'message': 'Upload the case recording to this URL.',
        })

    except Exception as e:
        logger.error(f"Error creating CME recording upload URL: {str(e)}")
        return create_response(500, {'error': f'Error creating upload URL: {str(e)}'})


def handle_start_cme_processing(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trigger CME processing pipeline after recording upload
    This initiates Steps 3-8: Transcription, NLP, CV, Demeanor Analysis, Report
    **NOW WITH STEP FUNCTION ORCHESTRATION**
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

        current_status = str(session.get('status') or '').lower()
        if current_status == 'processing':
            return create_response(409, {
                'error': 'Processing is already running for this session. Refresh the case page for live status.',
            })
        if current_status in ('completed', 'completed_with_warnings'):
            return create_response(409, {
                'error': 'This session already has a completed report. Create a new case to run another analysis.',
            })
        if current_status == 'cancelled':
            return create_response(409, {
                'error': 'This session was cancelled and cannot be restarted. Create a new case to continue.',
            })

        # Get recordings list (support old single video_uri storage)
        recordings = session.get('recordings', [])
        if not recordings and session.get('video_uri'):
            # Migrate old format to new format
            recordings = [{
                'uri': session.get('video_uri'),
                's3_key': session.get('video_uri').replace('s3://', '').split('/', 1)[1] if session.get('video_uri').startswith('s3://') else session.get('video_uri'),
                'filename': 'recording.mp4',
                'uploaded_at': session.get('updated_at', int(time.time()))
            }]
        
        if not recordings:
            return create_response(400, {'error': 'No recordings uploaded for this session'})
        if len(recordings) > 1:
            return create_response(409, {
                'error': 'Only one recording is supported per live case right now. Combine segments into one file before processing.',
            })

        def _sort_recordings(recs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            def key_fn(ir: tuple) -> tuple:
                i, r = ir
                s = _recording_slot_as_int(r.get('recording_slot'))
                if s is None:
                    s = 10_000_000 + i
                try:
                    ts = int(r.get('uploaded_at', 0) or 0)
                except (TypeError, ValueError):
                    ts = 0
                return (s, ts)

            return [r for _, r in sorted(enumerate(recs), key=key_fn)]

        recordings = _sort_recordings(recordings)

        missing_uploads = []
        for recording in recordings:
            video_uri = recording.get('uri') or recording.get('s3_key') or ''
            parsed = _s3_bucket_key_from_uri(video_uri)
            if not parsed:
                missing_uploads.append({
                    'filename': recording.get('filename') or 'recording',
                    'reason': 'missing_s3_key',
                })
                continue
            bucket, key = parsed
            try:
                s3_client.head_object(Bucket=bucket, Key=key)
            except Exception as head_err:
                error_code = (
                    head_err.response.get('Error', {}).get('Code', '')
                    if hasattr(head_err, 'response') and head_err.response
                    else ''
                )
                if error_code in ('404', 'NoSuchKey', 'NotFound'):
                    missing_uploads.append({
                        'filename': recording.get('filename') or key,
                        's3_key': key,
                        'reason': 'upload_not_found',
                    })
                    continue
                raise

        if missing_uploads:
            return create_response(409, {
                'error': 'One or more recording uploads have not finished. Please retry the upload before starting processing.',
                'missing_recordings': missing_uploads,
            })

        # Update session status
        processing_started_at = int(time.time())
        sessions_table.update_item(
            Key={'session_id': session_id},
            UpdateExpression=(
                'SET #status = :status, processing_stage = :stage, '
                'processing_started_at = :started, updated_at = :updated '
                'REMOVE last_error, analysis_warning, transcript_uri, transcription_jobs'
            ),
            ExpressionAttributeNames={
                '#status': 'status'  # 'status' is a reserved keyword in DynamoDB
            },
            ExpressionAttributeValues={
                ':status': 'processing',
                ':stage': 'transcription',
                ':started': processing_started_at,
                ':updated': processing_started_at,
            }
        )
        
        # Process the single production recording.
        transcription_jobs = []
        video_s3_keys = []
        
        for idx, recording in enumerate(recordings):
            # Create a temporary session dict for transcription
            temp_session = session.copy()
            temp_session['video_uri'] = recording.get('uri', recording.get('s3_key', ''))
            transcription_job = start_transcription_job(temp_session, recording_index=idx)
            transcription_jobs.append(transcription_job)
            
            # Extract S3 key
            video_uri = recording.get('uri', recording.get('s3_key', ''))
            if video_uri.startswith('s3://'):
                s3_key = video_uri.replace('s3://', '').split('/', 1)[1]
            else:
                s3_key = video_uri
            video_s3_keys.append(s3_key)

        failed_transcriptions = [j for j in transcription_jobs if not j.get('job_name')]
        if failed_transcriptions:
            first_error = failed_transcriptions[0].get('error') or failed_transcriptions[0].get('message') or 'unknown error'
            raise RuntimeError(
                f"Could not start transcription for {len(failed_transcriptions)} recording(s): {first_error}"
            )
        
        # *** START STEP FUNCTION WORKFLOW ***
        # The Step Functions workflow is intentionally single-recording until
        # timestamp alignment for combined transcripts is implemented.
        
        valid_jobs = [j for j in transcription_jobs if j.get('job_name')]
        sessions_table.update_item(
            Key={'session_id': session_id},
            UpdateExpression='SET transcription_jobs = :jobs, updated_at = :updated',
            ExpressionAttributeValues={
                ':jobs': valid_jobs,
                ':updated': int(time.time()),
            },
        )

        step_functions_arn = STEP_FUNCTION_ARN
        first_job_name = valid_jobs[0]['job_name'] if valid_jobs else None
        orchestration_mode = 'fallback_polling'
        if step_functions_arn and first_job_name:
            execution_input = {
                'session_id': session_id,
                'transcription_job_name': first_job_name,
                'video_s3_key': video_s3_keys[0] if video_s3_keys else '',
            }
            try:
                execution_response = stepfunctions_client.start_execution(
                    stateMachineArn=step_functions_arn,
                    name=f"cme-{session_id}-{int(time.time())}",
                    input=json.dumps(execution_input),
                )
                logger.info(f"Started Step Function: {execution_response['executionArn']}")
                orchestration_mode = 'step_functions'
            except Exception as sf_error:
                # Not fatal: the GET-poll fallback advances the pipeline, but
                # record the mode so the fallback knows to drive every stage.
                logger.error(f"Failed to start Step Function: {sf_error}")
        elif not step_functions_arn:
            logger.warning(
                'STEP_FUNCTION_ARN not set; pipeline will advance via session GET polling'
            )
        sessions_table.update_item(
            Key={'session_id': session_id},
            UpdateExpression='SET orchestration_mode = :mode, updated_at = :updated',
            ExpressionAttributeValues={
                ':mode': orchestration_mode,
                ':updated': int(time.time()),
            },
        )
        
        logger.info(f"Started CME processing for session: {session_id}")
        
        return create_response(200, {
            'session_id': session_id,
            'status': 'processing',
            'stage': 'transcription',
            'transcription_job': transcription_job,
            'message': 'CME analysis processing started - full pipeline will run automatically',
            'estimated_time': 'Processing time depends on recording length (typically 5-15 minutes)'
        })
        
    except Exception as e:
        logger.error(f"Error starting CME processing: {str(e)}")
        # Roll the session out of 'processing' so the UI shows a real error
        # instead of a pipeline stuck at the transcription stage forever.
        try:
            session_id = body.get('session_id')
            if session_id:
                dynamodb.Table(CME_SESSIONS_TABLE).update_item(
                    Key={'session_id': session_id},
                    UpdateExpression=(
                        'SET #status = :status, processing_stage = :stage, '
                        'last_error = :err, updated_at = :updated'
                    ),
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={
                        ':status': 'error',
                        ':stage': 'processing_start_failed',
                        ':err': str(e)[:500],
                        ':updated': int(time.time()),
                    },
                )
        except Exception as mark_err:
            logger.error(f"Failed to mark session error: {mark_err}")
        return create_response(500, {'error': f'Error starting processing: {str(e)}'})


def convert_mpeg_to_mp4_mediaconvert(s3_bucket: str, input_key: str, output_key: str) -> Dict[str, Any]:
    """
    Convert MPEG/MPG file to MP4 format using AWS MediaConvert
    Returns job info or error
    """
    try:
        # Get MediaConvert endpoint
        try:
            mediaconvert_temp = boto3.client('mediaconvert', region_name=AWS_REGION)
            endpoints = mediaconvert_temp.describe_endpoints()
            mediaconvert_endpoint = endpoints['Endpoints'][0]['Url']
            mediaconvert = boto3.client('mediaconvert', endpoint_url=mediaconvert_endpoint, region_name=AWS_REGION)
        except Exception as e:
            logger.error(f"Error getting MediaConvert endpoint: {str(e)}")
            return {'error': str(e), 'success': False}
        
        input_uri = f"s3://{s3_bucket}/{input_key}"
        output_dir = f"s3://{s3_bucket}/{os.path.dirname(output_key)}/"
        
        # Get IAM role ARN - MediaConvert needs a service role with S3 access
        # Use STS to get account ID
        sts = boto3.client('sts')
        account_id = sts.get_caller_identity()['Account']
        # Use MediaConvert service role (not Lambda execution role)
        role_arn = f'arn:aws:iam::{account_id}:role/MediaConvertServiceRole'
        
        # Create MediaConvert job - simplified for audio extraction
        job_settings = {
            'Role': role_arn,
            'Settings': {
                'Inputs': [{
                    'FileInput': input_uri,
                    'AudioSelectors': {
                        'Audio Selector 1': {
                            'DefaultSelection': 'DEFAULT'
                        }
                    },
                    'VideoSelector': {}
                }],
                'OutputGroups': [{
                    'Name': 'File Group',
                    'OutputGroupSettings': {
                        'Type': 'FILE_GROUP_SETTINGS',
                        'FileGroupSettings': {
                            'Destination': f"s3://{s3_bucket}/{os.path.dirname(output_key)}/"
                        }
                    },
                    'Outputs': [{
                        'NameModifier': os.path.basename(output_key).replace('.mp4', ''),
                        'ContainerSettings': {
                            'Container': 'MP4',
                            'Mp4Settings': {}
                        },
                        'VideoDescription': {
                            'CodecSettings': {
                                'Codec': 'H_264',
                                'H264Settings': {
                                    'RateControlMode': 'QVBR',
                                    'QualityTuningLevel': 'SINGLE_PASS',
                                    'MaxBitrate': 5000000,  # 5 Mbps
                                    'QvbrSettings': {
                                        'QvbrQualityLevel': 8
                                    }
                                }
                            }
                        },
                        'AudioDescriptions': [{
                            'CodecSettings': {
                                'Codec': 'AAC',
                                'AacSettings': {
                                    'Bitrate': 96000,
                                    'CodingMode': 'CODING_MODE_2_0',
                                    'SampleRate': 48000
                                }
                            }
                        }]
                    }]
                }]
            }
        }
        
        response = mediaconvert.create_job(**job_settings)
        job_id = response['Job']['Id']
        
        logger.info(f"Started MediaConvert job {job_id} to convert {input_key} to {output_key}")
        
        return {
            'success': True,
            'job_id': job_id,
            'status': 'SUBMITTED',
            'output_key': output_key
        }
        
    except Exception as e:
        logger.error(f"Error creating MediaConvert job: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {'error': str(e), 'success': False}


def start_transcription_job(session: Dict[str, Any], recording_index: int = 0) -> Dict[str, Any]:
    """
    Step 3: Speech-to-Text & Speaker Diarization
    Start AWS Transcribe Medical job with speaker identification
    Handles MPEG/MPG files by converting to MP3 first (Transcribe doesn't support MPEG)
    The production workflow currently supports one recording per session.
    """
    try:
        session_id = session['session_id']
        video_uri = session.get('video_uri', '')
        
        if not video_uri:
            return {'error': 'No video_uri provided'}
        
        # Extract S3 bucket and key from URI
        if video_uri.startswith('s3://'):
            s3_path = video_uri.replace('s3://', '')
            bucket, key = s3_path.split('/', 1)
        else:
            bucket = S3_BUCKET
            key = video_uri
        
        job_name = f"cme-transcribe-{session_id}-{recording_index}-{int(time.time())}"
        
        # Detect media format from file extension
        file_extension = key.split('.')[-1].lower() if '.' in key else 'mp4'

        if file_extension in {'mpeg', 'mpg', 'avi', 'mkv', 'wmv', 'flv'}:
            return {
                'error': (
                    f'Unsupported media extension for production transcription: .{file_extension}. '
                    'Convert the recording to MP4, MOV, M4V, WEBM, or supported audio before upload.'
                ),
                'job_name': None,
                'status': 'FAILED',
            }
        
        # Check if there's already a conversion job in progress or complete
        conversion_job_id = session.get('conversion_job_id')
        if conversion_job_id:
            logger.info(f"Found existing conversion job: {conversion_job_id}")
            # Check if conversion is complete by looking for converted file
            converted_key_pattern = f"cme-converted/{session_id}/"
            try:
                # List files in converted directory
                s3_response = s3_client.list_objects_v2(Bucket=bucket, Prefix=converted_key_pattern)
                if 'Contents' in s3_response and s3_response['Contents']:
                    # Found converted file(s) - use the first .mp4 file
                    for obj in s3_response['Contents']:
                        if obj['Key'].endswith('.mp4'):
                            converted_uri = f"s3://{bucket}/{obj['Key']}"
                            logger.info(f"Found existing converted file: {converted_uri}")
                            # Update session to use converted file
                            sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
                            sessions_table.update_item(
                                Key={'session_id': session_id},
                                UpdateExpression='SET video_uri = :uri, converted_video_uri = :uri, processing_stage = :stage, updated_at = :updated',
                                ExpressionAttributeValues={
                                    ':uri': converted_uri,
                                    ':stage': 'conversion_complete',
                                    ':updated': int(time.time())
                                }
                            )
                            # Update key to use converted file for transcription
                            key = obj['Key']
                            file_extension = 'mp4'
                            logger.info(f"Using converted file for transcription: {key}")
                            break
            except Exception as e:
                logger.warning(f"Error checking for converted file: {str(e)}, proceeding with new conversion")
        
        # For MPEG/MPG files, convert to MP4 first using MediaConvert
        if file_extension in ['mpeg', 'mpg']:
            logger.info(f"MPEG file detected. Starting automatic conversion to MP4...")
            converted_key = f"cme-converted/{session_id}/video.mp4"
            conversion_result = convert_mpeg_to_mp4_mediaconvert(bucket, key, converted_key)
            
            if not conversion_result.get('success'):
                logger.error(f"MediaConvert conversion failed: {conversion_result.get('error')}")
                return {
                    'error': f"Failed to convert MPEG file: {conversion_result.get('error', 'Unknown error')}",
                    'job_name': None,
                    'status': 'FAILED',
                    'conversion_job_id': conversion_result.get('job_id')
                }
            
            # Update session with conversion job ID
            sessions_table = dynamodb.Table(CME_SESSIONS_TABLE)
            sessions_table.update_item(
                Key={'session_id': session_id},
                UpdateExpression='SET conversion_job_id = :job_id, processing_stage = :stage, updated_at = :updated',
                ExpressionAttributeValues={
                    ':job_id': conversion_result['job_id'],
                    ':stage': 'converting',
                    ':updated': int(time.time())
                }
            )
            
            # Return info that conversion is in progress
            return {
                'job_name': None,
                'status': 'CONVERTING',
                'conversion_job_id': conversion_result['job_id'],
                'message': 'MPEG file is being converted to MP4. Transcription will start automatically after conversion completes.',
                'estimated_time': 'Conversion typically takes 5-15 minutes depending on file size'
            }
        else:
            # Format mapping for Transcribe
            format_mapping = {
                'mp4': 'mp4',
                'mp3': 'mp3',
                'wav': 'wav',
                'flac': 'flac',
                'ogg': 'ogg',
                'amr': 'amr',
                'webm': 'webm',
                'm4a': 'mp4',
                'mov': 'mp4'
            }
            media_format = format_mapping.get(file_extension)
            if not media_format:
                return {
                    'error': f'Unsupported media extension for transcription: .{file_extension}',
                    'job_name': None,
                    'status': 'FAILED',
                }
        
        # Use Medical Transcribe for better medical vocabulary (now that MPEG is converted)
        use_medical = True
        
        if use_medical:
            # Use Medical Transcribe for better medical vocabulary
            response = transcribe_client.start_medical_transcription_job(
                MedicalTranscriptionJobName=job_name,
                LanguageCode='en-US',
                MediaFormat=media_format,
                Media={
                    'MediaFileUri': f"s3://{bucket}/{key}"
                },
                OutputBucketName=bucket,
                OutputKey=f"cme-transcripts/{session_id}/transcript_{recording_index}.json",
                Settings={
                    'ShowSpeakerLabels': True,
                    'MaxSpeakerLabels': 5,  # Examiner, patient, and possibly observers
                    'ChannelIdentification': False
                },
                Specialty='PRIMARYCARE',
                Type='CONVERSATION'
            )
        else:
            # Use regular Transcribe for MPEG/MPG files (supports more formats)
            logger.info(f"Using regular Transcribe for {file_extension} format (MPEG/MPG not supported by Medical Transcribe)")
            response = transcribe_client.start_transcription_job(
                TranscriptionJobName=job_name,
                LanguageCode='en-US',
                MediaFormat=media_format,
                Media={
                    'MediaFileUri': f"s3://{bucket}/{key}"
                },
                OutputBucketName=bucket,
                OutputKey=f"cme-transcripts/{session_id}/transcript_{recording_index}.json",
                Settings={
                    'ShowSpeakerLabels': True,
                    'MaxSpeakerLabels': 5,
                    'ChannelIdentification': False
                }
            )
        
        logger.info(f"Started transcription job: {job_name} (Medical: {use_medical})")
        
        return {
            'job_name': job_name,
            'status': 'IN_PROGRESS',
            'output_uri': f"s3://{bucket}/cme-transcripts/{session_id}/transcript.json",
            'is_medical': use_medical
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


def _log_request_summary(event: Dict[str, Any]) -> None:
    """Log routing metadata without Authorization headers or request bodies."""
    headers = event.get('headers') or {}
    origin = headers.get('origin') or headers.get('Origin') or ''
    request_context = event.get('requestContext') or {}
    logger.info(json.dumps({
        'message': 'CME API request',
        'request_id': request_context.get('requestId'),
        'http_method': event.get('httpMethod', 'POST'),
        'path': event.get('path', '/'),
        'origin': origin,
        'has_body': bool(event.get('body')),
    }))


def handler(event, context):
    """Main Lambda handler for CME operations"""
    try:
        _log_request_summary(event)
        
        # Parse request
        http_method = event.get('httpMethod', 'POST')
        path = event.get('path', '/')
        body = json.loads(event.get('body', '{}')) if event.get('body') else {}
        
        # Handle OPTIONS for CORS
        if http_method == 'OPTIONS':
            return create_response(200, {})
        
        # Route to appropriate handler
        # Handle path parameters from API Gateway
        path_parts = path.rstrip('/').split('/')
        
        # GET /cme/sessions - List all sessions
        if (path == '/cme/sessions' or path.endswith('/cme/sessions')) and http_method == 'GET':
            return handle_list_cme_sessions()
        # POST /cme/sessions - Create new session
        elif (path == '/cme/sessions' or path.endswith('/cme/sessions')) and http_method == 'POST':
            return handle_create_cme_session(body)
        # GET /cme/sessions/{session_id} or .../report
        elif '/cme/sessions/' in path and http_method == 'GET':
            tail = path.split('/cme/sessions/')[-1].strip('/')
            parts = [p for p in tail.split('/') if p]
            session_id = parts[0] if parts else ''
            if not session_id or session_id == 'sessions':
                return create_response(400, {'error': 'Invalid session ID'})
            if len(parts) > 1 and parts[1] == 'report':
                query = event.get('queryStringParameters') or {}
                return handle_get_cme_report(session_id, query)
            return handle_get_cme_session(session_id)
        elif path.endswith('/cme/consent') and http_method == 'POST':
            return handle_submit_consent(body)
        elif path.endswith('/cme/upload') and http_method == 'POST':
            return handle_upload_cme_recording(body)
        elif path.endswith('/cme/process') and http_method == 'POST':
            return handle_start_cme_processing(body)
        else:
            logger.warning(f"Endpoint not found: {http_method} {path}")
            return create_response(404, {'error': f'Endpoint not found: {http_method} {path}'})
    
    except Exception as e:
        logger.error(f"Error in CME handler: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return create_response(500, {'error': str(e)})
