/**
 * Client-side Case Assistant (v1): rule-based Q&A over loaded case context.
 * No API keys or LLM calls — answers are synthesized from retrieved facts.
 */
import api from './cmeApi';
import { getMockCase, isMockMode } from './casesService';
import {
  isReportAvailableSessionStatus,
  STATUS_CONFIG,
  REPORT_TYPES,
} from '../lib/caseConstants';

const SAMPLE_BASE = '/sample-case';

const PROCESSING_STAGES = [
  { id: 'ingestion', label: 'File ingestion', etaMin: 0 },
  { id: 'transcription', label: 'Transcription', etaMin: 5 },
  { id: 'vision', label: 'Vision analysis', etaMin: 10 },
  { id: 'behavior', label: 'Behavior pass', etaMin: 15 },
  { id: 'report', label: 'Report generation', etaMin: 20 },
];

export const CONTEXT_TYPES = {
  DASHBOARD: 'dashboard',
  NEW_CASE: 'new_case',
  SAMPLE: 'sample',
  PROCESSING: 'processing',
  SESSION: 'session',
  GENERAL: 'general',
};

const normalize = (text) =>
  (text || '')
    .toLowerCase()
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const includesAny = (text, keywords) => keywords.some((k) => text.includes(k));

const scoreIntent = (text, keywords, weight = 1) => {
  let score = 0;
  keywords.forEach((k) => {
    if (text.includes(k)) score += weight;
  });
  return score;
};

export function detectContextType(pathname) {
  if (pathname === '/') return CONTEXT_TYPES.DASHBOARD;
  if (pathname === '/cases/new') return CONTEXT_TYPES.NEW_CASE;
  if (pathname === '/cases/sample') return CONTEXT_TYPES.SAMPLE;
  if (/^\/cases\/[^/]+$/.test(pathname) && pathname !== '/cases/new' && pathname !== '/cases/sample') {
    return CONTEXT_TYPES.PROCESSING;
  }
  if (/^\/sessions\/[^/]+$/.test(pathname)) return CONTEXT_TYPES.SESSION;
  return CONTEXT_TYPES.GENERAL;
}

export function extractRouteParams(pathname) {
  const caseMatch = pathname.match(/^\/cases\/([^/]+)$/);
  const sessionMatch = pathname.match(/^\/sessions\/([^/]+)$/);
  return {
    caseId: caseMatch && caseMatch[1] !== 'new' && caseMatch[1] !== 'sample' ? caseMatch[1] : null,
    sessionId: sessionMatch ? sessionMatch[1] : null,
  };
}

