"""
CME Video Processor - Video Segmentation and Visual Action Analysis
Implements Steps 5 & 6 from the technical documentation
"""

import json
import boto3
import logging
from typing import Dict, Any, List, Optional, Tuple
import subprocess
import os
import tempfile
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
rekognition_client = boto3.client('rekognition')

# Expected motion patterns for different test types
TEST_MOTION_EXPECTATIONS = {
    'lumbar_rom': {
        'expected_movements': ['forward_bend', 'backward_bend', 'lateral_bend', 'rotation'],
        'patient_motion_required': True,
        'examiner_touch': False,
        'description': 'Patient should bend forward, backward, and side-to-side'
    },
    'straight_leg_raise': {
        'expected_movements': ['leg_raise', 'hip_flexion'],
        'patient_motion_required': True,
        'examiner_touch': True,
        'description': 'Examiner raises patient\'s leg while patient lies supine'
    },
    'cervical_rom': {
        'expected_movements': ['head_rotation', 'head_flexion', 'head_extension'],
        'patient_motion_required': True,
        'examiner_touch': False,
        'description': 'Patient rotates and flexes neck in various directions'
    },
    'gait': {
        'expected_movements': ['walking', 'heel_to_toe', 'standing'],
        'patient_motion_required': True,
        'examiner_touch': False,
        'description': 'Patient walks normally and performs heel-to-toe walking'
    },
    'neurological': {
        'expected_movements': ['limb_movement', 'reflex_test'],
        'patient_motion_required': False,
        'examiner_touch': True,
        'description': 'Examiner tests reflexes using reflex hammer'
    },
    'palpation': {
        'expected_movements': ['examiner_hand_movement'],
        'patient_motion_required': False,
        'examiner_touch': True,
        'description': 'Examiner presses along spine or affected area'
    },
    'spine': {
        'expected_movements': ['examiner_hand_movement', 'visual_inspection'],
        'patient_motion_required': False,
        'examiner_touch': True,
        'description': 'Examiner inspects and palpates spine'
    }
}


