# CME Software - Technical Stack Explained

## 🎯 How All The Models Work Together

This document explains EXACTLY how each AI model is embedded in the code and what it does.

---

## 📊 THE COMPLETE STACK

```
┌─────────────────────────────────────────────────────┐
│  LAYER 1: Audio Analysis                           │
│  ├─ AWS Transcribe Medical (Speech-to-text)       │
│  └─ Location: cme_handler.py (start_transcription)│
└─────────────────────────────────────────────────────┘
         ↓ Produces transcript.json
┌─────────────────────────────────────────────────────┐
│  LAYER 2: Text/NLP Analysis                        │
│  ├─ Pattern Matching (Regex) - ALWAYS RUNS        │
│  ├─ Transformers AI (Emotion) - IF INSTALLED      │
│  └─ Location: cme_nlp_processor.py                 │
└─────────────────────────────────────────────────────┘
         ↓ Produces: commands, confusion, distress
┌─────────────────────────────────────────────────────┐
│  LAYER 3: Video Analysis                           │
│  ├─ AWS Rekognition (Objects) - ALWAYS RUNS       │
│  ├─ MediaPipe (Body Pose) - IF INSTALLED          │
│  └─ Location: cme_video_processor.py               │
└─────────────────────────────────────────────────────┘
         ↓ Produces: attention metrics, movements
┌─────────────────────────────────────────────────────┐
│  LAYER 4: Report Generation                        │
│  └─ Location: cme_report_generator.py              │
└─────────────────────────────────────────────────────┘
```

---

## 🔧 EACH MODEL EXPLAINED

### **1. AWS Transcribe Medical** (Always Active)

**File:** `cme_handler.py` lines 490-520  
**What it does:** Converts audio to text with speaker labels  
**Requires:** AWS credentials (already have)  
**Cost:** $0.024/minute ($1.44/hour)

```python
# Real code from cme_handler.py:
response = transcribe_client.start_medical_transcription_job(
    MedicalTranscriptionJobName=job_name,
    Media={'MediaFileUri': f"s3://{bucket}/{audio_key}"},
    OutputBucketName=bucket,
    LanguageCode='en-US',
    Specialty='PRIMARYCARE',
    Type='CONVERSATION',
    Settings={'ShowSpeakerLabels': True}
)
```

**Output Example:**
```json
{
  "results": {
    "speaker_labels": {
      "segments": [
        {
          "speaker_label": "speaker_0",
          "start_time": "125.5",
          "items": [{"content": "Please lift your leg"}]
        }
      ]
    }
  }
}
```

---

### **2. Pattern Matching** (Always Active)

**File:** `cme_nlp_processor.py` lines 435-473  
**What it does:** Regex pattern matching for commands, confusion, distress  
**Requires:** Nothing (built-in Python)  
**Cost:** $0 (runs in Lambda)

```python
# Real code from cme_nlp_processor.py:
DOCTOR_COMMAND_PATTERNS = [
    r'(?:please|now|go ahead and)\s+(?:lift|raise|move)',
    r'can you\s+(?:lift|raise|move)',
    # ... more patterns
]

# How it's used:
for pattern in DOCTOR_COMMAND_PATTERNS:
    if re.search(pattern, text_lower):
        commands.append({
            'timestamp': start_time,
            'command': segment_text,
            'requires_observation': True
        })
```

**This runs FIRST** - always catches basic patterns.

---

### **3. Transformers AI** (Optional - Better Emotion Detection)

**File:** `cme_nlp_processor.py` lines 14-26, 906-924  
**What it does:** AI emotion detection (sadness, fear, anger, etc.)  
**Requires:** `pip install transformers torch`  
**Cost:** $0 (runs in Lambda, uses model cache)  
**Better than:** Pattern matching alone

```python
# Real code from cme_nlp_processor.py:
try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
    emotion_classifier = pipeline(
        "text-classification",
        model="j-hartmann/emotion-english-distilroberta-base"
    )
except ImportError:
    TRANSFORMERS_AVAILABLE = False
```

