#!/usr/bin/env python3
"""
CME Analysis Runner - Complete pipeline for analyzing CME video recordings
Analyzes videos, extracts transcripts, detects medical tests, and generates report
"""

import os
import sys
import json
import time
import uuid
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# AWS clients
import boto3
from botocore.exceptions import ClientError

# Configuration
AWS_REGION = 'us-east-1'
S3_BUCKET = 'eve-legal-documents-388846700527'

# Initialize clients
s3_client = boto3.client('s3', region_name=AWS_REGION)
transcribe_client = boto3.client('transcribe', region_name=AWS_REGION)
bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)

class CMEAnalyzer:
    def __init__(self, case_info: Dict[str, str], video_files: List[str]):
        self.case_info = case_info
        self.video_files = video_files
        self.session_id = f"cme_{uuid.uuid4().hex[:12]}"
        self.transcripts = []
        self.declared_tests = []
        self.analysis_results = []
        
    def run_full_analysis(self) -> Dict[str, Any]:
        """Run complete CME analysis pipeline"""
        print(f"\n{'='*60}")
        print(f"CME ANALYSIS - {self.case_info['plaintiff_name']}")
        print(f"{'='*60}")
        print(f"Session ID: {self.session_id}")
        print(f"Examiner: {self.case_info['examiner']}")
        print(f"DOB: {self.case_info['dob']}")
        print(f"DOI: {self.case_info['doi']}")
        print(f"Videos: {len(self.video_files)}")
        print(f"{'='*60}\n")
        
        # Step 1: Upload videos to S3
        print("📤 Step 1: Uploading videos to S3...")
        s3_keys = self.upload_videos()
        
        # Step 2: Start transcriptions
        print("\n🎙️ Step 2: Starting transcriptions...")
        job_names = self.start_transcriptions(s3_keys)
        
        # Step 3: Wait for transcriptions
        print("\n⏳ Step 3: Waiting for transcriptions to complete...")
        self.wait_for_transcriptions(job_names)
        
        # Step 4: Get transcripts
        print("\n📝 Step 4: Retrieving transcripts...")
        self.get_transcripts(job_names)
        
        # Step 5: Analyze transcripts for declared tests
        print("\n🔍 Step 5: Analyzing transcripts for medical tests...")
        self.analyze_transcripts()
        
        # Step 6: AI analysis of test performance
        print("\n🤖 Step 6: AI analysis of test performance...")
        self.analyze_test_performance()
        
        # Step 7: Generate report
        print("\n📊 Step 7: Generating report...")
        report = self.generate_report()
        
        return report
    
    def upload_videos(self) -> List[str]:
        """Upload video files to S3"""
        s3_keys = []
        for i, video_path in enumerate(self.video_files):
            filename = os.path.basename(video_path)
            s3_key = f"cme-recordings/{self.session_id}/{filename}"
            
            print(f"  Uploading {filename}...")
            file_size = os.path.getsize(video_path) / (1024 * 1024)
            
            try:
                s3_client.upload_file(video_path, S3_BUCKET, s3_key)
                print(f"  ✓ Uploaded: {filename} ({file_size:.1f} MB)")
                s3_keys.append(s3_key)
            except Exception as e:
                print(f"  ✗ Failed: {e}")
        
        return s3_keys
    
    def start_transcriptions(self, s3_keys: List[str]) -> List[str]:
        """Start AWS Transcribe jobs for each video"""
        job_names = []
        
        for i, s3_key in enumerate(s3_keys):
            job_name = f"{self.session_id}_part{i+1}_{int(time.time())}"
            media_uri = f"s3://{S3_BUCKET}/{s3_key}"
            
            try:
                transcribe_client.start_transcription_job(
                    TranscriptionJobName=job_name,
                    Media={'MediaFileUri': media_uri},
                    MediaFormat='mp4',
                    LanguageCode='en-US',
                    OutputBucketName=S3_BUCKET,
                    OutputKey=f"cme-transcripts/{self.session_id}/{job_name}.json",
                    Settings={
                        'ShowSpeakerLabels': True,
                        'MaxSpeakerLabels': 3
                    }
                )
                print(f"  ✓ Started transcription job: {job_name}")
                job_names.append(job_name)
            except Exception as e:
                print(f"  ✗ Failed to start transcription: {e}")
        
        return job_names
    
    def wait_for_transcriptions(self, job_names: List[str], timeout: int = 1800):
        """Wait for all transcription jobs to complete"""
        start_time = time.time()
        completed = set()
        
        while len(completed) < len(job_names):
            if time.time() - start_time > timeout:
                print("  ⚠ Timeout waiting for transcriptions")
                break
            
            for job_name in job_names:
                if job_name in completed:
                    continue
                    
                try:
                    response = transcribe_client.get_transcription_job(
                        TranscriptionJobName=job_name
                    )
                    status = response['TranscriptionJob']['TranscriptionJobStatus']
                    
                    if status == 'COMPLETED':
                        print(f"  ✓ Completed: {job_name}")
                        completed.add(job_name)
                    elif status == 'FAILED':
                        print(f"  ✗ Failed: {job_name}")
                        completed.add(job_name)
                except Exception as e:
                    pass
            
            if len(completed) < len(job_names):
                elapsed = int(time.time() - start_time)
                print(f"  ⏳ Waiting... ({elapsed}s elapsed, {len(completed)}/{len(job_names)} done)")
                time.sleep(30)
    
    def get_transcripts(self, job_names: List[str]):
        """Retrieve completed transcripts from S3"""
        for job_name in job_names:
            try:
                response = transcribe_client.get_transcription_job(
                    TranscriptionJobName=job_name
                )
                
                if response['TranscriptionJob']['TranscriptionJobStatus'] == 'COMPLETED':
                    transcript_uri = response['TranscriptionJob']['Transcript']['TranscriptFileUri']
                    
                    # Download transcript from S3
                    s3_key = f"cme-transcripts/{self.session_id}/{job_name}.json"
                    local_path = f"/tmp/{job_name}.json"
                    
                    s3_client.download_file(S3_BUCKET, s3_key, local_path)
                    
                    with open(local_path, 'r') as f:
                        transcript_data = json.load(f)
                    
                    transcript_text = transcript_data['results']['transcripts'][0]['transcript']
                    self.transcripts.append({
                        'job_name': job_name,
                        'text': transcript_text,
                        'items': transcript_data['results'].get('items', [])
                    })
                    print(f"  ✓ Retrieved transcript: {len(transcript_text)} chars")
            except Exception as e:
                print(f"  ✗ Error getting transcript {job_name}: {e}")
    
    def analyze_transcripts(self):
        """Use AI to analyze transcripts and detect declared medical tests"""
        combined_transcript = "\n\n".join([t['text'] for t in self.transcripts])
        
        prompt = f"""You are an expert medical-legal analyst reviewing a Compulsory Medical Examination (CME) video transcript.

CASE INFORMATION:
- Plaintiff: {self.case_info['plaintiff_name']}
- DOB: {self.case_info['dob']}
- Date of Injury: {self.case_info['doi']}
- Examining Doctor: {self.case_info['examiner']}

TRANSCRIPT:
{combined_transcript[:30000]}

TASK: Identify ALL medical tests, examinations, and procedures that the doctor mentions, describes, or claims to perform.

For each test identified, provide:
1. Test name (standardized medical terminology)
2. Body region examined
3. Exact quote from transcript where test is mentioned
4. Whether the doctor claims a specific result
5. Approximate timestamp (if determinable from context)

IMPORTANT: Distinguish between:
- Tests the doctor SAYS they will do
- Tests the doctor CLAIMS to have done
- Tests where specific measurements are given (e.g., "flexion 45 degrees")
- Tests where only vague results are stated (e.g., "range of motion is adequate")

Return JSON format:
{{
    "tests_identified": [
        {{
            "test_name": "string",
            "body_region": "string", 
            "transcript_quote": "string",
            "result_claimed": "string or null",
            "measurement_given": true/false,
            "specific_degrees": "string or null",
            "vague_assessment": true/false,
            "timestamp_approx": "string or null"
        }}
    ],
    "total_exam_duration_estimate": "string",
    "hands_on_exam_duration_estimate": "string",
    "red_flags": ["list of concerns"],
    "summary": "brief summary of examination"
}}"""

        try:
            response = bedrock_client.invoke_model(
                modelId='meta.llama3-8b-instruct-v1:0',
                body=json.dumps({
                    'prompt': prompt,
                    'max_gen_len': 4000,
                    'temperature': 0.1
                })
            )
            
            result = json.loads(response['body'].read().decode('utf-8'))
            content = result.get('generation', '{}')
            
            # Extract JSON from response
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                analysis = json.loads(json_match.group())
                self.declared_tests = analysis.get('tests_identified', [])
                self.exam_summary = analysis
                print(f"  ✓ Identified {len(self.declared_tests)} declared tests")
            else:
                print(f"  ✗ Could not parse AI response")
                self.declared_tests = []
                self.exam_summary = {}
                
        except Exception as e:
            print(f"  ✗ AI analysis error: {e}")
            self.declared_tests = []
            self.exam_summary = {}
    
    def analyze_test_performance(self):
        """Analyze each declared test to determine if properly performed"""
        
        for test in self.declared_tests:
            test_name = test.get('test_name', 'Unknown')
            body_region = test.get('body_region', '')
            transcript_quote = test.get('transcript_quote', '')
            measurement_given = test.get('measurement_given', False)
            vague_assessment = test.get('vague_assessment', False)
            
            # Determine performance status using AI
            prompt = f"""Analyze this medical test from a CME examination:

TEST: {test_name}
BODY REGION: {body_region}
DOCTOR'S STATEMENT: "{transcript_quote}"
MEASUREMENT GIVEN: {measurement_given}
VAGUE ASSESSMENT: {vague_assessment}

Based on medical literature and AMA Guides standards, determine:

1. Was this test properly performed per standard protocols?
2. Were objective measurements documented (specific degrees, not "adequate" or "full")?
3. What would a proper examination of this type require?
4. What deficiencies are present?

IMPORTANT CONTEXT:
- Per Hirsch study: visual estimation of ROM has 11.9° error - proper exam requires goniometer/inclinometer
- AMA Guides require specific degree measurements for impairment ratings
- Vague terms like "adequate", "full", "WNL" without numbers are red flags
- Cervical ROM requires 6 planes: flexion, extension, left/right lateral flexion, left/right rotation

Return JSON:
{{
    "properly_performed": true/false,
    "objective_measurements": true/false,
    "deficiencies": ["list"],
    "what_was_required": "string",
    "confidence": 0.0-1.0,
    "status": "performed" | "brief" | "not_observed" | "inadequate"
}}"""

            try:
                response = bedrock_client.invoke_model(
                    modelId='meta.llama3-8b-instruct-v1:0',
                    body=json.dumps({
                        'prompt': prompt,
                        'max_gen_len': 800,
                        'temperature': 0.1
                    })
                )
                
                result = json.loads(response['body'].read().decode('utf-8'))
                content = result.get('generation', '{}')
                
                import re
                json_match = re.search(r'\{[\s\S]*?\}', content)
                if json_match:
                    analysis = json.loads(json_match.group())
                    test['performance_analysis'] = analysis
                    status = analysis.get('status', 'unknown')
                    print(f"  • {test_name}: {status}")
                    
            except Exception as e:
                test['performance_analysis'] = {'error': str(e), 'status': 'unknown'}
        
        self.analysis_results = self.declared_tests
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive CME analysis report"""
        
        # Count statistics
        total_tests = len(self.declared_tests)
        performed = sum(1 for t in self.declared_tests 
                       if t.get('performance_analysis', {}).get('status') == 'performed')
        inadequate = sum(1 for t in self.declared_tests 
                        if t.get('performance_analysis', {}).get('status') == 'inadequate')
        not_observed = sum(1 for t in self.declared_tests 
                         if t.get('performance_analysis', {}).get('status') == 'not_observed')
        
        # Collect deficiencies
        all_deficiencies = []
        for test in self.declared_tests:
            analysis = test.get('performance_analysis', {})
            deficiencies = analysis.get('deficiencies', [])
            for d in deficiencies:
                all_deficiencies.append({
                    'test': test.get('test_name'),
                    'deficiency': d
                })
        
        report = {
            'case_information': {
                'plaintiff_name': self.case_info['plaintiff_name'],
                'date_of_birth': self.case_info['dob'],
                'date_of_injury': self.case_info['doi'],
                'examining_doctor': self.case_info['examiner'],
                'analysis_date': datetime.now().strftime('%Y-%m-%d'),
                'session_id': self.session_id
            },
            'summary': {
                'total_tests_declared': total_tests,
                'tests_properly_performed': performed,
                'tests_inadequate': inadequate,
                'tests_not_observed': not_observed,
                'performance_rate': f"{(performed/total_tests*100):.1f}%" if total_tests > 0 else "N/A",
                'exam_duration_estimate': self.exam_summary.get('total_exam_duration_estimate', 'Unknown'),
                'hands_on_duration_estimate': self.exam_summary.get('hands_on_exam_duration_estimate', 'Unknown')
            },
            'red_flags': self.exam_summary.get('red_flags', []),
            'deficiencies': all_deficiencies,
            'tests_analyzed': self.declared_tests,
            'transcripts': [{'job': t['job_name'], 'length': len(t['text'])} for t in self.transcripts],
            'methodology': {
                'video_analysis': 'Bedrock AI (Rekognition disabled for cost savings)',
                'transcript_analysis': 'AWS Transcribe + Claude AI',
                'standards_applied': ['AMA Guides', 'Hirsch ROM Study', 'AAOS Guidelines']
            }
        }
        
        # Save report
        report_path = f"/Users/hammadhaque/Documents/cme-analysis-platform/cme_report_{self.session_id}.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"  ✓ Report saved: {report_path}")
        
        # Generate HTML report
        html_path = self.generate_html_report(report)
        
        return report
    
    def generate_html_report(self, report: Dict) -> str:
        """Generate HTML version of report"""
        
        case = report['case_information']
        summary = report['summary']
        
        # Build test rows
        test_rows = ""
        for test in report.get('tests_analyzed', []):
            analysis = test.get('performance_analysis', {})
            status = analysis.get('status', 'unknown')
            
            status_class = {
                'performed': 'status-performed',
                'inadequate': 'status-inadequate', 
                'not_observed': 'status-not-observed',
                'brief': 'status-brief'
            }.get(status, 'status-unknown')
            
            deficiencies = analysis.get('deficiencies', [])
            deficiency_html = "<br>".join([f"• {d}" for d in deficiencies]) if deficiencies else "None"
            
            test_rows += f"""
            <tr>
                <td>{test.get('test_name', 'Unknown')}</td>
                <td>{test.get('body_region', '')}</td>
                <td class="{status_class}">{status.upper()}</td>
                <td>{'Yes' if test.get('measurement_given') else 'No'}</td>
                <td class="deficiency">{deficiency_html}</td>
            </tr>"""
        
        # Build deficiency list
        deficiency_items = ""
        for d in report.get('deficiencies', []):
            deficiency_items += f"<li><strong>{d['test']}:</strong> {d['deficiency']}</li>"
        
        # Build red flags
        red_flag_items = ""
        for rf in report.get('red_flags', []):
            red_flag_items += f"<li>{rf}</li>"
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>CME Analysis Report - {case['plaintiff_name']}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 40px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #1a365d; border-bottom: 3px solid #3182ce; padding-bottom: 15px; }}
        h2 {{ color: #2d3748; margin-top: 30px; }}
        .header-info {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; background: #edf2f7; padding: 20px; border-radius: 8px; margin-bottom: 30px; }}
        .header-info div {{ }}
        .header-info label {{ font-weight: bold; color: #4a5568; }}
        .header-info span {{ color: #1a202c; }}
        .summary-box {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
        .summary-item {{ background: #f7fafc; padding: 20px; border-radius: 8px; text-align: center; }}
        .summary-item .number {{ font-size: 36px; font-weight: bold; color: #2d3748; }}
        .summary-item .label {{ color: #718096; font-size: 14px; }}
        .performed {{ color: #38a169; }}
        .inadequate {{ color: #dd6b20; }}
        .not-observed {{ color: #e53e3e; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th {{ background: #2d3748; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 12px; border-bottom: 1px solid #e2e8f0; }}
        tr:hover {{ background: #f7fafc; }}
        .status-performed {{ color: #38a169; font-weight: bold; }}
        .status-inadequate {{ color: #dd6b20; font-weight: bold; }}
        .status-not-observed {{ color: #e53e3e; font-weight: bold; }}
        .status-brief {{ color: #d69e2e; font-weight: bold; }}
        .status-unknown {{ color: #718096; }}
        .deficiency {{ font-size: 12px; color: #e53e3e; }}
        .red-flags {{ background: #fed7d7; border-left: 4px solid #e53e3e; padding: 15px; margin: 20px 0; }}
        .red-flags h3 {{ color: #c53030; margin-top: 0; }}
        .deficiencies {{ background: #feebc8; border-left: 4px solid #dd6b20; padding: 15px; margin: 20px 0; }}
        .deficiencies h3 {{ color: #c05621; margin-top: 0; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; color: #718096; font-size: 12px; }}
        @media print {{ body {{ margin: 0; }} .container {{ box-shadow: none; }} }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 CME Analysis Report</h1>
        
        <div class="header-info">
            <div><label>Plaintiff:</label> <span>{case['plaintiff_name']}</span></div>
            <div><label>Date of Birth:</label> <span>{case['date_of_birth']}</span></div>
            <div><label>Date of Injury:</label> <span>{case['date_of_injury']}</span></div>
            <div><label>Examining Doctor:</label> <span>{case['examining_doctor']}</span></div>
            <div><label>Analysis Date:</label> <span>{case['analysis_date']}</span></div>
            <div><label>Session ID:</label> <span>{case['session_id']}</span></div>
        </div>
        
        <h2>📊 Executive Summary</h2>
        <div class="summary-box">
            <div class="summary-item">
                <div class="number">{summary['total_tests_declared']}</div>
                <div class="label">Tests Declared</div>
            </div>
            <div class="summary-item">
                <div class="number performed">{summary['tests_properly_performed']}</div>
                <div class="label">Properly Performed</div>
            </div>
            <div class="summary-item">
                <div class="number inadequate">{summary['tests_inadequate']}</div>
                <div class="label">Inadequate</div>
            </div>
            <div class="summary-item">
                <div class="number not-observed">{summary['tests_not_observed']}</div>
                <div class="label">Not Observed</div>
            </div>
        </div>
        
        <p><strong>Performance Rate:</strong> {summary['performance_rate']}</p>
        <p><strong>Estimated Exam Duration:</strong> {summary['exam_duration_estimate']}</p>
        <p><strong>Estimated Hands-On Duration:</strong> {summary['hands_on_duration_estimate']}</p>
        
        {f'<div class="red-flags"><h3>⚠️ Red Flags</h3><ul>{red_flag_items}</ul></div>' if red_flag_items else ''}
        
        {f'<div class="deficiencies"><h3>📋 Examination Deficiencies</h3><ul>{deficiency_items}</ul></div>' if deficiency_items else ''}
        
        <h2>📝 Detailed Test Analysis</h2>
        <table>
            <thead>
                <tr>
                    <th>Test Name</th>
                    <th>Body Region</th>
                    <th>Status</th>
                    <th>Measurements?</th>
                    <th>Deficiencies</th>
                </tr>
            </thead>
            <tbody>
                {test_rows}
            </tbody>
        </table>
        
        <div class="footer">
            <p>Report generated by CME Analysis Platform | Session: {case['session_id']}</p>
            <p>Analysis powered by AWS Bedrock (Claude AI) | Standards: AMA Guides, Hirsch ROM Study, AAOS Guidelines</p>
        </div>
    </div>
</body>
</html>"""
        
        html_path = f"/Users/hammadhaque/Documents/cme-analysis-platform/cme_report_{self.session_id}.html"
        with open(html_path, 'w') as f:
            f.write(html)
        print(f"  ✓ HTML report: {html_path}")
        
        return html_path