async function fetchJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}`);
  return res.json();
}

export async function loadContextData(contextType, { caseId, sessionId } = {}) {
  const base = { contextType, caseId, sessionId, loadedAt: Date.now(), error: null };

  try {
    if (contextType === CONTEXT_TYPES.SAMPLE) {
      const [manifest, comprehensive, behavior, testLedger] = await Promise.all([
        fetchJSON(`${SAMPLE_BASE}/MANIFEST.json`),
        fetchJSON(`${SAMPLE_BASE}/comprehensive_analysis.json`),
        fetchJSON(`${SAMPLE_BASE}/behavior_summary.json`),
        fetchJSON(`${SAMPLE_BASE}/test_ledger.json`).catch(() => null),
      ]);
      return { ...base, manifest, comprehensive, behavior, testLedger };
    }

    if (contextType === CONTEXT_TYPES.PROCESSING && caseId) {
      const mock = getMockCase(caseId);
      if (mock) return { ...base, caseData: { ...mock, source: 'mock' } };
      if (!isMockMode()) {
        const res = await api.get(`/cme/sessions/${caseId}`);
        const s = res.data?.session || res.data || {};
        return {
          ...base,
          caseData: {
            case_id: caseId,
            plaintiff_name: s.patient_name || s.plaintiff_name,
            examiner_name: s.doctor_name || s.examiner_name,
            exam_date: s.exam_date,
            status: s.status,
            processing_started_at: s.processing_started_at || s.updated_at,
            videos: s.recordings || [],
            reports: s.doctor_report ? [s.doctor_report] : [],
            source: 'live',
          },
        };
      }
      return { ...base, caseData: null, error: 'Case not found in this browser session.' };
    }

    if (contextType === CONTEXT_TYPES.SESSION && sessionId) {
      const res = await api.get(`/cme/sessions/${sessionId}`);
      const session = res.data?.session || res.data || {};
      return { ...base, session };
    }

    return base;
  } catch (err) {
    return {
      ...base,
      error: err.response?.data?.error || err.message || 'Could not load case data.',
    };
  }
}

export function getSuggestedQuestions(contextType, contextData = {}) {
  switch (contextType) {
    case CONTEXT_TYPES.DASHBOARD:
      return [
        'How do I create a new case?',
        'What files do I need to upload?',
        'How does PDF import work?',
        'What does the platform analyze?',
      ];
    case CONTEXT_TYPES.NEW_CASE:
      return [
        'What information is required?',
        'What video formats are supported?',
        'Which report types can I upload?',
        'What happens after I submit?',
      ];
    case CONTEXT_TYPES.SAMPLE:
      return [
        'What orthopedic tests were observed?',
        'What technique issues were found?',
        'Summarize behavior findings',
        'What was the analysis cost?',
      ];
    case CONTEXT_TYPES.PROCESSING:
      return [
        "What's the processing status?",
        'When will the report be ready?',
        'What pipeline stages are running?',
        'Who is the plaintiff on this case?',
      ];
    case CONTEXT_TYPES.SESSION:
      return [
        'What orthopedic tests were observed?',
        "What's the processing status?",
        'What was the analysis cost?',
        'Can I upload more files?',
      ];
    default:
      return [
        'What can this platform do?',
        'How do I get started?',
        'What is a CME analysis?',
        'Where is the sample case?',
      ];
  }
}

function statusLabel(status) {
  return STATUS_CONFIG[status]?.label || status || 'Unknown';
}

function estimateProcessingStage(caseData) {
  if (!caseData?.processing_started_at) return PROCESSING_STAGES[1];
  const elapsedMin = (Date.now() - new Date(caseData.processing_started_at).getTime()) / 60000;
  let stage = PROCESSING_STAGES[0];
  for (const s of PROCESSING_STAGES) {
    if (elapsedMin >= s.etaMin) stage = s;
  }
  return stage;
}

function expectedFinish(caseData) {
  if (!caseData?.processing_started_at) return null;
  try {
    const started = new Date(caseData.processing_started_at);
    return new Date(started.getTime() + 30 * 60 * 1000);
  } catch {
    return null;
  }
}

function formatIssueLabel(issue) {
  return (issue || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function answerDashboard(text) {
  if (scoreIntent(text, ['create', 'new case', 'start', 'begin']) >= 1) {
    return `To create a new case, click **New case** in the navigation or use the dashboard action button. You'll walk through four steps: case details (plaintiff & examiner), examination videos, supporting PDF reports, then review & submit. Once uploaded, processing typically completes in about 15–30 minutes.`;
  }
  if (scoreIntent(text, ['file', 'upload', 'need', 'video', 'pdf', 'document']) >= 1) {
    return `You'll need **CME examination video recordings** (MP4, MOV, and other common formats; up to 5 GB each) and optional **supporting PDFs** such as the defense expert report, initial IME, or medical history. The wizard guides you through tagging each document.`;
  }
  if (scoreIntent(text, ['pdf', 'import', 'parse', 'extract']) >= 1) {
    return `On the **New case** page you can drag a defense CME PDF into the import zone. The platform extracts plaintiff name, examiner, exam date, and date of injury to pre-fill the wizard — always review extracted fields before submitting.`;
  }
  if (scoreIntent(text, ['sample', 'demo', 'example']) >= 1) {
    return `Open the **Sample** tab to explore the Osborne 2021 CME (Wendy Scammon v. Dr. Brett Osborn). It includes a full standard report, behavior dashboard, and timestamped technique findings — exactly what you'll receive when your case completes.`;
  }
  if (scoreIntent(text, ['mock', 'local', 'offline']) >= 1) {
    return isMockMode()
      ? `You're in **mock mode** — cases are stored locally in your browser and uploads are simulated. Set \`REACT_APP_USE_MOCK_API=false\` with a valid API URL to connect to the live backend.`
      : `You're connected to the **live API**. Cases sync with the deployed backend and processing runs on AWS.`;
  }
  return null;
}

