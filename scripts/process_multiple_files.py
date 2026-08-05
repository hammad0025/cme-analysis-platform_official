#!/usr/bin/env python3
"""
Script to process multiple CME recording files for a single case (batch processing)
Usage: python3 process_multiple_files.py <file1> <file2> ... <fileN> [options]
       python3 process_multiple_files.py *.mp4 [options]  # Process all MP4 files in directory
"""

import sys
import os
import boto3
import json
import time
import requests
import glob
from pathlib import Path
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cme_api_auth import api_session

# API endpoint
API_BASE_URL = "https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod"
# Authenticated session for API calls. The presigned S3 upload below must
# keep using plain requests -- S3 rejects presigned URLs sent with an
# Authorization header.
api = api_session()

def create_session(patient_id: str, patient_name: str, doctor_name: str, state: str = "FL", exam_date: str = None, case_id: str = None, attorney_name: str = None):
    """Create a new CME session"""
    if not exam_date:
        exam_date = time.strftime('%Y-%m-%d')
    
    payload = {
        'patient_id': patient_id,
        'patient_name': patient_name,
        'doctor_name': doctor_name,
        'state': state,
        'exam_date': exam_date,
        'case_id': case_id or f"case_{int(time.time())}",
        'attorney_name': attorney_name or ''
    }
    
    print(f"\n📋 Creating CME session...")
    print(f"   Patient: {patient_name} ({patient_id})")
    print(f"   Doctor: {doctor_name}")
    print(f"   State: {state}")
    
    response = api.post(f"{API_BASE_URL}/cme/sessions", json=payload)
    
    if response.status_code == 201:
        data = response.json()
        session_id = data.get('session_id')
        print(f"✅ Session created: {session_id}")
        return session_id, data
    else:
        print(f"❌ Failed to create session: {response.status_code}")
        print(f"   {response.text}")
        return None, None

def upload_file(session_id: str, file_path: str):
    """Upload a single file to the session"""
    file_path_obj = Path(file_path)
    
    if not file_path_obj.exists():
        print(f"❌ File not found: {file_path}")
        return None
    
    filename = file_path_obj.name
    file_size = file_path_obj.stat().st_size
    
    # Determine content type
    ext = file_path_obj.suffix.lower()
    content_types = {
        '.mp4': 'video/mp4',
        '.mp3': 'audio/mp3',
        '.mpeg': 'video/mpeg',
        '.mpg': 'video/mpeg',
        '.wav': 'audio/wav',
        '.mov': 'video/quicktime',
        '.m4a': 'audio/mp4'
    }
    content_type = content_types.get(ext, 'video/mp4')
    
    print(f"\n📤 Uploading: {filename} ({file_size / 1024 / 1024:.2f} MB)...")
    
    # Get upload URL
    upload_payload = {
        'session_id': session_id,
        'filename': filename,
        'content_type': content_type,
        'file_size': file_size
    }
    
    response = api.post(f"{API_BASE_URL}/cme/upload", json=upload_payload)
    
    if response.status_code != 200:
        print(f"❌ Failed to get upload URL: {response.status_code}")
        print(f"   {response.text}")
        return None
    
    upload_data = response.json()
    upload_url = upload_data.get('upload_url')
    recording_index = upload_data.get('recording_index', 0)
    total_recordings = upload_data.get('total_recordings', 1)
    
    # Upload file
    with open(file_path, 'rb') as f:
        upload_response = requests.put(upload_url, data=f, headers={'Content-Type': content_type})
    
    if upload_response.status_code == 200:
        print(f"✅ Uploaded {filename} ({recording_index + 1}/{total_recordings})")
        return True
    else:
        print(f"❌ Failed to upload file: {upload_response.status_code}")
        return None

def start_processing(session_id: str):
    """Start processing the uploaded files"""
    print(f"\n🚀 Starting processing pipeline...")
    
    response = api.post(f"{API_BASE_URL}/cme/process", json={'session_id': session_id})
    
    if response.status_code == 200:
        data = response.json()
        recording_count = data.get('recording_count', 1)
        transcription_jobs = data.get('transcription_jobs', [])
        
        print(f"✅ Processing started!")
        print(f"   Recording count: {recording_count}")
        print(f"   Transcription jobs: {len(transcription_jobs)}")
        print(f"\n⏳ Processing will take 5-15 minutes per recording...")
        print(f"   Check status at: {API_BASE_URL}/cme/sessions/{session_id}")
        return True
    else:
        print(f"❌ Failed to start processing: {response.status_code}")
        print(f"   {response.text}")
        return False