def main():
    # Case information
    case_info = {
        'plaintiff_name': 'Cynthia Roberts',
        'dob': '6/14/1965',
        'doi': '9/6/2019',
        'examiner': 'Dr. Osborn'
    }
    
    # Video files
    video_files = [
        '/Users/hammadhaque/Downloads/CME - Video - Dr. Osborn.MP4',
        '/Users/hammadhaque/Downloads/CME - Video - Dr. Osborn 1.mp4',
        '/Users/hammadhaque/Downloads/CME - Video - Dr. Osborn 2.mp4'
    ]
    
    # Verify files exist
    existing_files = [f for f in video_files if os.path.exists(f)]
    if not existing_files:
        print("❌ No video files found!")
        sys.exit(1)
    
    print(f"Found {len(existing_files)} video files:")
    for f in existing_files:
        size = os.path.getsize(f) / (1024*1024)
        print(f"  • {os.path.basename(f)}: {size:.1f} MB")
    
    # Run analysis
    analyzer = CMEAnalyzer(case_info, existing_files)
    report = analyzer.run_full_analysis()
    
    print(f"\n{'='*60}")
    print("✅ ANALYSIS COMPLETE")
    print(f"{'='*60}")
    print(f"Total tests declared: {report['summary']['total_tests_declared']}")
    print(f"Properly performed: {report['summary']['tests_properly_performed']}")
    print(f"Inadequate: {report['summary']['tests_inadequate']}")
    print(f"Performance rate: {report['summary']['performance_rate']}")
    print(f"\nReport saved to: cme_report_{analyzer.session_id}.html")


if __name__ == '__main__':
    main()
