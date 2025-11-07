"""
CME Report Generator - Create structured reports from CME analysis
Implements Step 8 from the technical documentation
"""

import json
import boto3
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from decimal import Decimal
import base64

logger = logging.getLogger()
logger.setLevel(logging.INFO)

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
            
            # Generate report based on format
            if format == 'html':
                report_content = self._generate_html_report(report_data, include_video_links)
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
                'generated_at': datetime.now().isoformat()
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
            
            return {
                'session': session,
                'declared_steps': sorted(declared_steps, key=lambda x: float(x.get('timestamp', 0))),
                'step_actions': step_actions,
                'demeanor_flags': sorted(demeanor_flags, key=lambda x: float(x.get('timestamp', 0))),
                'consents': consents
            }
            
        except Exception as e:
            logger.error(f"Error gathering session data: {str(e)}")
            return None
    
    def _generate_html_report(self, data: Dict[str, Any], include_video: bool) -> str:
        """Generate HTML report from session data"""
        
        session = data['session']
        declared_steps = data['declared_steps']
        step_actions = data['step_actions']
        demeanor_flags = data['demeanor_flags']
        
        # Calculate statistics
        total_tests = len(declared_steps)
        tests_performed = sum(1 for step in declared_steps 
                             if step_actions.get(step['declared_step_id'], {}).get('motion_present') == 'performed')
        tests_not_performed = sum(1 for step in declared_steps 
                                 if step_actions.get(step['declared_step_id'], {}).get('motion_present') == 'not_observed')
        high_severity_flags = sum(1 for flag in demeanor_flags if flag.get('severity') == 'high')
        
        # Build HTML content
        content = f"""
        <div class="header">
            <h1>📋 CME Analysis Report</h1>
            <p>Compulsory Medical Examination - AI-Powered Analysis</p>
        </div>
        
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
                <div class="stat-box">
                    <div class="stat-number">{total_tests}</div>
                    <div class="stat-label">Tests Declared</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{tests_performed}</div>
                    <div class="stat-label">Tests Performed</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{tests_not_performed}</div>
                    <div class="stat-label">Tests Not Observed</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{len(demeanor_flags)}</div>
                    <div class="stat-label">Demeanor Flags</div>
                </div>
            </div>
        </div>
        
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
                    <p><strong>Observed Action:</strong> {motion_present.replace('_', ' ').title()}</p>
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


# Import os for environment variables
import os

