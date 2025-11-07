# CME Analysis Platform

## AI-Based CME Analysis Platform (Florida Happy Path)

An AI-powered platform for analyzing Compulsory Medical Examination (CME) recordings to detect discrepancies between declared tests and observed actions, and to flag unprofessional examiner demeanor.

### 🎯 Purpose

This platform empowers plaintiff attorneys like Dorothy Clay Sims, Dr. Oregon Hunter, and Tim Felice to challenge biased CMEs by providing:

- **Automated Test Detection**: Identifies when examiners claim to perform tests
- **Visual Action Analysis**: Uses computer vision to verify if tests were actually performed
- **Demeanor Analysis**: Flags negative tone, interruptions, and dismissive behavior
- **Comprehensive Reports**: Generates structured reports with evidence and timestamps

### ⚖️ Legal Basis

**Florida**: Under Florida Rules of Civil Procedure Rule 1.360, the injured party has the right to record CMEs with audio and video. The 19th Judicial Circuit guidelines confirm that plaintiff's counsel, a videographer, and a court reporter may attend and record the examination.

**State-Aware**: The platform includes logic to handle different jurisdictions:
- **Florida, California**: Full video + audio recording
- **Pennsylvania**: Audio-only recording  
- **Texas**: Ephemeral mode (no storage of raw media)

### 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CME Analysis Platform                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  Session     │    │  Recording   │    │  Processing  │  │
│  │  Setup       │───▶│  Ingestion   │───▶│  Pipeline    │  │
│  │  & Consent   │    │  (S3)        │    │  (Step Fn)   │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  Speech-to   │    │  Test Intent │    │  Video       │  │
│  │  Text        │───▶│  Detection   │───▶│  Segmentation│  │
│  │  (Transcribe)│    │  (NLP)       │    │  (FFmpeg)    │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  Visual      │    │  Demeanor    │    │  Report      │  │
│  │  Action      │───▶│  Analysis    │───▶│  Generation  │  │
│  │  (CV)        │    │  (Sentiment) │    │  (PDF/HTML)  │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 🚀 Features

#### Core Workflow (8 Steps)

1. **Session Setup & Consent** - State-aware recording permissions, digital consent forms
2. **Data Ingestion & Storage** - Secure S3 storage with encryption
3. **Speech-to-Text & Diarization** - AWS Transcribe Medical with speaker labels
4. **Test Intent Detection** - NLP to identify declared medical tests
5. **Video Segmentation** - Extract clips around test timestamps  
6. **Visual Action Analysis** - Computer vision (pose estimation, motion detection)
7. **Demeanor & Tone Analysis** - Sentiment analysis and interruption detection
8. **Report Generation** - Structured PDF/HTML reports with evidence

#### Medical Test Taxonomy

The system can detect declarations of:
- Lumbar ROM (range of motion)
- Straight Leg Raise (SLR)
- Cervical ROM
- Gait analysis
- Neurological tests (reflexes, sensation)
- Palpation
- Waddell's signs
- Orthopedic assessments
- Cognitive tests

### 📁 Project Structure

```
cme-analysis-platform/
├── backend/
│   └── lambda_functions/
│       ├── cme_handler.py              # Session management, consent, upload
│       ├── cme_nlp_processor.py        # Test detection, demeanor analysis
│       ├── cme_video_processor.py      # Video segmentation, CV analysis
│       ├── cme_report_generator.py     # Report generation
│       └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/                 # React components
│       ├── pages/
│       │   ├── CMEAnalysis.js         # Main CME dashboard
│       │   ├── CMESessionDetail.js    # Session detail view
│       │   └── CMEReportView.js       # Report viewer
│       └── services/
│           └── cmeApi.js              # API service
├── infrastructure/
│   ├── cdk_stack.py                   # AWS CDK infrastructure
│   ├── dynamodb_tables.py             # DynamoDB table definitions
│   └── requirements.txt
├── docs/
│   ├── TECHNICAL_DOCUMENTATION.md     # Full technical spec
│   └── API.md                         # API reference
└── README.md
```

### 🔧 Technology Stack

**Backend:**
- AWS Lambda (Python 3.12)
- AWS Transcribe Medical
- AWS Rekognition / Custom CV models
- AWS Comprehend (sentiment analysis)
- AWS Bedrock (Claude for NLP)
- Amazon S3 (encrypted storage)
- DynamoDB (metadata)
- AWS Step Functions (orchestration)

**Frontend:**
- React 18
- Tailwind CSS
- React Router
- Axios

**Infrastructure:**
- AWS CDK (Infrastructure as Code)
- CloudWatch (logging & monitoring)
- API Gateway

### 📊 Data Models

**ExamSession**: Session metadata, state, recording mode
**DeclaredStep**: Detected test declarations with timestamps
**ObservedAction**: Visual analysis results for each test
**DemeanorFlag**: Tone/behavior issues with severity
**ConsentRecord**: Digital consent signatures

### 🚀 Quick Start

#### Prerequisites
- AWS Account with Bedrock, Transcribe, and Rekognition access
- Python 3.12+
- Node.js 18+
- AWS CLI configured

#### Backend Setup
```bash
cd backend
pip install -r requirements.txt
```

#### Frontend Setup
```bash
cd frontend
npm install
npm start
```

#### Infrastructure Deployment
```bash
cd infrastructure
pip install -r requirements.txt
cdk bootstrap
cdk deploy
```

### 📘 API Endpoints

**Sessions:**
- `POST /cme/sessions` - Create new CME session
- `GET /cme/sessions` - List all sessions
- `GET /cme/sessions/{id}` - Get session details
- `GET /cme/sessions/{id}/report` - Generate report

**Recording:**
- `POST /cme/upload` - Get presigned URL for recording upload
- `POST /cme/process` - Start processing pipeline

**Consent:**
- `POST /cme/consent` - Submit digital consent

### 🔒 Security & Compliance

- **Encryption**: All data encrypted at rest (S3) and in transit (TLS)
- **HIPAA Ready**: Uses HIPAA-eligible AWS services
- **Work Product Privilege**: Recordings belong to plaintiff, protected from discovery
- **Access Control**: Role-based access with JWT authentication
- **Audit Trail**: Immutable logs of all actions

### 📈 Processing Pipeline

1. Upload video/audio → S3
2. Trigger Step Function workflow
3. AWS Transcribe Medical → transcript with speaker labels
4. NLP analysis → detect declared tests
5. Video segmentation → extract clips
6. Computer vision → analyze actions
7. Sentiment analysis → detect demeanor issues
8. Generate report → PDF/HTML with evidence

### 🎓 Use Cases

- **Challenge biased CME reports**: Prove examiner didn't perform claimed tests
- **Demonstrate unprofessional behavior**: Evidence of negative tone, interruptions
- **Trial preparation**: Structured timeline of examination
- **Settlement negotiations**: Objective evidence of exam quality
- **Expert testimony**: Data-driven analysis for medical experts

### 📄 License

Proprietary - For use by authorized legal professionals only.

### 🆘 Support

For questions or support:
- Technical issues: Check `/docs` folder
- Legal questions: Consult with counsel regarding state-specific recording laws

---

**Built for plaintiff attorneys by attorneys who understand the challenges of fighting biased CMEs.**