**How it's used:**
```python
# In detect_patient_distress():
if TRANSFORMERS_AVAILABLE and emotion_classifier:
    emotions = emotion_classifier(segment_text)
    # Returns: [{'label': 'sadness', 'score': 0.92}, ...]
    
    for emotion in emotions[0]:
        if emotion['label'] in ['sadness', 'fear'] and emotion['score'] > 0.7:
            ai_distress_detected = True
```

**Fallback:** If Transformers not installed, uses pattern matching only.

---

### **4. AWS Rekognition** (Always Active)

**File:** `cme_video_processor.py` lines 913-934  
**What it does:** Detects objects in video frames (phone, computer, person)  
**Requires:** AWS credentials (already have)  
**Cost:** $0.001/image (~$1/hour video)

```python
# Real code from cme_video_processor.py:
response = rekognition_client.detect_labels(
    Image={'S3Object': {'Bucket': s3_bucket, 'Name': frame_key}},
    MaxLabels=50,
    MinConfidence=70
)

labels = [label['Name'].lower() for label in response['Labels']]

# Check for phone
if 'mobile phone' in labels:
    is_distracted = True
    distraction_type = 'phone_usage'
```

**Output Example:**
```python
labels = ['person', 'mobile phone', 'medical uniform', 'hand']
```

**This detects:** Phone, computer, clipboard, person presence

---

### **5. MediaPipe** (Optional - Body Movement Detection)

**File:** `cme_video_processor.py` lines 17-25, 1000-1088  
**What it does:** Detects body keypoints, calculates joint angles  
**Requires:** `pip install mediapipe opencv-python`  
**Cost:** $0 (runs locally/Lambda)  
**Better than:** Rekognition for body movements

```python
# Real code from cme_video_processor.py:
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
    mp_pose = mp.solutions.pose
except ImportError:
    MEDIAPIPE_AVAILABLE = False
```

**How it's used:**
```python
# In analyze_pose_with_mediapipe():
pose = mp_pose.Pose()
results = pose.process(frame)

if results.pose_landmarks:
    # Get actual body parts
    left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP]
    left_knee = landmarks[mp_pose.PoseLandmark.LEFT_KNEE]
    left_ankle = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE]
    
    # Calculate angle
    leg_angle = calculate_angle_from_landmarks(left_hip, left_knee, left_ankle)
    
    if leg_angle > 45:
        print("Leg raise detected! Angle:", leg_angle)
```

**Output Example:**
```python
{
    'movements_detected': [
        {
            'type': 'leg_raise',
            'timestamp': 125.7,
            'angle': 58.3,
            'confidence': 0.9
        }
    ]
}
```

**This detects:** Actual leg raises, arm movements, body positions, physical contact

**Fallback:** If MediaPipe not installed, uses Rekognition only.

---

## 🎯 HOW THEY WORK TOGETHER

### **Example: Detecting "Doctor on phone during leg raise test"**

```python
# Step 1: AWS Transcribe (ALWAYS)
transcript = "Doctor says: Please lift your leg"
timestamp = 125.5

# Step 2: Pattern Matching (ALWAYS)
command_detected = True  # Regex matched "please lift"

# Step 3: AWS Rekognition (ALWAYS)
rekognition_labels = ['person', 'mobile phone', 'hand']
phone_detected = True

# Step 4: MediaPipe (IF INSTALLED)
if MEDIAPIPE_AVAILABLE:
    leg_angle = 58.3  # Actual leg raised
    leg_raise_detected = True
else:
    leg_raise_detected = None  # Can't confirm

# Step 5: Correlation
result = {
    'doctor_command': "Please lift your leg",
    'timestamp': 125.5,
    'phone_detected': True,  # From Rekognition
    'leg_raise_detected': True,  # From MediaPipe
    'discrepancy': 'Doctor on phone while patient performed test'
}
```

---

## 💰 COST BREAKDOWN

| Service | Cost per 1-hour Video | Required? | Alternative |
|---------|----------------------|-----------|-------------|
| AWS Transcribe | $1.44 | ✅ Yes | Whisper (free, but harder) |
| AWS Rekognition | ~$1.00 | ✅ Yes | None (best for objects) |
| AWS Lambda | ~$0.10 | ✅ Yes | None (serverless) |
| S3 Storage | ~$0.05 | ✅ Yes | None (need storage) |
| **Transformers** | **$0.00** | ❌ No | Pattern matching |
| **MediaPipe** | **$0.00** | ❌ No | Rekognition only |

