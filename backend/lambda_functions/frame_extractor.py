"""
VIDEO FRAME EXTRACTOR FOR MAXIMUM ACCURACY ANALYSIS

Extracts frames from video at 1 frame/second for Claude Vision analysis.
This enables the AI to actually SEE what's happening in the video.

Pipeline:
1. Download video from S3
2. Extract frames using FFmpeg at 1fps
3. Encode frames to base64
4. Send to Claude Vision for analysis
"""

import boto3
import subprocess
import os
import base64
import json
import logging
import tempfile
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')


def extract_frames_from_video(
    video_path: str,
    output_dir: str,
    fps: float = 1.0,
    max_frames: int = 300,
    start_time: Optional[float] = None,
    duration: Optional[float] = None,
    quality: int = 2  # 1-31, lower is better quality
) -> List[str]:
    """
    Extract frames from video using FFmpeg.
    
    Args:
        video_path: Path to input video
        output_dir: Directory to save frames
        fps: Frames per second to extract (default: 1)
        max_frames: Maximum number of frames to extract
        start_time: Start time in seconds (optional)
        duration: Duration in seconds (optional)
        quality: JPEG quality (1-31, lower is better)
    
    Returns:
        List of paths to extracted frame images
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Build FFmpeg command
    cmd = ['ffmpeg', '-i', video_path]
    
    if start_time is not None:
        cmd.extend(['-ss', str(start_time)])
    
    if duration is not None:
        cmd.extend(['-t', str(duration)])
    
    cmd.extend([
        '-vf', f'fps={fps}',
        '-q:v', str(quality),
        '-frames:v', str(max_frames),
        os.path.join(output_dir, 'frame_%04d.jpg')
    ])
    
    logger.info(f"Running FFmpeg: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        logger.error(f"FFmpeg error: {result.stderr}")
        return []
    
    # Get list of extracted frames
    frames = sorted(Path(output_dir).glob('frame_*.jpg'))
    logger.info(f"Extracted {len(frames)} frames")
    
    return [str(f) for f in frames]


def frame_to_base64(frame_path: str) -> str:
    """
    Convert a frame image to base64 for Claude Vision.
    """
    with open(frame_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def extract_frames_for_exam_segment(
    video_s3_key: str,
    s3_bucket: str,
    exam_start_time: float,
    exam_duration: float = 120.0,  # 2 minutes around exam
    fps: float = 1.0
) -> List[Dict[str, Any]]:
    """
    Extract frames for a specific exam segment.
    
    Returns list of:
    [
        {'timestamp': 0.0, 'base64': '...', 'frame_number': 0},
        {'timestamp': 1.0, 'base64': '...', 'frame_number': 1},
        ...
    ]
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Download video
        local_video = os.path.join(temp_dir, 'video.mp4')
        logger.info(f"Downloading video from s3://{s3_bucket}/{video_s3_key}")
        s3_client.download_file(s3_bucket, video_s3_key, local_video)
        
        # Calculate extraction window
        start_time = max(0, exam_start_time - 30)  # 30 seconds before
        
        # Extract frames
        frames_dir = os.path.join(temp_dir, 'frames')
        frame_paths = extract_frames_from_video(
            video_path=local_video,
            output_dir=frames_dir,
            fps=fps,
            max_frames=int(exam_duration * fps),
            start_time=start_time,
            duration=exam_duration
        )
        
        # Convert to base64 with timestamps
        frames_data = []
        for i, frame_path in enumerate(frame_paths):
            frames_data.append({
                'timestamp': start_time + (i / fps),
                'base64': frame_to_base64(frame_path),
                'frame_number': i
            })
        
        logger.info(f"Prepared {len(frames_data)} frames for analysis")
        return frames_data