function answerNewCase(text) {
  if (scoreIntent(text, ['required', 'information', 'field', 'detail']) >= 1) {
    return `Required fields: **plaintiff name**, **examiner name**, and **exam date**. Optional but recommended: date of injury, date of birth, and state (defaults to FL).`;
  }
  if (scoreIntent(text, ['video', 'format', 'recording']) >= 1) {
    return `Supported video formats include MP4, MOV, M4V, MPG, AVI, MKV, and WebM. Each file can be up to **5 GB**. You may upload multiple examination recordings.`;
  }
  if (scoreIntent(text, ['report', 'document', 'pdf', 'type']) >= 1) {
    const types = REPORT_TYPES.map((r) => r.label).join(', ');
    return `Supported report types: ${types}. All supporting materials should be PDF format.`;
  }
  if (scoreIntent(text, ['after', 'submit', 'process', 'happens', 'next']) >= 1) {
    return `After you submit, files upload securely and processing begins automatically. The pipeline transcribes the deposition video, reviews the examination against the doctor's written report, and generates a report-vs-video crosswalk. Expect deliverables in **about 15–30 minutes**.`;
  }
  return answerDashboard(text);
}

function answerSample(text, ctx) {
  const { manifest, comprehensive, behavior, testLedger } = ctx;
  const examiner = manifest?.examiner_name || comprehensive?.examiner_name || behavior?.examiner_name;
  const plaintiff = manifest?.plaintiff_name || comprehensive?.plaintiff_name;
  const cost = manifest?.cost_usd ?? comprehensive?.total_cost_usd;

  if (scoreIntent(text, ['orthopedic', 'ortho', 'neurologic', 'hoffmann', 'babinski', 'romberg', 'test index', 'test ledger']) >= 1
      || (scoreIntent(text, ['test', 'tests', 'performed']) >= 1 && !includesAny(text, ['cost', 'price', 'examiner', 'doctor']))) {
    if (testLedger?.events?.length) {
      const ortho = testLedger.events.filter((e) => e.category === 'orthopedic_neurologic');
      const observed = testLedger.events.filter((e) => e.observed_on_video);
      const claimOnly = testLedger.events.filter((e) => e.three_way_status === 'claimed_not_observed');
      const notReported = testLedger.events.filter((e) => e.three_way_status === 'observed_not_reported');
      const top = observed.slice(0, 6).map(
        (e) => `• **${e.test_name}**${e.start_sec != null ? ` at ${e.start_sec}s` : ''} — ${e.technique_verdict}`,
      );
      return `The **Report vs video** tab lists statements from the doctor's written report checked against the deposition recording. `
        + `${observed.length} with video timestamps; ${claimOnly.length} in report but not seen on video.\n\n`
        + `Open **Report vs video** and click a timestamp to jump to that moment in the recording.`;
    }
    const tests = comprehensive?.tests_performed || {};
    const entries = Object.entries(tests)
      .filter(([k]) => k !== 'unknown')
      .map(([k, v]) => `${formatIssueLabel(k)}: ${v} observations`);
    return `Tests observed in video:\n\n${entries.map((e) => `• ${e}`).join('\n') || 'No test counts available.'}\n\nRun \`scripts/build_test_ledger.py\` for the full test index.`;
  }
  if (scoreIntent(text, ['examiner', 'doctor', 'who']) >= 1) {
    return `The examiner on this sample case is **${examiner || 'Dr. Brett Osborn DO'}**, with plaintiff **${plaintiff || 'Wendy Scammon'}**. The CME was conducted on ${manifest?.exam_date || comprehensive?.exam_date || '2021-03-09'}.`;
  }
  if (scoreIntent(text, ['plaintiff', 'patient']) >= 1) {
    return `The plaintiff is **${plaintiff || 'Wendy Scammon'}** (DOB ${manifest?.date_of_birth || '1964-10-01'}). Date of injury: ${manifest?.date_of_injury || '2014-12-06'}.`;
  }
  if (scoreIntent(text, ['cost', 'price', 'spend', 'fee', '47']) >= 1) {
    const amt = cost != null ? `$${Number(cost).toFixed(2)}` : 'approximately $47.45';
    return `This sample analysis cost **${amt}** USD for the full Osborne 2021 video review. Viewing the completed session or sample case is **$0** — no re-analysis required.`;
  }
  if (scoreIntent(text, ['technique', 'issue', 'problem', 'missed', 'equipment', 'goniometer']) >= 1) {
    const issues = comprehensive?.technique_issues || [];
    const missing = comprehensive?.equipment_missing || [];
    if (!issues.length && !missing.length) {
      return 'No technique issues were flagged in the sample analysis.';
    }
    const issueLines = issues.slice(0, 5).map((i) => {
      const label = formatIssueLabel(i.issue || i.description);
      return `• **${label}** (${i.severity || 'medium'} severity${i.timestamp_sec != null ? `, at ${i.timestamp_sec}s` : ''})`;
    });
    const missingLine = missing.length
      ? `\n\nEquipment not observed: **${missing.map(formatIssueLabel).join(', ')}**.`
      : '';
    return `Key technique issues in this sample:\n\n${issueLines.join('\n')}${missingLine}`;
  }
  if (scoreIntent(text, ['behavior', 'demeanor', 'conduct', 'attention', 'phone', 'empathy', 'summarize']) >= 1) {
    const issues = behavior?.behavior_issues || comprehensive?.behavior_issues || [];
    const demeanor = behavior?.overall_demeanor || 'distracted';
    const top = issues.slice(0, 4).map((i) => `• **${i.category}**: ${i.description}`);
    const scores = behavior
      ? `\n\nScores — eye contact: ${behavior.eye_contact_score?.toFixed(1) ?? 'N/A'}, attention: ${behavior.attention_score?.toFixed(1) ?? 'N/A'}. Overall demeanor: **${demeanor}**.`
      : '';
    return `Behavior summary for ${plaintiff || 'this case'}:\n\n${top.join('\n') || 'No behavior issues recorded.'}${scores}`;
  }
  if (scoreIntent(text, ['claim', 'report', 'contradict', 'reality']) >= 1) {
    const claims = comprehensive?.claim_vs_reality || [];
    if (!claims.length) return 'No claim-vs-reality discrepancies were recorded.';
    const lines = claims.slice(0, 3).map(
      (c) => `• Report claimed: "${c.claim}" — observed: ${c.observation} (**${formatIssueLabel(c.issue)}**, ${c.severity})`,
    );
    return `Claim vs. reality findings:\n\n${lines.join('\n')}`;
  }
  if (scoreIntent(text, ['duration', 'time', 'hands on']) >= 1) {
    const claimed = comprehensive?.claimed_exam_time_min;
    const actual = comprehensive?.actual_hands_on_exam_sec;
    if (claimed != null && actual != null) {
      const actualMin = (actual / 60).toFixed(1);
      return `The report claimed **${claimed} minutes** of examination time. Video analysis found **${actualMin} minutes** (${actual}s) of hands-on examination — a significant discrepancy useful for cross-examination.`;
    }
    return 'Duration metrics are available in the comprehensive analysis on this sample case.';
  }
  return null;
}