**Total with just AWS:** ~$2.60/video  
**Total with FREE upgrades:** ~$2.60/video (same!)

**Transformers and MediaPipe are FREE upgrades that make it better!**

---

## 🚀 INSTALLATION

### **Option 1: Basic (AWS Only)**
```bash
cd backend
pip install -r requirements.txt
```

Everything works, uses AWS only.

### **Option 2: Enhanced (Add FREE upgrades)**
```bash
cd backend
pip install -r requirements.txt
# Everything already included!
```

Your requirements.txt already has:
- ✅ `transformers==4.36.2`
- ✅ `mediapipe==0.10.9`
- ✅ `opencv-python-headless==4.9.0.80`

**You're already ready to use the enhanced features!**

---

## 🎯 WHICH MODEL DOES WHAT

### **Doctor Attention/Distraction:**
- **Rekognition**: Detects phone, computer, clipboard ✅
- **MediaPipe**: Not needed for this

### **Patient Crying/Distress:**
- **Pattern Matching**: Catches "it hurts", "crying" ✅
- **Transformers**: Better - detects emotional tone ⭐

### **Physical Contact:**
- **Rekognition**: Unreliable (can't tell touch from proximity)
- **MediaPipe**: Better - tracks hand positions ⭐

### **Medical Test Detection:**
- **Rekognition**: Detects "arm raised" (generic)
- **MediaPipe**: Detects "leg raised 58°" (precise!) ⭐

### **Test Timing:**
- **Pattern Matching**: Detects when doctor says test name ✅
- **MediaPipe**: Confirms when action actually happened ⭐

---

## 📋 DECISION TREE

```
START: Video uploaded
  ↓
AWS Transcribe → transcript.json
  ↓
Run Pattern Matching (ALWAYS)
  ├─ Detect commands
  ├─ Detect confusion
  └─ Detect distress patterns
  ↓
IF Transformers installed:
  └─ Enhance distress detection
  ↓
AWS Rekognition → analyze frames
  ├─ Detect phone
  ├─ Detect person presence
  └─ Calculate attention %
  ↓
IF MediaPipe installed:
  ├─ Detect body movements
  ├─ Calculate joint angles
  └─ Confirm physical contact
  ↓
Generate Report
```

---

## 🎯 BOTTOM LINE

**Current Code Uses:**
- ✅ AWS Transcribe Medical (always)
- ✅ Pattern Matching (always)
- ✅ AWS Rekognition (always)
- ⭐ Transformers (optional, if installed)
- ⭐ MediaPipe (optional, if installed)

**Your requirements.txt already has Transformers + MediaPipe!**

**So you're ALREADY using the enhanced version!** 🎉

**Cost:** ~$2.60 per video (AWS charges only)  
**Profit:** Charge $2,500-5,000 per case = 1,000x ROI

---

## 🔧 TESTING IF ENHANCEMENTS ARE ACTIVE

Add this to test script:

```python
import sys

# Check Transformers
try:
    from transformers import pipeline
    print("✅ Transformers available - Enhanced emotion detection ON")
except ImportError:
    print("❌ Transformers not available - Using pattern matching only")

# Check MediaPipe
try:
    import mediapipe as mp
    print("✅ MediaPipe available - Body tracking ON")
except ImportError:
    print("❌ MediaPipe not available - Using Rekognition only")
```

---

## 💡 WHEN TO UPGRADE TO PREMIUM

- **Revenue < $50K/month:** Stick with current stack
- **Revenue > $50K/month:** Add Twelve Labs ($5K/month)
- **High-value case > $1M:** Use Kinetisense for that case ($10K one-time)
- **Going to trial:** Add Tobii Pro gaze tracking ($5K)

**Don't upgrade until you're profitable!**

---

**Questions? Check the code:**
- Audio/NLP: `cme_nlp_processor.py`
- Video: `cme_video_processor.py`
- Reports: `cme_report_generator.py`
