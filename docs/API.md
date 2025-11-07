# CME Analysis Platform - API Documentation

Base URL: `https://your-api-gateway.amazonaws.com/prod`

## Authentication

All requests (except public endpoints) require a Bearer token in the Authorization header:

```
Authorization: Bearer <token>
```

## Endpoints

### Session Management

#### Create CME Session
```http
POST /cme/sessions
```

**Request Body:**
```json
{
  "patient_id": "string",
  "patient_name": "string",
  "doctor_name": "string",
  "state": "FL",
  "exam_date": "2025-01-15",
  "case_id": "string (optional)",
  "attorney_name": "string (optional)"
}
```

**Response (201):**
```json
{
  "session_id": "cme_abc123",
  "state": "FL",
  "recording_mode": "Full Record",
  "recording_allowed": {
    "video": true,
    "audio": true
  },
  "legal_basis": "Rule 1.360",
  "consent_required": true,
  "consent_text": "...",
  "session": { /* full session object */ }
}
```

#### List CME Sessions
```http
GET /cme/sessions?case_id=xxx&state=FL
```

**Response (200):**
```json
{
  "sessions": [
    {
      "session_id": "cme_abc123",
      "patient_name": "John Doe",
      "doctor_name": "Dr. Smith",
      "state": "FL",
      "status": "completed",
      "mode": "Full Record",
      "exam_date": "2025-01-15",
      "created_at": 1705334400
    }
  ],
  "count": 1
}
```

#### Get Session Details
```http
GET /cme/sessions/{session_id}
```

**Response (200):**
```json
{
  "session_id": "cme_abc123",
  "patient_id": "PT123",
  "patient_name": "John Doe",
  "doctor_name": "Dr. Smith",
  "state": "FL",
  "mode": "Full Record",
  "status": "processing",
  "processing_stage": "video_analysis",
  "video_uri": "s3://bucket/path",
  "transcript_uri": "s3://bucket/transcript.json",
  "consent_hash": "consent_xyz",
  "recording_allowed": {
    "video": true,
    "audio": true,
    "rule": "Rule 1.360"
  },
  "created_at": 1705334400,
  "updated_at": 1705334500
}
```

### Consent Management

#### Submit Consent
```http
POST /cme/consent
```

**Request Body:**
```json
{
  "session_id": "cme_abc123",
  "participant_role": "patient",
  "signature": "John Doe",
  "consent_text": "Full consent text...",
  "ip_address": "192.168.1.1"
}
```

**Response (200):**
```json
{
  "consent_id": "consent_xyz",
  "session_id": "cme_abc123",
  "participant_role": "patient",
  "timestamp": 1705334400,
  "message": "Consent recorded successfully"
}
```

### Recording Upload

#### Get Upload URL
```http
POST /cme/upload
```

**Request Body:**
```json
{
  "session_id": "cme_abc123",
  "filename": "recording.mp4",
  "content_type": "video/mp4",
  "file_size": 524288000
}
```

**Response (200):**
```json
{
  "session_id": "cme_abc123",
  "upload_url": "https://s3.amazonaws.com/presigned-url",
  "s3_key": "cme-recordings/cme_abc123/recording.mp4",
  "expires_in": 7200,
  "message": "Upload recording to this URL..."
}
```

**Upload Process:**
1. Get presigned URL from this endpoint
2. PUT file to presigned URL:
   ```javascript
   await fetch(upload_url, {
     method: 'PUT',
     body: file,
     headers: { 'Content-Type': 'video/mp4' }
   });
   ```
3. Call `/cme/process` to start analysis

#### Start Processing
```http
POST /cme/process
```

**Request Body:**
```json
{
  "session_id": "cme_abc123"
}
```

**Response (200):**
```json
{
  "session_id": "cme_abc123",
  "status": "processing",
  "stage": "transcription",
  "transcription_job": {
    "job_name": "cme-transcribe-abc123-...",
    "status": "IN_PROGRESS"
  },
  "estimated_time": "Processing time depends on recording length..."
}
```

### Reports

#### Generate Report
```http
GET /cme/sessions/{session_id}/report?format=html
```

**Query Parameters:**
- `format` (optional): `html` or `json` (default: `html`)
- `include_video` (optional): `true` or `false` (default: `true`)

**Response (200):**
```json
{
  "session_id": "cme_abc123",
  "report_key": "cme-reports/cme_abc123/report.html",
  "download_url": "https://s3.amazonaws.com/presigned-download-url",
  "format": "html",
  "generated_at": "2025-01-15T10:30:00Z"
}
```

## Data Models

### ExamSession
```typescript
{
  session_id: string;           // Primary key
  patient_id: string;
  patient_name?: string;
  doctor_name: string;
  state: string;                // State code (FL, CA, TX, PA)
  mode: string;                 // 'Full Record', 'Audio Only', 'Ephemeral'
  recording_allowed: {
    video: boolean;
    audio: boolean;
    rule: string;
  };
  video_uri?: string;
  transcript_uri?: string;
  consent_hash?: string;
  status: string;               // 'created', 'recording_uploaded', 'processing', 'completed', 'error'
  processing_stage?: string;    // 'transcription', 'nlp', 'video_analysis', etc.
  exam_date?: string;
  case_id?: string;
  attorney_name?: string;
  created_at: number;
  updated_at: number;
  metadata?: object;
}
```

### DeclaredStep
```typescript
{
  declared_step_id: string;     // Primary key
  session_id: string;           // GSI partition key
  timestamp: number;            // Decimal (seconds from start)
  label: string;                // Test type (lumbar_rom, straight_leg_raise, etc.)
  transcript_text: string;
  confidence: number;           // Decimal 0.0-1.0
  video_snippet_uri?: string;
  created_at: number;
}
```

### ObservedAction
```typescript
{
  observed_action_id: string;   // Primary key
  declared_step_id: string;
  motion_present: string;       // 'performed', 'brief', 'not_observed'
  pose_match: string;           // 'full_match', 'partial', 'no_match'
  confidence_score: number;     // Decimal 0.0-1.0
  analysis_details: object;
  created_at: number;
}
```

### DemeanorFlag
```typescript
{
  flag_id: string;              // Primary key
  session_id: string;
  timestamp: number;            // Decimal (seconds from start)
  flag_type: string;            // 'negative_tone', 'interruption', 'dismissive', 'aggressive'
  transcript_excerpt: string;
  severity: string;             // 'low', 'medium', 'high'
  description?: string;
  created_at: number;
}
```

### ConsentRecord
```typescript
{
  consent_id: string;           // Primary key
  session_id: string;
  participant_role: string;     // 'patient', 'examiner', 'attorney'
  signature: string;
  consent_text: string;
  timestamp: number;
  ip_address?: string;
  created_at: number;
}
```

## Error Responses

All errors follow this format:

```json
{
  "error": "Error message",
  "details": "Optional additional details"
}
```

**Status Codes:**
- `400` - Bad Request (missing/invalid parameters)
- `401` - Unauthorized (missing/invalid token)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `500` - Internal Server Error

## Rate Limits

- Standard tier: 1000 requests/minute
- Burst: 2000 requests

## State-Specific Rules

| State | Video | Audio | Mode | Legal Basis |
|-------|-------|-------|------|-------------|
| FL | ✅ | ✅ | Full Record | Rule 1.360 |
| CA | ✅ | ✅ | Full Record | CCP §2032.320 |
| PA | ❌ | ✅ | Audio Only | PA law |
| TX | ❌ | ❌ | Ephemeral | TX Civil Practice |

## Webhooks (Future)

Coming soon: Webhook notifications for processing status updates.