function answerProcessing(text, ctx) {
  const { caseData } = ctx;
  if (!caseData) {
    return ctx.error || 'I could not find details for this case. It may only exist in another browser session.';
  }

  const plaintiff = caseData.plaintiff_name || 'the plaintiff';
  const examiner = caseData.examiner_name || 'the examiner';
  const status = caseData.status || 'processing';

  if (scoreIntent(text, ['status', 'progress', 'where']) >= 1) {
    const stage = estimateProcessingStage(caseData);
    return `Case **${caseData.case_id}** is currently **${statusLabel(status)}**. The active pipeline stage is **${stage.label}**. Plaintiff: ${plaintiff}; examiner: ${examiner}.`;
  }
  if (scoreIntent(text, ['when', 'ready', 'eta', 'finish', 'deliver', 'report']) >= 1) {
    const finish = expectedFinish(caseData);
    const finishStr = finish ? finish.toLocaleString() : 'in approximately 15–30 minutes from upload';
    return `Full analysis typically completes in **about 15–30 minutes**. ${finish ? `Earliest expected delivery: **${finishStr}**.` : 'Processing time depends on video length and queue depth.'} You'll receive a standard report, behavior dashboard, and comprehensive JSON findings.`;
  }
  if (scoreIntent(text, ['stage', 'pipeline', 'step', 'transcription', 'vision', 'behavior']) >= 1) {
    const stage = estimateProcessingStage(caseData);
    const stages = PROCESSING_STAGES.map(
      (s) => `• ${s.label}${s.id === stage.id ? ' ← **in progress**' : ''}`,
    );
    return `Processing pipeline for this case:\n\n${stages.join('\n')}\n\nThe examination video is compared statement-by-statement to the insurance doctor's written report.`;
  }
  if (scoreIntent(text, ['plaintiff', 'patient', 'who']) >= 1) {
    return `This case is for **${plaintiff}**, examined by **${examiner}** on ${caseData.exam_date || 'TBD'}.`;
  }
  if (scoreIntent(text, ['examiner', 'doctor']) >= 1) {
    return `The defense examiner is **${examiner}**. Plaintiff: ${plaintiff}.`;
  }
  if (scoreIntent(text, ['video', 'report', 'file', 'upload']) >= 1) {
    const vCount = caseData.videos?.length || (caseData.video ? 1 : 0);
    const rCount = caseData.reports?.length || 0;
    return `Uploaded materials: **${vCount}** video(s) and **${rCount}** report(s). Processing uses all submitted files.`;
  }
  return null;
}

