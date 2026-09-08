"""
CME Report Generator - Create structured reports from CME analysis
Implements Step 8 from the technical documentation
"""

import json
import boto3
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from decimal import Decimal
import base64
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Administrative / transcription noise that must never surface as a report
# finding (kept local: this Lambda is deployed standalone, without the
# cme_egregious_ranking package). Mirrors cme_egregious_ranking._BANNED_NOISE_RE.
_REPORT_NOISE_RE = re.compile(
    r"\b(?:"
    r"name\s+(?:was\s+)?(?:recorded|spelled|misspelled|mispronounced|stated)"
    r"|misspell\w*|spelling|mispronunc\w*|pronunciation"
    r"|transcription\s+(?:error|artifact|issue|quality)"
    r"|transcript\s+(?:error|artifact)"
    r"|audio\s+quality|recording\s+quality|inaudible"
    r"|recorded\s+improperly"
    r"|paperwork|scheduling|check[- ]?in|consent\s+form"
    r"|small\s+talk|greeting"
    r")\b",
    re.I,
)

_UNANALYZED_MOTION_STATUSES = {'analysis_unavailable', 'unknown', None}


def _is_noise_flag(flag: Dict[str, Any]) -> bool:
    """True when a demeanor flag is administrative/transcription noise."""
    text = " ".join(
        str(flag.get(k) or "")
        for k in ("flag_type", "description", "transcript_excerpt")
    )
    return bool(_REPORT_NOISE_RE.search(text))


def _analysis_completion_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize whether declared tests received a real video verdict."""
    declared_steps = data.get('declared_steps') or []
    step_actions = data.get('step_actions') or {}
    tests_unanalyzed = sum(
        1 for step in declared_steps
        if step_actions.get(step.get('declared_step_id'), {}).get('motion_present')
        in _UNANALYZED_MOTION_STATUSES
    )
    return {
        'analysis_status': 'incomplete' if tests_unanalyzed else 'complete',
        'tests_unanalyzed': tests_unanalyzed,
        'total_declared_tests': len(declared_steps),
    }

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# HTML Template for CME Report
HTML_REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CME Analysis Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 2.5em;
        }}
        .metadata {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metadata-item {{
            padding: 10px;
        }}
        .metadata-item strong {{
            display: block;
            color: #667eea;
            margin-bottom: 5px;
        }}
        .section {{
            background: white;
            padding: 25px;
            margin-bottom: 25px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .section h2 {{
            color: #667eea;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
            margin-top: 0;
        }}
        .timeline {{
            position: relative;
            padding-left: 40px;
        }}
        .timeline-item {{
            position: relative;
            padding: 20px;
            margin-bottom: 20px;
            background: #f9f9f9;
            border-left: 4px solid #667eea;
            border-radius: 4px;
        }}
        .timeline-item:hover {{
            background: #f0f0ff;
        }}
        .timeline-time {{
            font-weight: bold;
            color: #667eea;
            font-size: 1.1em;
            margin-bottom: 5px;
        }}
        .timeline-label {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.9em;
            margin-bottom: 10px;
        }}
        .discrepancy {{
            background: #fff3cd;
            border-left-color: #ffc107;
            border-left-width: 6px;
        }}
        .discrepancy .timeline-label {{
            background: #ffc107;
            color: #000;
        }}
        .flag {{
            padding: 15px;
            margin: 10px 0;
            border-radius: 6px;
            border-left: 5px solid;
        }}
        .flag-high {{
            background: #ffe5e5;
            border-left-color: #dc3545;
        }}
        .flag-medium {{
            background: #fff3cd;
            border-left-color: #ffc107;
        }}
        .flag-low {{
            background: #d1ecf1;
            border-left-color: #17a2b8;
        }}
        .flag-type {{
            font-weight: bold;
            text-transform: uppercase;
            font-size: 0.9em;
            margin-bottom: 5px;
        }}
        .transcript-excerpt {{
            background: #f8f9fa;
            padding: 10px;
            border-left: 3px solid #6c757d;
            margin-top: 10px;
            font-style: italic;
            color: #495057;
        }}
        .video-link {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 8px 16px;
            border-radius: 5px;
            text-decoration: none;
            margin-top: 10px;
        }}
        .video-link:hover {{
            background: #5568d3;
        }}
        .summary-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .stat-box {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-number {{
            font-size: 2.5em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .stat-label {{
            font-size: 0.9em;
            opacity: 0.9;
        }}
        .confidence-bar {{
            width: 100%;
            height: 20px;
            background: #e9ecef;
            border-radius: 10px;
            overflow: hidden;
            margin-top: 10px;
        }}
        .confidence-fill {{
            height: 100%;
            background: linear-gradient(90deg, #28a745, #20c997);
            transition: width 0.3s ease;
        }}
        .motion-performed {{
            color: #28a745;
            font-weight: bold;
        }}
        .motion-brief {{
            color: #ffc107;
            font-weight: bold;
        }}
        .motion-not_observed {{
            color: #dc3545;
            font-weight: bold;
        }}
        .motion-pending {{
            color: #6c757d;
            font-style: italic;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            border-radius: 8px;
            margin-top: 30px;
            color: #6c757d;
        }}
        @media print {{
            body {{
                background: white;
            }}
            .section {{
                box-shadow: none;
                border: 1px solid #ddd;
            }}
        }}
    </style>
</head>
<body>
    {content}
</body>
</html>"""


