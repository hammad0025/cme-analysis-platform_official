/**
 * Cases service: wraps the live API and a fully local mock so the demo flow
 * works whether or not the deployed backend is reachable. Toggle with
 * REACT_APP_USE_MOCK_API=true (default off when an explicit API URL is set,
 * default on when REACT_APP_DEV_MODE=true).
 *
 * No analyzer code is invoked from here. Mock mode only stores case metadata
 * in localStorage and simulates upload progress.
 */
import api from './cmeApi';

const STORAGE_KEY = 'cme_mock_cases_v1';
const DIRECT_UPLOAD_TIMEOUT_MS = 115 * 60 * 1000;

const USE_MOCK = (() => {
  const explicit = process.env.REACT_APP_USE_MOCK_API;
  const apiUrl = (process.env.REACT_APP_API_URL || '').trim();
  if (explicit === 'true') return true;
  if (explicit === 'false') {
    if (!apiUrl) {
      if (process.env.NODE_ENV !== 'production') {
        console.warn(
          '[CME] REACT_APP_USE_MOCK_API=false requires REACT_APP_API_URL; using mock mode.',
        );
      }
      return true;
    }
    return false;
  }
  // Default: mock when explicitly in dev mode and no overriding API URL.
  if (process.env.REACT_APP_DEV_MODE === 'true' && !apiUrl) {
    return true;
  }
  return false;
})();

export const isMockMode = () => USE_MOCK;

const readMockCases = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (_err) {
    return [];
  }
};

const writeMockCases = (cases) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cases));
  } catch (_err) {
    // Quota / private-mode: ignore. Mock cases just don't persist.
  }
};

const randomId = () => {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 8);
  return `mock_${ts}_${rand}`;
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Create a case shell (metadata only, no files yet). */
export async function createCase(metadata) {
  const payload = {
    plaintiff_name: metadata.plaintiff_name,
    examiner_name: metadata.examiner_name,
    exam_date: metadata.exam_date,
    date_of_injury: metadata.date_of_injury,
    date_of_birth: metadata.date_of_birth,
    state: metadata.state || 'FL',
  };

  if (USE_MOCK) {
    const caseId = randomId();
    const record = {
      case_id: caseId,
      ...payload,
      status: 'uploading',
      created_at: new Date().toISOString(),
      video: null,
      reports: [],
      is_mock: true,
    };
    const cases = readMockCases();
    cases.unshift(record);
    writeMockCases(cases);
    return record;
  }

  // Live: the deployed API still uses /cme/sessions for case creation.
  const slug = (payload.plaintiff_name || 'patient')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 40) || 'patient';
  const apiPayload = {
    patient_id: `${slug}-${Date.now().toString(36)}`,
    patient_name: payload.plaintiff_name,
    doctor_name: payload.examiner_name,
    exam_date: payload.exam_date,
    date_of_injury: payload.date_of_injury,
    date_of_birth: payload.date_of_birth,
    case_id: '',
    state: payload.state,
    attorney_name: '',
  };
  const resp = await api.post('/cme/sessions', apiPayload);
  const session = resp.data || {};
  return {
    case_id: session.session_id || session.case_id,
    ...payload,
    status: session.status || 'created',
    created_at: new Date().toISOString(),
    video: null,
    reports: [],
    is_mock: false,
  };
}

/** Persist updated case state (mock only; live API has its own state). */
export function updateMockCase(caseId, patch) {
  if (!USE_MOCK) return null;
  const cases = readMockCases();
  const idx = cases.findIndex((c) => c.case_id === caseId);
  if (idx < 0) return null;
  cases[idx] = { ...cases[idx], ...patch };
  writeMockCases(cases);
  return cases[idx];
}

export function listMockCases() {
  return readMockCases();
}

export function getMockCase(caseId) {
  return readMockCases().find((c) => c.case_id === caseId) || null;
}

export function deleteMockCase(caseId) {
  const cases = readMockCases().filter((c) => c.case_id !== caseId);
  writeMockCases(cases);
}

/** Remove all mock cases from localStorage (browser-only demo state). */
export function clearAllMockCases() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (_err) {
    // ignore
  }
}

export const MOCK_CASES_STORAGE_KEY = STORAGE_KEY;

// Browsers often report an empty MIME type for less common containers
// (.mpg, .mkv, ...). The presigned URL is signed against the content type we
// request, so the PUT must send the exact same header — infer it here and use
// it in both places.
const EXTENSION_CONTENT_TYPES = {
  mp4: 'video/mp4',
  m4v: 'video/mp4',
  mov: 'video/quicktime',
  mpg: 'video/mpeg',
  mpeg: 'video/mpeg',
  avi: 'video/x-msvideo',
  mkv: 'video/x-matroska',
  webm: 'video/webm',
  mp3: 'audio/mpeg',
  m4a: 'audio/mp4',
  wav: 'audio/wav',
  flac: 'audio/flac',
  pdf: 'application/pdf',
  doc: 'application/msword',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
};

export function inferContentType(file) {
  if (file?.type) return file.type;
  const ext = (file?.name || '').split('.').pop().toLowerCase();
  return EXTENSION_CONTENT_TYPES[ext] || 'application/octet-stream';
}