function answerSession(text, ctx) {
  const { session } = ctx;
  if (!session) {
    return ctx.error || 'Session data is not loaded yet. Please try again in a moment.';
  }

  const status = session.status || 'created';
  const reportAvailable = isReportAvailableSessionStatus(status);
  const plaintiff = session.patient_name || session.plaintiff_name || 'Unknown';
  const examiner = session.doctor_name || session.examiner_name || 'Unknown';

  if (scoreIntent(text, ['cost', 'price', 'spend', 'fee', '47']) >= 1) {
    const summary = session.analysis_summary || {};
    const cost = summary.cost_usd;
    if (cost != null) {
      return `This session's linked analysis cost **$${Number(cost).toFixed(2)}** USD. Opening the **Report vs video** tab or reports is **$0** — do not re-run processing.`;
    }
    return 'Analysis cost is available on completed Osborne sessions (~**$47.45** for the sample half-second run). Viewing linked artifacts does not incur new charges.';
  }
  if (scoreIntent(text, ['orthopedic', 'ortho', 'neurologic', 'test index', 'hoffmann', 'babinski', 'romberg']) >= 1
      || (scoreIntent(text, ['test', 'tests']) >= 1 && !includesAny(text, ['cost', 'price']))) {
    if (reportAvailable) {
      return 'Open the **Report vs video** tab on this session for the deposition crosswalk. Click any row to seek the deposition video to that timestamp. Rows show report claims, named tests (Hoffmann, Babinski, Romberg, cervical ROM planes), and technique verdicts.';
    }
    return 'The **Report vs video** tab will populate after analysis completes, with click-to-seek deposition timestamps and three-way claim reconciliation.';
  }
  if (scoreIntent(text, ['status', 'progress']) >= 1) {
    return `Session status: **${statusLabel(status)}**. Patient: **${plaintiff}**; examiner: **${examiner}**; exam date: ${session.exam_date || 'TBD'}.`;
  }
  if (scoreIntent(text, ['when', 'ready', 'eta', 'report']) >= 1) {
    if (status === 'completed_with_warnings') {
      return `This session generated a report but needs review because some video analysis did not complete. ${session.analysis_warning || 'Open the report and warning banner before relying on it.'}`;
    }
    if (reportAvailable) {
      return `This session is **complete**. Download the standard report, behavior dashboard, and analysis artifacts from the session detail tabs.`;
    }
    if (status === 'processing') {
      return `Analysis is **in progress**. Expect deliverables in **about 15–30 minutes** after processing started. This page auto-refreshes every 15 seconds while processing.`;
    }
    if (['failed', 'error', 'cancelled'].includes(status)) {
      return `This session did not complete successfully (status: **${statusLabel(status)}**). You may need to re-upload materials or contact support.`;
    }
    return `Upload examination videos and reports first, then start processing. Once queued, expect results in **about 15–30 minutes**.`;
  }
  if (scoreIntent(text, ['examiner', 'doctor']) >= 1) {
    return `The examiner is **${examiner}**.`;
  }
  if (scoreIntent(text, ['plaintiff', 'patient']) >= 1) {
    return `The patient/plaintiff is **${plaintiff}**.`;
  }
  if (scoreIntent(text, ['upload', 'add', 'file', 'more']) >= 1) {
    const canEdit = status === 'created' || status === 'recording_uploaded';
    return canEdit
      ? `You can still **upload additional videos or reports** on this page while status is "${statusLabel(status)}".`
      : `Materials are locked once processing begins. Current status: **${statusLabel(status)}**.`;
  }
  if (scoreIntent(text, ['download', 'report', 'artifact']) >= 1) {
    return reportAvailable
      ? 'Report-ready sessions expose the **Overview**, **Standard Report**, **Behavior Dashboard**, and raw analysis JSON for download or review.'
      : `Reports become available when status is **Completed** or **Review Needed** (currently **${statusLabel(status)}**).`;
  }
  return null;
}

