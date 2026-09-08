export const STEPS = [
  { id: 1, title: 'Case details', description: 'Plaintiff & examiner info' },
  { id: 2, title: 'Examination videos', description: 'CME recordings' },
  { id: 3, title: 'Reports & documents', description: 'PDF supporting materials' },
  { id: 4, title: 'Review & submit', description: 'Confirm and upload' },
];

export const VIDEO_MIME_PATTERN = /^video\//i;
export const VIDEO_EXT_PATTERN = /\.(mp4|mov|m4v|mpg|mpeg|avi|mkv|webm)$/i;
export const VIDEO_ACCEPT = 'video/*,.mp4,.mov,.m4v,.mpg,.mpeg,.avi,.mkv,.webm';
export const PDF_ACCEPT = 'application/pdf,.pdf';
export const MAX_VIDEO_BYTES = 5 * 1024 * 1024 * 1024;

export const REPORT_TYPES = [
  { value: 'cme_report', label: 'Defense expert report', short: 'CME report', color: 'indigo' },
  { value: 'initial_ime', label: 'Initial IME report', short: 'Initial IME', color: 'purple' },
  { value: 'medical_history', label: "Plaintiff's medical history", short: 'Med history', color: 'violet' },
  { value: 'other', label: 'Other supporting document', short: 'Other', color: 'slate' },
];

export const STATUS_CONFIG = {
  created: { label: 'Created', tone: 'blue', pulse: false },
  recording_uploaded: { label: 'Uploaded', tone: 'amber', pulse: false },
  uploading: { label: 'Uploading', tone: 'indigo', pulse: true },
  processing: { label: 'Processing', tone: 'purple', pulse: true },
  completed: { label: 'Completed', tone: 'emerald', pulse: false },
  completed_with_warnings: { label: 'Review Needed', tone: 'amber', pulse: false },
  cancelled: { label: 'Cancelled', tone: 'rose', pulse: false },
  failed: { label: 'Failed', tone: 'rose', pulse: false },
  error: { label: 'Error', tone: 'rose', pulse: false },
};

const REPORT_AVAILABLE_STATUSES = new Set(['completed', 'completed_with_warnings']);

// Maps backend processing_stage values onto the visible pipeline timeline.
// Pipeline order: ingestion → transcription → nlp (transcript analysis) →
// vision (video review) → report.
const PROCESSING_STAGE_TO_TIMELINE = {
  session_setup: 'ingestion',
  created: 'ingestion',
  ingestion: 'ingestion',
  recording_uploaded: 'ingestion',
  converting: 'ingestion',
  conversion_complete: 'ingestion',
  transcription: 'transcription',
  transcription_complete: 'nlp',
  nlp_analysis: 'nlp',
  video_analysis: 'vision',
  report_generation: 'report',
  report_generated: 'report',
  analysis_incomplete: 'report',
};

export const isFailedSessionStatus = (status) =>
  ['error', 'failed', 'cancelled'].includes(String(status || '').toLowerCase());

export const isReportAvailableSessionStatus = (status) =>
  REPORT_AVAILABLE_STATUSES.has(String(status || '').toLowerCase());

export const isTerminalSessionStatus = (status) =>
  isFailedSessionStatus(status) || isReportAvailableSessionStatus(status);

export function timelineStageForSession(session) {
  const status = String(session?.status || '').toLowerCase();
  if (isReportAvailableSessionStatus(status)) return 'report';
  const stage = String(session?.processing_stage || '').toLowerCase();
  if (stage.startsWith('transcription_failed')) return 'transcription';
  if (stage === 'conversion_failed') return 'ingestion';
  if (stage === 'report_failed') return 'report';
  if (stage === 'processing_start_failed') return 'ingestion';
  return PROCESSING_STAGE_TO_TIMELINE[stage]
    || (status === 'processing' ? 'transcription' : 'ingestion');
}

export const todayISO = () => new Date().toISOString().slice(0, 10);

export const formatBytes = (n) => {
  if (!Number.isFinite(n) || n <= 0) return '0 B';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
};

export const isVideoFile = (file) =>
  !!file && (VIDEO_MIME_PATTERN.test(file.type || '') || VIDEO_EXT_PATTERN.test(file.name || ''));

export const isPdfFile = (file) =>
  !!file && (file.type === 'application/pdf' || /\.pdf$/i.test(file.name || ''));

export const makeFileId = (file) =>
  `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2, 8)}`;

export const reportLabel = (type) =>
  REPORT_TYPES.find((r) => r.value === type)?.label || type;

export const reportShortLabel = (type) =>
  REPORT_TYPES.find((r) => r.value === type)?.short || type;