/**
 * Request a presigned upload URL for a file. In mock mode this resolves
 * immediately with a fake URL; the upload step will simulate progress.
 */
export async function requestUploadUrl({ caseId, file, kind, tag, recordingSlot }) {
  const contentType = inferContentType(file);
  if (USE_MOCK) {
    await sleep(120);
    return {
      upload_url: `mock://upload/${caseId}/${encodeURIComponent(file.name)}`,
      file_key: `${caseId}/${kind}/${Date.now()}_${file.name}`,
      recording_slot: recordingSlot,
      content_type: contentType,
      mock: true,
    };
  }
  const payload = {
    session_id: caseId,
    upload_kind: kind === 'video' ? 'recording' : 'doctor_report',
    filename: file.name,
    content_type: contentType,
    file_size: file.size,
    tag,
  };
  if (kind === 'video' && recordingSlot != null) {
    payload.recording_slot = recordingSlot;
  }
  const resp = await api.post('/cme/upload', payload);
  return {
    upload_url: resp.data.upload_url,
    file_key: resp.data.s3_key || resp.data.file_key || file.name,
    recording_slot: resp.data.recording_slot,
    content_type: contentType,
    mock: false,
  };
}

/**
 * Upload a file with progress reporting. Returns a cancel function alongside
 * a promise so callers can abort cleanly.
 */
export function uploadFileWithProgress({ url, file, onProgress, mock, contentType }) {
  if (mock) {
    let cancelled = false;
    let timer = null;
    const promise = new Promise((resolve, reject) => {
      let pct = 0;
      // Stretch the simulated upload to feel like work: ~3s + 1s per 100MB.
      const total = file.size;
      const steps = Math.min(40, Math.max(12, Math.ceil(file.size / (5 * 1024 * 1024))));
      const tickMs = Math.max(60, Math.min(180, 2500 / steps));
      timer = setInterval(() => {
        if (cancelled) return;
        pct = Math.min(100, pct + 100 / steps);
        if (onProgress) {
          onProgress({
            loaded: Math.round((pct / 100) * total),
            total,
            percent: pct,
          });
        }
        if (pct >= 100) {
          clearInterval(timer);
          resolve({ ok: true });
        }
      }, tickMs);
    });
    return {
      promise,
      cancel: () => {
        cancelled = true;
        if (timer) clearInterval(timer);
      },
    };
  }

  const xhr = new XMLHttpRequest();
  const promise = new Promise((resolve, reject) => {
    xhr.open('PUT', url, true);
    xhr.timeout = DIRECT_UPLOAD_TIMEOUT_MS;
    const effectiveType = contentType || inferContentType(file);
    if (effectiveType) {
      // Must match the content type the presigned URL was signed with,
      // otherwise S3 rejects the PUT with 403 SignatureDoesNotMatch.
      xhr.setRequestHeader('Content-Type', effectiveType);
    }
    xhr.upload.onprogress = (evt) => {
      if (!evt.lengthComputable || !onProgress) return;
      onProgress({
        loaded: evt.loaded,
        total: evt.total,
        percent: (evt.loaded / evt.total) * 100,
      });
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        if (onProgress) {
          onProgress({
            loaded: file.size,
            total: file.size,
            percent: 100,
          });
        }
        resolve({ ok: true, status: xhr.status });
      } else {
        const body = (xhr.responseText || '').replace(/\s+/g, ' ').trim().slice(0, 240);
        const details = body ? `: ${body}` : '';
        reject(new Error(`Upload failed (HTTP ${xhr.status})${details}`));
      }
    };
    xhr.onerror = () => reject(new Error('Network error during upload. Check the connection and try again.'));
    xhr.onabort = () => reject(new Error('Upload cancelled'));
    xhr.ontimeout = () => reject(new Error('Upload timed out before it completed. Check the connection and try again.'));
    xhr.send(file);
  });
  return { promise, cancel: () => xhr.abort() };
}

/** Mark uploads complete and kick off processing. */
export async function startProcessing({ caseId, video, videos, reports }) {
  const videoList = videos || (video ? [video] : []);
  if (USE_MOCK) {
    updateMockCase(caseId, {
      status: 'processing',
      video: videoList[0] || null,
      videos: videoList,
      reports,
      processing_started_at: new Date().toISOString(),
    });
    return { ok: true, mock: true };
  }
  const resp = await api.post('/cme/process', { session_id: caseId });
  return { ok: true, mock: false, ...(resp.data || {}) };
}

/** Try to list sessions/cases from live API; gracefully fall back to mock. */
export async function listCases() {
  const mockCases = readMockCases();
  if (USE_MOCK) {
    return { cases: mockCases, source: 'mock' };
  }
  try {
    const resp = await api.get('/cme/sessions');
    const remote = (resp.data && resp.data.sessions) || [];
    const normalized = remote.map((s) => ({
      case_id: s.session_id || s.case_id,
      plaintiff_name: s.patient_name || s.plaintiff_name,
      examiner_name: s.doctor_name || s.examiner_name,
      exam_date: s.exam_date,
      status: s.status,
      created_at: s.created_at || s.uploaded_at,
      is_mock: false,
    }));
    return { cases: [...mockCases, ...normalized], source: 'live' };
  } catch (err) {
    return { cases: mockCases, source: 'mock-fallback', error: err };
  }
}