function answerGeneral(text) {
  if (scoreIntent(text, ['what can', 'help', 'capability', 'do', 'feature']) >= 1) {
    return `The CME Analysis Platform helps defense teams scrutinize compulsory medical examinations. It analyzes **examination video** for technique deficiencies (missing equipment, testing through clothing, inadequate gowning), **examiner behavior** (distraction, dismissiveness, ignored distress), and **claim vs. reality** discrepancies. Outputs include a standard report, behavior dashboard, and timestamped evidence.`;
  }
  if (scoreIntent(text, ['start', 'begin', 'get started']) >= 1) {
    return `Start from the **Dashboard** → **New case**, or explore the **Sample** case first to see deliverables. Upload CME video and optional PDF reports, then submit for automated analysis.`;
  }
  if (scoreIntent(text, ['cme', 'what is']) >= 1) {
    return `A **Compulsory Medical Examination (CME)** is an independent exam ordered in litigation. This platform reviews the recorded examination to identify deviations from standard practice and support cross-examination preparation.`;
  }
  if (scoreIntent(text, ['sample', 'demo']) >= 1) {
    return `Visit **Sample** in the navigation bar to explore a fully analyzed Osborne 2021 CME with real findings, costs, and downloadable reports.`;
  }
  return null;
}

function pickFallback(contextType, ctx) {
  const prompts = getSuggestedQuestions(contextType, ctx);
  return `I'm not sure I understood that. I'm best at questions about ${contextLabel(contextType)}. Try one of these:\n\n${prompts.map((p) => `• ${p}`).join('\n')}`;
}