class CMEVideoProcessor:
    """Process CME video recordings for action analysis"""
    
    def __init__(self, s3_bucket: str):
        self.s3_bucket = s3_bucket
        self.temp_dir = tempfile.gettempdir()
    
    def extract_video_segment(
        self,
        video_s3_key: str,
        start_time: float,
        duration: float = 60.0,
        output_key_prefix: str = 'cme-segments'
    ) -> Optional[str]:
        """
        Step 5: Video Segment Extraction
        Extract a video segment around a declared test timestamp
        
        Args:
            video_s3_key: S3 key of the full video
            start_time: Start timestamp in seconds
            duration: Duration to extract (default 60 seconds: ±30s around declaration)
            output_key_prefix: S3 prefix for output segments
            
        Returns:
            S3 key of extracted segment
        """
        try:
            # Calculate extraction window (30 seconds before, 30 seconds after)
            extract_start = max(0, start_time - 30)
            
            # Generate output filename
            segment_id = f"segment_{int(start_time)}_{int(duration)}"
            local_input = os.path.join(self.temp_dir, 'input_video.mp4')
            local_output = os.path.join(self.temp_dir, f'{segment_id}.mp4')
            output_s3_key = f"{output_key_prefix}/{segment_id}.mp4"
            
            # Download video from S3
            logger.info(f"Downloading video from s3://{self.s3_bucket}/{video_s3_key}")
            s3_client.download_file(self.s3_bucket, video_s3_key, local_input)
            
            # Extract segment using FFmpeg
            # Note: In production Lambda, you'd include FFmpeg layer or use MediaConvert
            command = [
                'ffmpeg',
                '-i', local_input,
                '-ss', str(extract_start),
                '-t', str(duration),
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-y',  # Overwrite output
                local_output
            ]
            
            logger.info(f"Extracting segment: start={extract_start}s, duration={duration}s")
            
            # For Lambda, you'd need to check if ffmpeg is available
            if os.path.exists('/usr/bin/ffmpeg') or os.path.exists('/opt/bin/ffmpeg'):
                result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                if result.returncode != 0:
                    logger.error(f"FFmpeg error: {result.stderr}")
                    return None
                
                # Upload segment to S3
                s3_client.upload_file(local_output, self.s3_bucket, output_s3_key)
                logger.info(f"Uploaded segment to s3://{self.s3_bucket}/{output_s3_key}")
                
                # Cleanup
                os.remove(local_input)
                os.remove(local_output)
                
                return output_s3_key
            else:
                # Fallback: Use AWS MediaConvert or Elemental for video processing
                logger.warning("FFmpeg not available, using MediaConvert fallback")
                return self._extract_segment_with_mediaconvert(
                    video_s3_key, extract_start, duration, output_s3_key
                )
            
        except Exception as e:
            logger.error(f"Error extracting video segment: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _extract_segment_with_mediaconvert(
        self,
        input_key: str,
        start_time: float,
        duration: float,
        output_key: str
    ) -> Optional[str]:
        """Fallback method using AWS MediaConvert for video segmentation"""
        try:
            # In production, implement AWS Elemental MediaConvert job
            # This would create a job to extract the segment
            logger.info(f"MediaConvert extraction not yet implemented")
            return None
        except Exception as e:
            logger.error(f"MediaConvert error: {str(e)}")
            return None
    
    def analyze_video_segment(
        self,
        segment_s3_key: str,
        test_type: str
    ) -> Dict[str, Any]:
        """
        Step 6: Visual Action Analysis
        Analyze video segment for motion and actions using computer vision
        
        Args:
            segment_s3_key: S3 key of video segment
            test_type: Type of medical test (e.g., 'lumbar_rom', 'gait')
            
        Returns:
            Analysis results with motion detection and pose estimation
        """
        try:
            # Get expected movements for this test type
            expectations = TEST_MOTION_EXPECTATIONS.get(test_type, {})
            
            # Analyze video using AWS Rekognition
            motion_analysis = self._analyze_motion_rekognition(segment_s3_key)
            
            # Detect people and poses
            pose_analysis = self._detect_poses_rekognition(segment_s3_key)
            
            # Compare observed actions against expectations
            comparison = self._compare_with_expectations(
                motion_analysis,
                pose_analysis,
                expectations
            )
            
            return {
                'segment_key': segment_s3_key,
                'test_type': test_type,
                'motion_detected': motion_analysis,
                'poses_detected': pose_analysis,
                'comparison': comparison,
                'expectations': expectations
            }
            
        except Exception as e:
            logger.error(f"Error analyzing video segment: {str(e)}")
            return {
                'error': str(e),
                'segment_key': segment_s3_key,
                'test_type': test_type
            }
    
    def _analyze_motion_rekognition(self, video_s3_key: str) -> Dict[str, Any]:
        """Use AWS Rekognition to detect motion in video segment"""
        try:
            # Start video analysis job
            response = rekognition_client.start_label_detection(
                Video={
                    'S3Object': {
                        'Bucket': self.s3_bucket,
                        'Name': video_s3_key
                    }
                },
                MinConfidence=60.0,
                Features=['GENERAL_LABELS']
            )
            
            job_id = response['JobId']
            logger.info(f"Started Rekognition label detection: {job_id}")
            
            # Wait for job completion (in production, use async processing)
            # For now, return job ID for async polling
            return {
                'job_id': job_id,
                'status': 'IN_PROGRESS',
                'type': 'motion_analysis'
            }
            
        except Exception as e:
            logger.error(f"Rekognition motion analysis error: {str(e)}")
            return {'error': str(e)}
    
    def _detect_poses_rekognition(self, video_s3_key: str) -> Dict[str, Any]:
        """Use AWS Rekognition to detect people and body poses"""
        try:
            # Start person tracking
            response = rekognition_client.start_person_tracking(
                Video={
                    'S3Object': {
                        'Bucket': self.s3_bucket,
                        'Name': video_s3_key
                    }
                }
            )
            
            job_id = response['JobId']
            logger.info(f"Started Rekognition person tracking: {job_id}")
            
            return {
                'job_id': job_id,
                'status': 'IN_PROGRESS',
                'type': 'pose_detection'
            }
            
        except Exception as e:
            logger.error(f"Rekognition pose detection error: {str(e)}")
            return {'error': str(e)}
    
    def _compare_with_expectations(
        self,
        motion_analysis: Dict[str, Any],
        pose_analysis: Dict[str, Any],
        expectations: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compare observed motion/poses with expected test actions"""
        
        # This would be more sophisticated in production
        # For now, return a basic comparison structure
        
        motion_present = 'unknown'
        pose_match = 'unknown'
        confidence = 0.5
        
        # Check if analysis jobs are complete
        if motion_analysis.get('status') == 'COMPLETED' and pose_analysis.get('status') == 'COMPLETED':
            # In production, analyze the detailed results
            motion_present = 'performed'  # or 'brief' or 'not_observed'
            pose_match = 'full_match'  # or 'partial' or 'no_match'
            confidence = 0.75
        
        return {
            'motion_present': motion_present,
            'pose_match': pose_match,
            'confidence_score': confidence,
            'expected_movements': expectations.get('expected_movements', []),
            'patient_motion_required': expectations.get('patient_motion_required', False),
            'examiner_touch_required': expectations.get('examiner_touch', False),
            'analysis_status': 'pending' if motion_analysis.get('status') == 'IN_PROGRESS' else 'completed'
        }
    
    def get_rekognition_results(self, job_id: str, job_type: str) -> Dict[str, Any]:
        """Poll Rekognition job results"""
        try:
            if job_type == 'motion_analysis':
                response = rekognition_client.get_label_detection(JobId=job_id)
            elif job_type == 'pose_detection':
                response = rekognition_client.get_person_tracking(JobId=job_id)
            else:
                return {'error': 'Unknown job type'}
            
            job_status = response.get('JobStatus')
            
            if job_status == 'SUCCEEDED':
                return {
                    'status': 'COMPLETED',
                    'results': response,
                    'job_type': job_type
                }
            elif job_status == 'IN_PROGRESS':
                return {
                    'status': 'IN_PROGRESS',
                    'job_type': job_type
                }
            else:
                return {
                    'status': 'FAILED',
                    'error': response.get('StatusMessage', 'Unknown error'),
                    'job_type': job_type
                }
                
        except Exception as e:
            logger.error(f"Error getting Rekognition results: {str(e)}")
            return {'error': str(e)}


class PoseEstimationEngine:
    """
    Advanced pose estimation using MediaPipe or OpenPose
    This would be deployed as a separate service or Lambda with custom container
    """
    
    @staticmethod
    def estimate_poses_mediapipe(video_frames: List[Any]) -> List[Dict[str, Any]]:
        """
        Use MediaPipe Pose to extract skeletal keypoints
        
        In production, this would:
        1. Load video frames
        2. Run MediaPipe Pose on each frame
        3. Extract 33 body keypoints per person
        4. Track motion patterns
        5. Classify movements (bending, raising leg, etc.)
        """
        try:
            # This is a placeholder - real implementation would use:
            # import mediapipe as mp
            # mp_pose = mp.solutions.pose
            # pose = mp_pose.Pose()
            
            logger.info("MediaPipe pose estimation not yet implemented")
            
            # Return mock structure
            return [{
                'frame': 0,
                'timestamp': 0.0,
                'persons': [{
                    'person_id': 0,
                    'keypoints': {},  # Would contain 33 keypoint coordinates
                    'pose_landmarks': [],
                    'visibility': []
                }]
            }]
            
        except Exception as e:
            logger.error(f"MediaPipe pose estimation error: {str(e)}")
            return []
    
    @staticmethod
    def analyze_motion_patterns(pose_sequence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze sequence of poses to detect specific movements
        
        Returns:
            Classification of observed movements with confidence scores
        """
        movements_detected = {
            'forward_bend': False,
            'leg_raise': False,
            'walking': False,
            'examiner_touch': False,
            'patient_response': False
        }
        
        # In production, analyze pose keypoint sequences to detect:
        # - Trunk flexion/extension
        # - Limb movements
        # - Gait patterns
        # - Examiner-patient interactions
        
        return {
            'movements': movements_detected,
            'confidence': 0.0,
            'frames_analyzed': len(pose_sequence)
        }


def process_video_for_cme_test(
    session_id: str,
    declared_test: Dict[str, Any],
    video_s3_key: str,
    s3_bucket: str
) -> Dict[str, Any]:
    """
    Main processing function for video analysis of a declared test
    Combines video segmentation and action analysis
    """
    processor = CMEVideoProcessor(s3_bucket)
    
    test_timestamp = float(declared_test.get('timestamp', 0))
    test_type = declared_test.get('label', 'unknown')
    
    # Step 5: Extract video segment
    segment_key = processor.extract_video_segment(
        video_s3_key=video_s3_key,
        start_time=test_timestamp,
        duration=60.0,
        output_key_prefix=f'cme-segments/{session_id}'
    )
    
    if not segment_key:
        return {
            'error': 'Failed to extract video segment',
            'test_type': test_type,
            'timestamp': test_timestamp
        }
    
    # Step 6: Analyze the segment
    analysis = processor.analyze_video_segment(segment_key, test_type)
    
    return {
        'session_id': session_id,
        'test_type': test_type,
        'timestamp': test_timestamp,
        'segment_key': segment_key,
        'analysis': analysis,
        'status': 'completed'
    }


def generate_frame_snapshots(
    video_s3_key: str,
    timestamps: List[float],
    s3_bucket: str,
    output_prefix: str = 'cme-frames'
) -> List[str]:
    """
    Extract still frame images at specific timestamps for report inclusion
    
    Returns:
        List of S3 keys for extracted frames
    """
    frame_keys = []
    
    try:
        temp_dir = tempfile.gettempdir()
        local_video = os.path.join(temp_dir, 'video_for_frames.mp4')
        
        # Download video
        s3_client.download_file(s3_bucket, video_s3_key, local_video)
        
        for i, timestamp in enumerate(timestamps):
            frame_filename = f'frame_{i}_{int(timestamp)}.jpg'
            local_frame = os.path.join(temp_dir, frame_filename)
            output_key = f"{output_prefix}/{frame_filename}"
            
            # Extract frame using FFmpeg
            if os.path.exists('/usr/bin/ffmpeg'):
                command = [
                    'ffmpeg',
                    '-i', local_video,
                    '-ss', str(timestamp),
                    '-frames:v', '1',
                    '-q:v', '2',
                    '-y',
                    local_frame
                ]
                
                subprocess.run(command, capture_output=True, timeout=30)
                
                if os.path.exists(local_frame):
                    s3_client.upload_file(local_frame, s3_bucket, output_key)
                    frame_keys.append(output_key)
                    os.remove(local_frame)
        
        # Cleanup
        if os.path.exists(local_video):
            os.remove(local_video)
        
        return frame_keys
        
    except Exception as e:
        logger.error(f"Error generating frame snapshots: {str(e)}")
        return []

