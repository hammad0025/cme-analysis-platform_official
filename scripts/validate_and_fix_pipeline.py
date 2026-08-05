#!/usr/bin/env python3
"""
PRODUCTION-GRADE PIPELINE VALIDATION AND FIX
Validates entire pipeline end-to-end and fixes any issues
"""

import boto3
import json
import time
from decimal import Decimal
from typing import Dict, List, Any

SESSION_ID = 'cme_7285456d8748'
REGION = 'us-east-1'

class PipelineValidator:
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb', region_name=REGION)
        self.lambda_client = boto3.client('lambda', region_name=REGION)
        self.s3_client = boto3.client('s3', region_name=REGION)
        
    def validate_nlp_output(self, session_id: str) -> Dict[str, Any]:
        """Validate NLP processor output has declared_step_id"""
        print("\n1️⃣ VALIDATING NLP OUTPUT...")
        
        steps_table = self.dynamodb.Table('cme-declared-steps')
        response = steps_table.scan(
            FilterExpression='session_id = :sid',
            ExpressionAttributeValues={':sid': session_id}
        )
        
        steps = response.get('Items', [])
        issues = []
        
        for step in steps:
            if not step.get('declared_step_id'):
                issues.append(f"Step missing declared_step_id: {step}")
            if not step.get('label'):
                issues.append(f"Step missing label: {step}")
            if not step.get('timestamp'):
                issues.append(f"Step missing timestamp: {step}")
        
        if issues:
            print(f"   ❌ Found {len(issues)} issues")
            for issue in issues[:5]:
                print(f"      - {issue}")
            return {'valid': False, 'issues': issues, 'steps': steps}
        
        print(f"   ✅ All {len(steps)} steps have required fields")
        return {'valid': True, 'steps': steps}
    
    def validate_video_analysis(self, session_id: str) -> Dict[str, Any]:
        """Validate video analysis results are linked properly"""
        print("\n2️⃣ VALIDATING VIDEO ANALYSIS...")
        
        steps_table = self.dynamodb.Table('cme-declared-steps')
        actions_table = self.dynamodb.Table('cme-observed-actions')
        
        # Get all steps
        steps_response = steps_table.scan(
            FilterExpression='session_id = :sid',
            ExpressionAttributeValues={':sid': session_id}
        )
        steps = steps_response.get('Items', [])
        
        # Get all actions
        actions_response = actions_table.scan()
        all_actions = actions_response.get('Items', [])
        
        # Build mapping
        step_ids = {step['declared_step_id'] for step in steps}
        action_step_ids = {action.get('declared_step_id') for action in all_actions if action.get('declared_step_id')}
        
        linked = step_ids & action_step_ids
        missing = step_ids - action_step_ids
        
        print(f"   Steps: {len(steps)}")
        print(f"   Actions: {len(all_actions)}")
        print(f"   Linked: {len(linked)}")
        print(f"   Missing video analysis: {len(missing)}")
        
        if missing:
            print(f"   ⚠️  {len(missing)} steps need video analysis")
            return {'valid': False, 'missing': list(missing), 'steps': steps}
        
        print(f"   ✅ All steps have video analysis")
        return {'valid': True, 'steps': steps, 'actions': all_actions}
    
    def validate_sentiment_analysis(self, session_id: str) -> Dict[str, Any]:
        """Validate sentiment analysis is working"""
        print("\n3️⃣ VALIDATING SENTIMENT ANALYSIS...")
        
        demeanor_table = self.dynamodb.Table('cme-demeanor-flags')
        response = demeanor_table.scan(
            FilterExpression='session_id = :sid',
            ExpressionAttributeValues={':sid': session_id}
        )
        
        flags = response.get('Items', [])
        
        if not flags:
            print(f"   ⚠️  No demeanor flags found")
            return {'valid': False, 'flags': []}
        
        flag_types = {}
        for flag in flags:
            flag_type = flag.get('flag_type', 'unknown')
            flag_types[flag_type] = flag_types.get(flag_type, 0) + 1
        
        print(f"   ✅ Found {len(flags)} demeanor flags")
        for flag_type, count in flag_types.items():
            print(f"      - {flag_type}: {count}")
        
        return {'valid': True, 'flags': flags}
    
    def fix_missing_video_analysis(self, session_id: str, missing_step_ids: List[str]):
        """Process video analysis for missing steps"""
        print(f"\n🔧 FIXING {len(missing_step_ids)} MISSING VIDEO ANALYSES...")
        
        steps_table = self.dynamodb.Table('cme-declared-steps')
        sessions_table = self.dynamodb.Table('cme-sessions')
        
        # Get session to find video
        session_response = sessions_table.get_item(Key={'session_id': session_id})
        session = session_response.get('Item', {})
        
        # Get video S3 key
        video_uri = session.get('video_uri', '')
        if video_uri.startswith('s3://'):
            parts = video_uri.replace('s3://', '').split('/', 1)
            s3_bucket = parts[0]
            video_s3_key = parts[1] if len(parts) > 1 else ''
        else:
            recordings = session.get('recordings', [])
            if recordings:
                uri = recordings[0].get('uri', recordings[0].get('s3_key', ''))
                if uri.startswith('s3://'):
                    parts = uri.replace('s3://', '').split('/', 1)
                    s3_bucket = parts[0]
                    video_s3_key = parts[1] if len(parts) > 1 else ''
                else:
                    print("   ❌ Could not find video")
                    return
            else:
                print("   ❌ Could not find video")
                return
        
        print(f"   Video: s3://{s3_bucket}/{video_s3_key}")
        
        # Process each missing step
        processed = 0
        for step_id in missing_step_ids[:10]:  # Limit to 10 at a time
            try:
                # Get step details
                step_response = steps_table.get_item(Key={'declared_step_id': step_id})
                step = step_response.get('Item', {})
                
                if not step:
                    continue
                
                test_label = step.get('label', 'unknown')
                test_timestamp = float(step.get('timestamp', 0))
                
                print(f"   Processing: {test_label}...", end=' ')
                
                # Prepare payload
                payload = {
                    'session_id': session_id,
                    'declared_test': {
                        'declared_step_id': step_id,
                        'label': test_label,
                        'timestamp': test_timestamp,
                        'transcript_text': step.get('transcript_text', '')
                    },
                    'video_s3_key': video_s3_key
                }
                
                # Invoke video processor
                response = self.lambda_client.invoke(
                    FunctionName='cme-video-processor',
                    InvocationType='RequestResponse',
                    Payload=json.dumps(payload)
                )
                
                result = json.loads(response['Payload'].read().decode('utf-8'))
                
                if result.get('statusCode') == 200:
                    motion = result.get('motion_present', 'unknown')
                    print(f"✅ {motion}")
                    processed += 1
                else:
                    print(f"❌ {result.get('error', 'Unknown')}")
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                print(f"❌ Exception: {e}")
        
        print(f"\n   ✅ Processed {processed}/{len(missing_step_ids)}")
    
    def regenerate_report(self, session_id: str) -> str:
        """Regenerate report"""
        print("\n4️⃣ REGENERATING REPORT...")
        
        try:
            response = self.lambda_client.invoke(
                FunctionName='cme-report-generator',
                InvocationType='RequestResponse',
                Payload=json.dumps({
                    'session_id': session_id,
                    'format': 'html'
                })
            )
            
            result = json.loads(response['Payload'].read().decode('utf-8'))
            
            if result.get('statusCode') == 200:
                report_key = result.get('report_key', '')
                print(f"   ✅ Report generated: {report_key}")
                return report_key
            else:
                print(f"   ❌ Error: {result.get('error', 'Unknown')}")
                return None
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return None
    
    def run_full_validation(self, session_id: str):
        """Run complete pipeline validation"""
        print("="*60)
        print("🔍 PRODUCTION PIPELINE VALIDATION")
        print("="*60)
        print(f"\nSession ID: {session_id}\n")
        
        # Step 1: Validate NLP
        nlp_result = self.validate_nlp_output(session_id)
        if not nlp_result['valid']:
            print("\n❌ NLP validation failed - fix NLP processor first")
            return
        
        # Step 2: Validate Video Analysis
        video_result = self.validate_video_analysis(session_id)
        
        # Step 3: Fix missing video analysis
        if not video_result['valid'] and video_result.get('missing'):
            self.fix_missing_video_analysis(session_id, video_result['missing'])
            # Re-validate
            video_result = self.validate_video_analysis(session_id)
        
        # Step 4: Validate Sentiment
        sentiment_result = self.validate_sentiment_analysis(session_id)
        
        # Step 5: Regenerate Report
        report_key = self.regenerate_report(session_id)
        
        # Summary
        print("\n" + "="*60)
        print("📊 VALIDATION SUMMARY")
        print("="*60)
        print(f"✅ NLP Output: {'PASS' if nlp_result['valid'] else 'FAIL'}")
        print(f"✅ Video Analysis: {'PASS' if video_result['valid'] else 'FAIL'}")
        print(f"✅ Sentiment Analysis: {'PASS' if sentiment_result['valid'] else 'WARN'}")
        print(f"✅ Report Generated: {'PASS' if report_key else 'FAIL'}")
        
        if all([nlp_result['valid'], video_result['valid'], report_key]):
            print("\n🎉 PIPELINE IS PRODUCTION-READY!")
        else:
            print("\n⚠️  PIPELINE NEEDS FIXES")

if __name__ == "__main__":
    validator = PipelineValidator()
    validator.run_full_validation(SESSION_ID)