function contextLabel(contextType) {
  const labels = {
    [CONTEXT_TYPES.DASHBOARD]: 'creating cases and uploading files',
    [CONTEXT_TYPES.NEW_CASE]: 'the new case wizard',
    [CONTEXT_TYPES.SAMPLE]: 'this sample case findings',
    [CONTEXT_TYPES.PROCESSING]: 'processing status and timelines',
    [CONTEXT_TYPES.SESSION]: 'this session and its reports',
    [CONTEXT_TYPES.GENERAL]: 'platform capabilities',
  };
  return labels[contextType] || 'the platform';
}

/**
 * @returns {Promise<{ answer: string, intent?: string }>}
 */
export async function answerQuestion(question, contextData = {}) {
  const text = normalize(question);
  if (!text) {
    return { answer: 'Please type a question and I\'ll do my best to help.', intent: 'empty' };
  }

  const { contextType } = contextData;
  let answer = null;
  let intent = 'unknown';

  if (includesAny(text, ['hello', 'hi', 'hey', 'thanks', 'thank you'])) {
    return {
      answer: `Hello! I'm your **Case Assistant**. I can help with ${contextLabel(contextType)}. What would you like to know?`,
      intent: 'greeting',
    };
  }

  switch (contextType) {
    case CONTEXT_TYPES.DASHBOARD:
      answer = answerDashboard(text);
      intent = 'dashboard';
      break;
    case CONTEXT_TYPES.NEW_CASE:
      answer = answerNewCase(text) || answerDashboard(text);
      intent = 'new_case';
      break;
    case CONTEXT_TYPES.SAMPLE:
      answer = answerSample(text, contextData);
      intent = 'sample';
      break;
    case CONTEXT_TYPES.PROCESSING:
      answer = answerProcessing(text, contextData);
      intent = 'processing';
      break;
    case CONTEXT_TYPES.SESSION:
      answer = answerSession(text, contextData);
      intent = 'session';
      break;
    default:
      answer = answerGeneral(text);
      intent = 'general';
      break;
  }

  if (!answer) {
    answer = answerGeneral(text);
    intent = 'general_fallback';
  }
  if (!answer) {
    answer = pickFallback(contextType, contextData);
    intent = 'fallback';
  }

  if (contextData.error && intent === 'fallback') {
    answer = `${contextData.error}\n\n${answer}`;
  }

  return { answer, intent };
}

export function getWelcomeMessage(contextType) {
  const labels = {
    [CONTEXT_TYPES.DASHBOARD]: 'your cases and getting started',
    [CONTEXT_TYPES.NEW_CASE]: 'creating and submitting a new case',
    [CONTEXT_TYPES.SAMPLE]: 'the Osborne 2021 sample analysis',
    [CONTEXT_TYPES.PROCESSING]: 'this case while it processes',
    [CONTEXT_TYPES.SESSION]: 'this session and its deliverables',
    [CONTEXT_TYPES.GENERAL]: 'the CME Analysis Platform',
  };
  return `Hi — I'm your **Case Assistant**. Ask me anything about ${labels[contextType] || 'the platform'}. I answer from case data and platform knowledge (no external AI in v1).`;
}

export const STORAGE_KEY = 'cme_assistant_chat_v1';

export function loadChatHistory() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveChatHistory(messages) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  } catch {
    // quota / private mode
  }
}