def extract_key_frames_smart(
    video_s3_key: str,
    s3_bucket: str,
    exam_timestamps: List[Dict[str, float]],  # [{'start': 100, 'end': 200}, ...]
    fps: float = 0.5  # Lower FPS for cost savings
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Smart frame extraction - only extract frames during exam periods.
    
    This is more cost-effective than extracting the entire video.
    """
    all_frames = {}
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Download video once
        local_video = os.path.join(temp_dir, 'video.mp4')
        logger.info(f"Downloading video from s3://{s3_bucket}/{video_s3_key}")
        s3_client.download_file(s3_bucket, video_s3_key, local_video)
        
        for i, exam_period in enumerate(exam_timestamps):
            start = exam_period.get('start', 0)
            end = exam_period.get('end', start + 60)
            duration = end - start
            exam_type = exam_period.get('exam_type', f'exam_{i}')
            
            frames_dir = os.path.join(temp_dir, f'frames_{i}')
            frame_paths = extract_frames_from_video(
                video_path=local_video,
                output_dir=frames_dir,
                fps=fps,
                start_time=start,
                duration=duration
            )
            
            frames_data = []
            for j, frame_path in enumerate(frame_paths):
                frames_data.append({
                    'timestamp': start + (j / fps),
                    'base64': frame_to_base64(frame_path),
                    'frame_number': j
                })
            
            all_frames[exam_type] = frames_data
            logger.info(f"Extracted {len(frames_data)} frames for {exam_type}")
    
    return all_frames


def upload_frames_to_s3(
    frames_data: List[Dict[str, Any]],
    s3_bucket: str,
    s3_prefix: str
) -> List[str]:
    """
    Upload extracted frames to S3 for evidence/review.
    """
    uploaded_keys = []
    
    for frame in frames_data:
        frame_key = f"{s3_prefix}/frame_{frame['frame_number']:04d}.jpg"
        
        # Decode base64 and upload
        image_data = base64.b64decode(frame['base64'])
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=frame_key,
            Body=image_data,
            ContentType='image/jpeg'
        )
        
        uploaded_keys.append(frame_key)
    
    logger.info(f"Uploaded {len(uploaded_keys)} frames to s3://{s3_bucket}/{s3_prefix}/")
    return uploaded_keys


def handler(event, context):
    """
    Lambda handler for frame extraction.
    
    Input:
    {
        "video_s3_key": "path/to/video.mp4",
        "s3_bucket": "bucket-name",
        "exam_start_time": 100.0,
        "exam_duration": 120.0,
        "fps": 1.0,
        "upload_frames": true/false
    }
    
    Output:
    {
        "frames": [{"timestamp": ..., "base64": ..., "frame_number": ...}, ...],
        "uploaded_keys": ["s3/key1.jpg", ...]
    }
    """
    try:
        video_s3_key = event.get('video_s3_key')
        s3_bucket = event.get('s3_bucket', os.environ.get('S3_BUCKET', 'eve-legal-documents'))
        exam_start_time = event.get('exam_start_time', 0)
        exam_duration = event.get('exam_duration', 120)
        fps = event.get('fps', 1.0)
        upload_frames = event.get('upload_frames', False)
        session_id = event.get('session_id', 'unknown')
        
        # Extract frames
        frames_data = extract_frames_for_exam_segment(
            video_s3_key=video_s3_key,
            s3_bucket=s3_bucket,
            exam_start_time=exam_start_time,
            exam_duration=exam_duration,
            fps=fps
        )
        
        result = {
            'statusCode': 200,
            'frames_count': len(frames_data),
            'frames': frames_data
        }
        
        # Optionally upload to S3 for evidence
        if upload_frames:
            s3_prefix = f"cme-frames/{session_id}"
            uploaded_keys = upload_frames_to_s3(frames_data, s3_bucket, s3_prefix)
            result['uploaded_keys'] = uploaded_keys
        
        return result
        
    except Exception as e:
        logger.error(f"Frame extraction error: {e}")
        import traceback
        return {
            'statusCode': 500,
            'error': str(e),
            'traceback': traceback.format_exc()
        }


if __name__ == '__main__':
    # Test locally
    print("Frame extractor module loaded")
    print("Use extract_frames_for_exam_segment() to extract frames from a video")