def get_session_status(session_id: str):
    """Get current session status"""
    response = api.get(f"{API_BASE_URL}/cme/sessions/{session_id}")
    
    if response.status_code == 200:
        data = response.json()
        session = data.get('session', data)
        return session.get('status'), session.get('processing_stage')
    return None, None

def expand_file_patterns(file_args: List[str]) -> List[str]:
    """Expand glob patterns and return list of actual files"""
    expanded = []
    for arg in file_args:
        # Check if it's a glob pattern
        if '*' in arg or '?' in arg or '[' in arg:
            matched = glob.glob(arg)
            if matched:
                expanded.extend(matched)
            else:
                print(f"⚠️  No files matched pattern: {arg}")
        else:
            # Regular file path
            if os.path.exists(arg):
                expanded.append(arg)
            else:
                print(f"⚠️  File not found: {arg}")
    return expanded

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 process_multiple_files.py <file1> [file2] ... [fileN] [options]")
        print("       python3 process_multiple_files.py *.mp4 [options]  # Process all MP4 files")
        print("\nOptions:")
        print("  --patient-name NAME    Patient name")
        print("  --doctor-name NAME     Doctor/examiner name")
        print("  --state STATE          State (default: FL)")
        print("  --patient-id ID        Patient ID (default: auto-generated)")
        print("  --case-id ID           Case ID (default: auto-generated)")
        print("\nExamples:")
        print("  # Process 3 specific files:")
        print("  python3 process_multiple_files.py file1.mp4 file2.mp4 file3.mp4 \\")
        print("    --patient-name 'John Doe' --doctor-name 'Dr. Smith'")
        print("")
        print("  # Process all MP4 files in current directory:")
        print("  python3 process_multiple_files.py *.mp4 \\")
        print("    --patient-name 'John Doe' --doctor-name 'Dr. Smith'")
        sys.exit(1)
    
    # Parse arguments - separate files from options
    files = []
    patient_name = "Patient"
    doctor_name = "Dr. Examiner"
    state = "FL"
    patient_id = f"PT_{int(time.time())}"
    case_id = None
    
    # Parse arguments - collect files and options
    i = 1
    while i < len(sys.argv):
        if sys.argv[i].startswith('--'):
            # It's an option
            if sys.argv[i] == '--patient-name' and i + 1 < len(sys.argv):
                patient_name = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == '--doctor-name' and i + 1 < len(sys.argv):
                doctor_name = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == '--state' and i + 1 < len(sys.argv):
                state = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == '--patient-id' and i + 1 < len(sys.argv):
                patient_id = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == '--case-id' and i + 1 < len(sys.argv):
                case_id = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        else:
            # It's a file (or glob pattern)
            files.append(sys.argv[i])
            i += 1
    
    # Expand glob patterns
    files = expand_file_patterns(files)
    
    if not files:
        print("❌ No files found to process!")
        sys.exit(1)
    
    print("=" * 60)
    print("🎬 CME BATCH FILE ANALYSIS")
    print("=" * 60)
    print(f"\n📁 Files to process: {len(files)}")
    for i, f in enumerate(files, 1):
        file_size = os.path.getsize(f) / (1024 * 1024)  # MB
        print(f"   {i:2d}. {os.path.basename(f):50s} ({file_size:.2f} MB)")
    
    # Create session
    session_id, session_data = create_session(
        patient_id=patient_id,
        patient_name=patient_name,
        doctor_name=doctor_name,
        state=state,
        case_id=case_id
    )
    
    if not session_id:
        print("\n❌ Failed to create session. Exiting.")
        sys.exit(1)
    
    # Upload all files
    print(f"\n📤 Uploading {len(files)} files...")
    uploaded_count = 0
    
    for file_path in files:
        if upload_file(session_id, file_path):
            uploaded_count += 1
        time.sleep(1)  # Small delay between uploads
    
    if uploaded_count != len(files):
        print(f"\n⚠️  Only {uploaded_count}/{len(files)} files uploaded successfully")
        response = input("Continue with processing? (y/n): ")
        if response.lower() != 'y':
            print("Exiting.")
            sys.exit(1)
    
    # Start processing
    if start_processing(session_id):
        print(f"\n✅ All done!")
        print(f"\n📊 Session ID: {session_id}")
        print(f"   View session: {API_BASE_URL}/cme/sessions/{session_id}")
        print(f"   Generate report: {API_BASE_URL}/cme/sessions/{session_id}/report")
        print(f"\n💡 The analysis will run automatically. Check back in 10-20 minutes.")
    else:
        print("\n❌ Failed to start processing")
        sys.exit(1)

if __name__ == "__main__":
    main()