class CMEReportGenerator:
    """Generate comprehensive CME analysis reports"""
    
    def __init__(self, s3_bucket: str):
        self.s3_bucket = s3_bucket
    
    def generate_report(
        self,
        session_id: str,
        include_video_links: bool = True,
        format: str = 'html'
    ) -> Dict[str, Any]:
        """
        Generate comprehensive CME analysis report
        
        Args:
            session_id: CME session ID
            include_video_links: Whether to include video snippet links
            format: Report format ('html', 'pdf', or 'json')
            
        Returns:
            Report data and S3 location
        """
        try:
            # Gather all data for the session
            report_data = self._gather_session_data(session_id)
            
            if not report_data:
                return {'error': 'Session not found or incomplete'}
            
            analysis_summary = _analysis_completion_summary(report_data)

            # Generate report based on format
            if format == 'html':
                report_content = self._generate_html_report(report_data, include_video_links)
                content_type = 'text/html'
                file_extension = 'html'
            elif format == 'pdf':
                # Generate HTML first, then convert to PDF
                html_content = self._generate_html_report(report_data, include_video_links)
                try:
                    from weasyprint import HTML
                    pdf_content = HTML(string=html_content).write_pdf()
                    report_content = pdf_content
                    content_type = 'application/pdf'
                    file_extension = 'pdf'
                except ImportError:
                    logger.warning("WeasyPrint not available, falling back to HTML")
                    report_content = html_content
                    content_type = 'text/html'
                    file_extension = 'html'
            elif format == 'json':
                report_content = json.dumps(report_data, indent=2, default=str)
                content_type = 'application/json'
                file_extension = 'json'
            else:
                return {'error': f'Unsupported format: {format}'}
            
            # Save report to S3
            report_key = f"cme-reports/{session_id}/report.{file_extension}"
            s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=report_key,
                Body=report_content.encode('utf-8') if isinstance(report_content, str) else report_content,
                ContentType=content_type
            )
            
            # Generate presigned URL for download
            download_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.s3_bucket, 'Key': report_key},
                ExpiresIn=86400  # 24 hours
            )
            
            logger.info(f"Generated CME report: {report_key}")
            
            return {
                'session_id': session_id,
                'report_key': report_key,
                'download_url': download_url,
                'format': format,
                'generated_at': datetime.now().isoformat(),
                **analysis_summary,
            }
            
        except Exception as e:
            logger.error(f"Error generating report: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {'error': str(e)}
    
    def _gather_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Gather all data related to a CME session"""
        try:
            # Get session info
            sessions_table = dynamodb.Table(os.environ.get('CME_SESSIONS_TABLE', 'cme-sessions'))
            session_response = sessions_table.get_item(Key={'session_id': session_id})
            session = session_response.get('Item')
            
            if not session:
                return None
            
            # Get declared steps
            steps_table = dynamodb.Table(os.environ.get('CME_STEPS_TABLE', 'cme-declared-steps'))
            steps_response = steps_table.scan(
                FilterExpression='session_id = :sid',
                ExpressionAttributeValues={':sid': session_id}
            )
            declared_steps = steps_response.get('Items', [])
            
            # Get observed actions
            actions_table = dynamodb.Table(os.environ.get('CME_ACTIONS_TABLE', 'cme-observed-actions'))
            actions_response = actions_table.scan()
            all_actions = actions_response.get('Items', [])
            
            # Map actions to steps
            step_actions = {}
            for action in all_actions:
                step_id = action.get('declared_step_id')
                if step_id:
                    step_actions[step_id] = action
            
            # Get demeanor flags
            demeanor_table = dynamodb.Table(os.environ.get('CME_DEMEANOR_TABLE', 'cme-demeanor-flags'))
            demeanor_response = demeanor_table.scan(
                FilterExpression='session_id = :sid',
                ExpressionAttributeValues={':sid': session_id}
            )
            demeanor_flags = demeanor_response.get('Items', [])
            
            # Get consent records
            consent_table = dynamodb.Table(os.environ.get('CME_CONSENT_TABLE', 'cme-consents'))
            consent_response = consent_table.scan(
                FilterExpression='session_id = :sid',
                ExpressionAttributeValues={':sid': session_id}
            )
            consents = consent_response.get('Items', [])
            
            # Get NEW DATA: Doctor commands, patient confusion, patient distress
            doctor_commands = []
            patient_confusion = []
            patient_distress = []
            attention_metrics = {}
            contact_metrics = {}
            
            # Try to fetch from new tables (if they exist)
            try:
                commands_table = dynamodb.Table(os.environ.get('CME_COMMANDS_TABLE', 'cme-doctor-commands'))
                commands_response = commands_table.scan(
                    FilterExpression='session_id = :sid',
                    ExpressionAttributeValues={':sid': session_id}
                )
                doctor_commands = commands_response.get('Items', [])
            except:
                pass
            
            try:
                confusion_table = dynamodb.Table(os.environ.get('CME_CONFUSION_TABLE', 'cme-patient-confusion'))
                confusion_response = confusion_table.scan(
                    FilterExpression='session_id = :sid',
                    ExpressionAttributeValues={':sid': session_id}
                )
                patient_confusion = confusion_response.get('Items', [])
            except:
                pass
            
            try:
                distress_table = dynamodb.Table(os.environ.get('CME_DISTRESS_TABLE', 'cme-patient-distress'))
                distress_response = distress_table.scan(
                    FilterExpression='session_id = :sid',
                    ExpressionAttributeValues={':sid': session_id}
                )
                patient_distress = distress_response.get('Items', [])
            except:
                pass
            
            # NEW: Gather attention/distraction data and detect inattentive test administration
            distraction_events = self._gather_attention_data(session_id, step_actions)
            inattentive_tests = self._detect_inattentive_test_administration(declared_steps, distraction_events)
            
            return {
                'session': session,
                'declared_steps': sorted(declared_steps, key=lambda x: float(x.get('timestamp', 0))),
                'step_actions': step_actions,
                'demeanor_flags': sorted(demeanor_flags, key=lambda x: float(x.get('timestamp', 0))),
                'consents': consents,
                'doctor_commands': sorted(doctor_commands, key=lambda x: float(x.get('timestamp', 0))),
                'patient_confusion': sorted(patient_confusion, key=lambda x: float(x.get('timestamp', 0))),
                'patient_distress': sorted(patient_distress, key=lambda x: float(x.get('timestamp', 0))),
                'attention_metrics': attention_metrics,
                'contact_metrics': contact_metrics,
                'inattentive_tests': inattentive_tests,
                'distraction_events': distraction_events
            }
            
        except Exception as e:
            logger.error(f"Error gathering session data: {str(e)}")
            return None
    
    def _detect_inattentive_test_administration(
        self,
        declared_steps: List[Dict[str, Any]],
        distraction_events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Cross-reference declared tests with doctor attention/distraction data
        Flags tests where doctor declared a test but wasn't watching during execution
        
        Args:
            declared_steps: List of declared test steps with timestamps
            distraction_events: List of distraction events with start_time/end_time
            
        Returns:
            List of inattentive test administration flags
        """
        inattentive_tests = []
        
        for step in declared_steps:
            test_timestamp = float(step.get('timestamp', 0))
            test_label = step.get('label', 'unknown')
            step_id = step.get('declared_step_id', '')
            
            # Estimate test execution window
            # Most tests take 10-60 seconds to perform
            # We'll check a window from test declaration to 60 seconds after
            test_start = test_timestamp
            test_end = test_timestamp + 60.0  # Assume 60 second window for test execution
            
            # Check if any distraction events overlap with test execution window
            overlapping_distractions = []
            total_distracted_time = 0.0
            
            for distraction in distraction_events:
                dist_start = float(distraction.get('start_time', 0))
                dist_end = float(distraction.get('end_time', 0))
                dist_type = distraction.get('type', 'unknown')
                
                # Check for overlap: distraction overlaps if it starts before test ends and ends after test starts
                if dist_start < test_end and dist_end > test_start:
                    overlap_start = max(test_start, dist_start)
                    overlap_end = min(test_end, dist_end)
                    overlap_duration = overlap_end - overlap_start
                    
                    overlapping_distractions.append({
                        'type': dist_type,
                        'start_time': overlap_start,
                        'end_time': overlap_end,
                        'duration': overlap_duration,
                        'severity': distraction.get('severity', 'medium')
                    })
                    total_distracted_time += overlap_duration
            
            # Calculate attention percentage during test window
            test_duration = test_end - test_start
            attention_percentage = ((test_duration - total_distracted_time) / test_duration * 100) if test_duration > 0 else 100
            
            # Flag as inattentive if:
            # 1. Doctor was distracted for >30% of test window, OR
            # 2. High severity distraction (phone, out of frame) occurred during test
            is_inattentive = False
            severity = 'low'
            
            if attention_percentage < 70:  # Less than 70% attentive
                is_inattentive = True
                severity = 'high' if attention_percentage < 50 else 'medium'
            
            # Check for high severity distractions
            high_severity_distractions = [d for d in overlapping_distractions if d.get('severity') == 'high']
            if high_severity_distractions:
                is_inattentive = True
                severity = 'high'
            
            if is_inattentive:
                inattentive_tests.append({
                    'declared_step_id': step_id,
                    'test_label': test_label,
                    'test_timestamp': test_timestamp,
                    'test_window_start': test_start,
                    'test_window_end': test_end,
                    'attention_percentage': attention_percentage,
                    'distracted_time': total_distracted_time,
                    'distraction_events': overlapping_distractions,
                    'severity': severity,
                    'description': f"Doctor declared {test_label} but was distracted for {total_distracted_time:.1f}s ({100-attention_percentage:.1f}% inattentive) during test execution"
                })
        
        logger.info(f"Detected {len(inattentive_tests)} inattentive test administrations")
        return inattentive_tests
    
    def _gather_attention_data(self, session_id: str, step_actions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Gather doctor attention/distraction data for a session
        This could come from:
        1. Observed actions table (if attention data is stored there)
        2. A dedicated attention/distraction table (if created)
        3. Video processor results
        
        For now, we'll check observed actions for attention metrics
        """
        distraction_events = []
        
        try:
            # Check observed actions for attention/distraction data
            # step_actions is already a dict mapping step_id -> action
            for step_id, action in step_actions.items():
                analysis_details = action.get('analysis_details', {})
                if isinstance(analysis_details, dict):
                    # Check if attention analysis results are stored here
                    attention_data = analysis_details.get('attention_analysis', {})
                    if attention_data:
                        events = attention_data.get('distraction_events', [])
                        distraction_events.extend(events)
            
            # Also scan all actions to find any with attention data
            try:
                actions_table = dynamodb.Table(os.environ.get('CME_ACTIONS_TABLE', 'cme-observed-actions'))
                actions_response = actions_table.scan()
                actions = actions_response.get('Items', [])
                
                # Filter actions that belong to declared steps for this session
                # (We'll match via declared_step_id which links to declared_steps)
                for action in actions:
                    analysis_details = action.get('analysis_details', {})
                    if isinstance(analysis_details, dict):
                        attention_data = analysis_details.get('attention_analysis', {})
                        if attention_data:
                            events = attention_data.get('distraction_events', [])
                            # Only add if not already in list
                            for event in events:
                                if event not in distraction_events:
                                    distraction_events.append(event)
            except Exception as e:
                logger.warning(f"Error scanning actions table: {str(e)}")
                
        except Exception as e:
            logger.warning(f"Error gathering attention data: {str(e)}")
        
        return distraction_events
    
    def _generate_html_report(self, data: Dict[str, Any], include_video: bool) -> str:
        """Generate HTML report from session data"""
        
        session = data['session']
        declared_steps = data['declared_steps']
        step_actions = data['step_actions']
        # Hard noise gate: drop administrative/transcription artifacts and
        # low-severity bedside-manner complaints — they are not findings.
        demeanor_flags = [
            f for f in data['demeanor_flags']
            if f.get('severity') in ('high', 'medium') and not _is_noise_flag(f)
        ]
        doctor_commands = data.get('doctor_commands', [])
        patient_confusion = data.get('patient_confusion', [])
        patient_distress = data.get('patient_distress', [])
        inattentive_tests = data.get('inattentive_tests', [])
        
        # Calculate statistics - DR. HUNTER'S KEY METRIC
        total_tests_mentioned = len(declared_steps)  # All test declarations/mentions
        tests_performed = sum(1 for step in declared_steps 
                             if step_actions.get(step['declared_step_id'], {}).get('motion_present') == 'performed')
        tests_not_performed = sum(1 for step in declared_steps 
                                 if step_actions.get(step['declared_step_id'], {}).get('motion_present') == 'not_observed')
        tests_brief = sum(1 for step in declared_steps 
                         if step_actions.get(step['declared_step_id'], {}).get('motion_present') == 'brief')
        
        # Legacy variable for backward compatibility
        total_tests = total_tests_mentioned
        high_severity_flags = sum(1 for flag in demeanor_flags if flag.get('severity') == 'high')
        
        # NEW STATISTICS
        total_commands = len(doctor_commands)
        confusion_not_clarified = sum(1 for c in patient_confusion if not c.get('clarification_provided', True))
        distress_dismissed = sum(1 for d in patient_distress if d.get('doctor_response') == 'dismissive')
        crying_events = sum(1 for d in patient_distress if d.get('distress_type') == 'emotional')
        tests_not_observed = len(inattentive_tests)

        # Tests the vision model could not judge. These are NOT discrepancies:
        # they must never be counted as "not performed" or presented as
        # evidence against the examiner.
        analysis_summary = _analysis_completion_summary(data)
        tests_unanalyzed = analysis_summary['tests_unanalyzed']
        incomplete_banner = ""
        if tests_unanalyzed:
            incomplete_banner = f"""
        <div style="background:#fff3cd;border:2px solid #e0a800;border-radius:6px;
                    padding:16px;margin:16px 0;color:#664d03;">
            <strong>⚠️ INCOMPLETE ANALYSIS — NOT FOR FILING</strong><br>
            Video analysis did not run for {tests_unanalyzed} of {total_tests_mentioned}
            declared test(s), so this report cannot say whether those tests were
            performed. Absence of a finding here is <em>not</em> evidence that the
            examiner skipped a test. Re-run the analysis once vision processing is
            available before relying on this report.
        </div>
"""

        # Build HTML content
        content = f"""
        <div class="header">
            <h1>📋 CME Analysis Report</h1>
            <p>Compulsory Medical Examination - AI-Powered Analysis</p>
        </div>
{incomplete_banner}
        
        <div class="metadata">
            <div class="metadata-item">
                <strong>Session ID</strong>
                {session.get('session_id', 'N/A')}
            </div>
            <div class="metadata-item">
                <strong>Patient</strong>
                {session.get('patient_name', 'N/A')}
            </div>
            <div class="metadata-item">
                <strong>Examiner</strong>
                {session.get('doctor_name', 'N/A')}
            </div>
            <div class="metadata-item">
                <strong>Exam Date</strong>
                {session.get('exam_date', 'N/A')}
            </div>
            <div class="metadata-item">
                <strong>State</strong>
                {session.get('state', 'N/A')}
            </div>
            <div class="metadata-item">
                <strong>Recording Mode</strong>
                {session.get('mode', 'N/A')}
            </div>
            <div class="metadata-item">
                <strong>Attorney</strong>
                {session.get('attorney_name', 'N/A')}
            </div>
            <div class="metadata-item">
                <strong>Report Generated</strong>
                {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
        </div>
        
        <div class="section">
            <h2>📊 Executive Summary</h2>
            <div class="summary-stats">
                <div class="stat-box" style="background: #fff3cd; border: 2px solid #ffc107;">
                    <div class="stat-number">{total_tests_mentioned}</div>
                    <div class="stat-label">Tests MENTIONED</div>
                    <div style="font-size: 0.8em; color: #856404; margin-top: 5px;">(Doctor declared/intended)</div>
                </div>
                <div class="stat-box" style="background: #d1ecf1; border: 2px solid #17a2b8;">
                    <div class="stat-number">{tests_performed}</div>
                    <div class="stat-label">Tests PERFORMED</div>
                    <div style="font-size: 0.8em; color: #0c5460; margin-top: 5px;">(Video validated)</div>
                </div>
                <div class="stat-box" style="background: #f8d7da; border: 2px solid #dc3545;">
                    <div class="stat-number">{tests_not_performed}</div>
                    <div class="stat-label">Tests NOT Performed</div>
                    <div style="font-size: 0.8em; color: #721c24; margin-top: 5px;">(Mentioned but not observed)</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{tests_brief}</div>
                    <div class="stat-label">Tests Brief/Partial</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{len(demeanor_flags)}</div>
                    <div class="stat-label">Demeanor Flags</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{total_commands}</div>
                    <div class="stat-label">Doctor Instructions</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{len(patient_confusion)}</div>
                    <div class="stat-label">Patient Confusion Events</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{crying_events}</div>
                    <div class="stat-label">Patient Crying Events</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{distress_dismissed}</div>
                    <div class="stat-label">Distress Dismissed</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{tests_not_observed}</div>
                    <div class="stat-label">Tests Not Observed</div>
                </div>
            </div>
        </div>
        
        """
        
        # CROSS-EXAMINATION FINDINGS: numbered, most damning first. Tests the
        # doctor declared but never performed lead; brief/partial follow.
        crossexam_candidates = []
        for step in declared_steps:
            action = step_actions.get(step['declared_step_id'], {})
            motion = action.get('motion_present')
            if motion not in ('not_observed', 'brief'):
                continue
            transcript = str(step.get('transcript_text') or '').strip()
            if _REPORT_NOISE_RE.search(transcript):
                continue
            crossexam_candidates.append({
                'label': str(step.get('label') or 'unknown').replace('_', ' ').title(),
                'timestamp': float(step.get('timestamp', 0)),
                'transcript': transcript,
                'motion': motion,
                'confidence': float(step.get('confidence', 0)),
            })
        # Never performed at all outranks performed briefly/partially.
        crossexam_candidates.sort(
            key=lambda c: (0 if c['motion'] == 'not_observed' else 1, -c['confidence'])
        )
        if crossexam_candidates:
            content += """
        <div class="section" style="border-left: 6px solid #dc3545; background: #fff5f5;">
            <h2>⚖️ CROSS-EXAMINATION FINDINGS</h2>
            <p>Ranked most-damning first. Each finding pits the examiner's own declared test
            against the timestamped video record.</p>
        """
            for i, c in enumerate(crossexam_candidates[:10], start=1):
                minutes = int(c['timestamp'] // 60)
                seconds = int(c['timestamp'] % 60)
                time_str = f"{minutes}:{seconds:02d}"
                if c['motion'] == 'not_observed':
                    fact = (
                        f"The video does not show {c['label']} being performed. "
                        f"The declaration appears at {time_str} of the video with no "
                        f"corresponding examination."
                    )
                else:
                    fact = (
                        f"What was performed at {time_str} of the video was brief/partial "
                        f"and does not qualify as a complete {c['label']}."
                    )
                quote = c['transcript'][:200]
                quote_html = (
                    f"<p><em>Declared on video:</em> &ldquo;{quote}&rdquo;</p>" if quote else ""
                )
                content += f"""
            <div style="background: white; border-left: 4px solid #dc3545; padding: 12px 16px; margin: 12px 0; border-radius: 4px;">
                <h3 style="margin: 0 0 8px 0; color: #721c24;">CROSS EXAMINATION #{i}: Examiner declared {c['label']} during the examination.</h3>
                {quote_html}
                <p><strong>FACT:</strong> {fact} See {time_str} of the video.</p>
            </div>
            """
            content += """
        </div>
        """
        
        # Add inattentive tests section if any exist
        if inattentive_tests:
            content += """
        <div class="section">
            <h2>⚠️ Tests Performed While Doctor Was Distracted</h2>
            <p>The following tests were declared by the examiner but the doctor was not adequately observing the patient during test execution:</p>
            <div class="timeline">
            """
            
            for inattentive in inattentive_tests:
                test_timestamp = inattentive.get('test_timestamp', 0)
                test_label = inattentive.get('test_label', 'unknown')
                attention_pct = inattentive.get('attention_percentage', 100)
                distracted_time = inattentive.get('distracted_time', 0)
                severity = inattentive.get('severity', 'medium')
                distraction_events = inattentive.get('distraction_events', [])
                
                minutes = int(test_timestamp // 60)
                seconds = int(test_timestamp % 60)
                time_str = f"{minutes:02d}:{seconds:02d}"
                
                severity_class = 'high-severity' if severity == 'high' else 'medium-severity'
                
                content += f"""
                <div class="timeline-item {severity_class}">
                    <div class="timeline-time">⏰ {time_str}</div>
                    <span class="timeline-label">{test_label.replace('_', ' ').title()}</span>
                    <p><strong>Attention Level:</strong> {attention_pct:.1f}% (Doctor was distracted for {distracted_time:.1f} seconds)</p>
                    <p><strong>Severity:</strong> {severity.upper()}</p>
                """
                
                if distraction_events:
                    content += "<p><strong>Distraction Events During Test:</strong></p><ul>"
                    for dist_event in distraction_events:
                        dist_type = dist_event.get('type', 'unknown')
                        dist_duration = dist_event.get('duration', 0)
                        content += f"<li>{dist_type.replace('_', ' ').title()}: {dist_duration:.1f} seconds</li>"
                    content += "</ul>"
                
                content += "</div>"
            
            content += """
            </div>
        </div>
        """
        
        content += """
        <div class="section">
            <h2>⏱️ Examination Timeline</h2>
            <div class="timeline">
        """
        
        # Add timeline items for declared tests
        for step in declared_steps:
            step_id = step['declared_step_id']
            timestamp = float(step.get('timestamp', 0))
            label = step.get('label', 'Unknown Test')
            transcript = step.get('transcript_text', '')
            confidence = float(step.get('confidence', 0))
            
            action = step_actions.get(step_id, {})
            motion_present = action.get('motion_present', 'unknown')
            
            # Better handling of missing video analysis
            if motion_present == 'unknown':
                motion_display = "⏳ Video Analysis Pending"
                motion_class = "pending"
            elif motion_present == 'analysis_unavailable':
                # Vision model did not return a verdict. Never present this as
                # evidence for or against the examiner.
                motion_display = "⚠️ Not Analyzed — vision analysis unavailable"
                motion_class = "pending"
            elif motion_present == 'performed':
                motion_display = "✅ Performed"
                motion_class = "performed"
            elif motion_present == 'brief':
                motion_display = "⚠️ Brief/Partial"
                motion_class = "brief"
            elif motion_present == 'not_observed':
                motion_display = "❌ Not Observed"
                motion_class = "not_observed"
            else:
                motion_display = motion_present.replace('_', ' ').title()
                motion_class = motion_present
            
            is_discrepancy = motion_present in ['not_observed', 'brief']
            discrepancy_class = 'discrepancy' if is_discrepancy else ''
            
            # Format timestamp as MM:SS
            minutes = int(timestamp // 60)
            seconds = int(timestamp % 60)
            time_str = f"{minutes:02d}:{seconds:02d}"
            
            content += f"""
                <div class="timeline-item {discrepancy_class}">
                    <div class="timeline-time">⏰ {time_str}</div>
                    <span class="timeline-label">{label.replace('_', ' ').title()}</span>
                    <p><strong>Examiner stated:</strong> "{transcript[:200]}{'...' if len(transcript) > 200 else ''}"</p>
                    <p><strong>Observed Action:</strong> <span class="motion-{motion_class}">{motion_display}</span></p>
                    <div class="confidence-bar">
                        <div class="confidence-fill" style="width: {confidence * 100}%"></div>
                    </div>
                    <small>Detection Confidence: {confidence * 100:.1f}%</small>
            """
            
            if include_video and step.get('video_snippet_uri'):
                content += f"""
                    <a href="#" class="video-link" onclick="alert('Video playback would open here')">
                        🎥 View Video Clip
                    </a>
                """
            
            content += "</div>"
        
        content += """
            </div>
        </div>
        """
        
        # Add demeanor analysis section
        if demeanor_flags:
            content += """
            <div class="section">
                <h2>🎭 Demeanor Analysis</h2>
                <p>The following behavioral patterns and tone issues were detected during the examination:</p>
            """
            
            for flag in demeanor_flags:
                flag_type = flag.get('flag_type', 'unknown')
                severity = flag.get('severity', 'low')
                timestamp = float(flag.get('timestamp', 0))
                excerpt = flag.get('transcript_excerpt', '')
                description = flag.get('description', '')
                
                minutes = int(timestamp // 60)
                seconds = int(timestamp % 60)
                time_str = f"{minutes:02d}:{seconds:02d}"
                
                content += f"""
                <div class="flag flag-{severity}">
                    <div class="flag-type">
                        {'🚨' if severity == 'high' else '⚠️' if severity == 'medium' else 'ℹ️'} 
                        {flag_type.replace('_', ' ').title()} - {severity.upper()} Severity
                    </div>
                    <p><strong>Time:</strong> {time_str}</p>
                    <p><strong>Issue:</strong> {description}</p>
                    <div class="transcript-excerpt">
                        "{excerpt[:300]}{'...' if len(excerpt) > 300 else ''}"
                    </div>
                </div>
                """
            
            content += "</div>"
        
        # Add patient confusion section
        if patient_confusion:
            content += """
            <div class="section">
                <h2>🤔 Patient Confusion & Comprehension Issues</h2>
                <p>Instances where patient expressed confusion or did not understand examiner's instructions:</p>
            """
            
            for confusion in patient_confusion:
                timestamp = float(confusion.get('timestamp', 0))
                statement = confusion.get('patient_statement', '')
                clarified = confusion.get('clarification_provided', False)
                severity = confusion.get('severity', 'low')
                
                minutes = int(timestamp // 60)
                seconds = int(timestamp % 60)
                time_str = f"{minutes:02d}:{seconds:02d}"
                
                content += f"""
                <div class="flag flag-{severity}">
                    <div class="flag-type">
                        {'✓' if clarified else '⚠️'} PATIENT CONFUSION - {severity.upper()}
                    </div>
                    <p><strong>Time:</strong> {time_str}</p>
                    <p><strong>Patient said:</strong> "{statement[:300]}{'...' if len(statement) > 300 else ''}"</p>
                    <p><strong>Doctor clarified:</strong> {'Yes ✓' if clarified else 'No ⚠️ - Doctor did not provide clarification'}</p>
                </div>
                """
            
            clarification_rate = ((len(patient_confusion) - confusion_not_clarified) / len(patient_confusion) * 100) if patient_confusion else 0
            content += f"""
                <p><strong>Summary:</strong> Patient expressed confusion {len(patient_confusion)} times. 
                Doctor provided clarification in {clarification_rate:.1f}% of cases.</p>
            </div>
            """
        
        # Add patient distress section
        if patient_distress:
            content += """
            <div class="section">
                <h2>😢 Patient Distress & Emotional Events</h2>
                <p>Instances where patient expressed pain, distress, or became emotional:</p>
            """
            
            for distress in patient_distress:
                timestamp = float(distress.get('timestamp', 0))
                statement = distress.get('patient_statement', '')
                distress_type = distress.get('distress_type', 'unknown')
                doctor_response = distress.get('doctor_response', 'no_response')
                severity = distress.get('severity', 'medium')
                
                minutes = int(timestamp // 60)
                seconds = int(timestamp % 60)
                time_str = f"{minutes:02d}:{seconds:02d}"
                
                response_emoji = {
                    'empathetic': '✓',
                    'acknowledged': '~',
                    'dismissive': '⚠️',
                    'no_response': '❌'
                }.get(doctor_response, '?')
                
                distress_emoji = '😢' if distress_type == 'emotional' else '😣'
                
                content += f"""
                <div class="flag flag-{severity}">
                    <div class="flag-type">
                        {distress_emoji} {distress_type.upper()} DISTRESS - {severity.upper()}
                    </div>
                    <p><strong>Time:</strong> {time_str}</p>
                    <p><strong>Patient said:</strong> "{statement[:300]}{'...' if len(statement) > 300 else ''}"</p>
                    <p><strong>Doctor response:</strong> {response_emoji} {doctor_response.replace('_', ' ').title()}</p>
                </div>
                """
            
            content += f"""
                <p><strong>Summary:</strong> Patient expressed distress {len(patient_distress)} times. 
                {crying_events} emotional/crying event(s). 
                Doctor dismissed distress in {distress_dismissed} case(s) ⚠️</p>
            </div>
            """
        
        # Add doctor commands section
        if doctor_commands:
            content += f"""
            <div class="section">
                <h2>📢 Doctor Instructions to Patient</h2>
                <p>Commands given by examiner requiring patient action and doctor observation:</p>
                <p><strong>Total commands:</strong> {len(doctor_commands)}</p>
            """
            
            for i, command in enumerate(doctor_commands[:10]):  # Show first 10
                timestamp = float(command.get('timestamp', 0))
                cmd_text = command.get('command', '')
                
                minutes = int(timestamp // 60)
                seconds = int(timestamp % 60)
                time_str = f"{minutes:02d}:{seconds:02d}"
                
                content += f"""
                <div style="padding: 10px; margin: 5px 0; background: #f9f9f9; border-left: 3px solid #667eea;">
                    <strong>[{time_str}]</strong> "{cmd_text[:200]}{'...' if len(cmd_text) > 200 else ''}"
                </div>
                """
            
            if len(doctor_commands) > 10:
                content += f"<p><em>... and {len(doctor_commands) - 10} more commands</em></p>"
            
            content += "</div>"
        
        # Add legal basis section
        recording_rules = session.get('recording_allowed', {})
        content += f"""
        <div class="section">
            <h2>⚖️ Legal Basis</h2>
            <p><strong>Jurisdiction:</strong> {session.get('state', 'N/A')}</p>
            <p><strong>Legal Rule:</strong> {recording_rules.get('rule', 'N/A')}</p>
            <p><strong>Recording Permitted:</strong> Video: {recording_rules.get('video', False)}, Audio: {recording_rules.get('audio', False)}</p>
            <p>This recording was made in compliance with applicable state law and belongs to the plaintiff and their legal representative.</p>
        </div>
        """
        
        # Add footer
        content += """
        <div class="footer">
            <p><strong>AI-Powered CME Analysis Platform</strong></p>
            <p>This report was generated using artificial intelligence analysis of audio, video, and transcripts.</p>
            <p>For legal use by authorized attorneys only. Confidential and protected by work-product privilege.</p>
        </div>
        """
        
        return HTML_REPORT_TEMPLATE.format(content=content)
    
    def create_report_bundle(
        self,
        session_id: str,
        include_recording: bool = True,
        include_transcript: bool = True
    ) -> Dict[str, Any]:
        """
        Create a downloadable bundle with report, recording, and supporting files
        
        Returns:
            S3 location of ZIP bundle
        """
        try:
            import zipfile
            import tempfile
            import os
            
            # Create temporary directory
            temp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(temp_dir, f'cme_report_{session_id}.zip')
            
            # Gather session data
            data = self._gather_session_data(session_id)
            if not data:
                return {'error': 'Session not found'}
            
            session = data['session']
            
            # Create ZIP file
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add HTML report
                report_html = self._generate_html_report(data, include_video=True)
                zipf.writestr('CME_Analysis_Report.html', report_html)
                
                # Add JSON data
                json_data = json.dumps(data, indent=2, default=str)
                zipf.writestr('session_data.json', json_data)
                
                # Add consent records
                consents_text = "CONSENT RECORDS\n\n"
                for consent in data.get('consents', []):
                    consents_text += f"Role: {consent.get('participant_role')}\n"
                    consents_text += f"Timestamp: {consent.get('timestamp')}\n"
                    consents_text += f"Signature: {consent.get('signature')}\n\n"
                zipf.writestr('consents.txt', consents_text)
                
                # Optionally download and include recording
                # (In production, this would be very large - may want to provide separate download link)
            
            # Upload ZIP to S3
            bundle_key = f"cme-reports/{session_id}/report_bundle.zip"
            with open(zip_path, 'rb') as f:
                s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=bundle_key,
                    Body=f,
                    ContentType='application/zip'
                )
            
            # Generate download URL
            download_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.s3_bucket, 'Key': bundle_key},
                ExpiresIn=86400
            )
            
            # Cleanup
            os.remove(zip_path)
            os.rmdir(temp_dir)
            
            return {
                'bundle_key': bundle_key,
                'download_url': download_url,
                'session_id': session_id
            }
            
        except Exception as e:
            logger.error(f"Error creating report bundle: {str(e)}")
            return {'error': str(e)}


def _update_session_after_report(
    session_id: str,
    *,
    success: bool,
    report_key: str = '',
    error: str = '',
    analysis_status: str = 'complete',
    tests_unanalyzed: int = 0,
    total_declared_tests: int = 0,
) -> None:
    """Reflect report generation outcome on the session record so the UI
    never shows 'completed' without a report or 'processing' forever."""
    import time as _time
    try:
        sessions_table = dynamodb.Table(os.environ.get('CME_SESSIONS_TABLE', 'cme-sessions'))
        if success:
            tests_unanalyzed = int(tests_unanalyzed or 0)
            total_declared_tests = int(total_declared_tests or 0)
            has_unanalyzed_tests = analysis_status == 'incomplete' or tests_unanalyzed > 0
            status = 'completed_with_warnings' if has_unanalyzed_tests else 'completed'
            stage = 'analysis_incomplete' if has_unanalyzed_tests else 'report_generated'
            warning = ''
            if has_unanalyzed_tests:
                warning = (
                    f"Vision analysis did not run for {tests_unanalyzed} of "
                    f"{total_declared_tests} declared test(s)."
                )
            sessions_table.update_item(
                Key={'session_id': session_id},
                UpdateExpression=(
                    'SET #status = :status, processing_stage = :stage, '
                    'report_key = :key, updated_at = :updated, '
                    'analysis_status = :analysis_status, '
                    'tests_unanalyzed = :tests_unanalyzed, '
                    'total_declared_tests = :total_declared_tests, '
                    'analysis_warning = :analysis_warning'
                ),
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': status,
                    ':stage': stage,
                    ':key': report_key,
                    ':updated': int(_time.time()),
                    ':analysis_status': analysis_status,
                    ':tests_unanalyzed': tests_unanalyzed,
                    ':total_declared_tests': total_declared_tests,
                    ':analysis_warning': warning,
                },
            )
        else:
            sessions_table.update_item(
                Key={'session_id': session_id},
                UpdateExpression=(
                    'SET #status = :status, processing_stage = :stage, '
                    'last_error = :err, updated_at = :updated'
                ),
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'error',
                    ':stage': 'report_failed',
                    ':err': (error or 'report generation failed')[:500],
                    ':updated': int(_time.time()),
                },
            )
    except Exception as ddb_error:
        logger.error(f"Failed to update session after report generation: {ddb_error}")


def generate_report(event, context):
    """
    Lambda handler for Step Functions invocation
    Generates CME analysis report
    """
    session_id = None
    try:
        logger.info(json.dumps({
            'message': 'Report Generator invoked',
            'request_id': getattr(context, 'aws_request_id', None),
            'session_id': event.get('session_id') if isinstance(event, dict) else None,
            'format': event.get('format', 'html') if isinstance(event, dict) else 'html',
        }))
        
        session_id = event.get('session_id')
        format = event.get('format', 'html')
        
        if not session_id:
            return {
                'statusCode': 400,
                'error': 'session_id is required'
            }
        
        s3_bucket = os.environ.get('S3_BUCKET', 'cme-analysis-recordings-388846700527')
        generator = CMEReportGenerator(s3_bucket)
        
        # Generate report
        result = generator.generate_report(
            session_id=session_id,
            include_video_links=True,
            format=format
        )
        
        if 'error' in result:
            # Mark the session failed and raise so Step Functions' Catch
            # runs instead of silently completing a session with no report.
            _update_session_after_report(session_id, success=False, error=str(result['error']))
            raise RuntimeError(f"Report generation failed: {result['error']}")
        
        _update_session_after_report(
            session_id,
            success=True,
            report_key=str(result.get('report_key') or ''),
            analysis_status=str(result.get('analysis_status') or 'complete'),
            tests_unanalyzed=int(result.get('tests_unanalyzed') or 0),
            total_declared_tests=int(result.get('total_declared_tests') or 0),
        )
        return {
            'statusCode': 200,
            **result
        }
        
    except Exception as e:
        logger.error(f"Error in report generator handler: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        if session_id:
            _update_session_after_report(session_id, success=False, error=str(e))
        raise


# Import os for environment variables
import os
