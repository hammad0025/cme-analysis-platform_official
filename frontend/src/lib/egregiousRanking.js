/**
 * Client-side mirror of backend cme_egregious_ranking.py for Main Issues hero.
 */

const METADATA_CLAIM_IDS = new Set([
  'plaintiff', 'patient', 'patient_name', 'plaintiff_name', 'examiner', 'examiner_name',
  'doctor', 'doctor_name', 'exam_date', 'date_of_injury', 'date_of_birth', 'dob', 'doi',
  'attorney', 'attorney_name', 'case_id', 'report_context', 'initial_ime_reference',
  'exam_time', 'state', 'video_length',
]);

const ISSUE_TYPE_LABELS = {
  contradiction: 'CONTRADICTION',
  rom_gap: 'ROM GAP',
  not_shown: 'NOT SHOWN ON VIDEO',
  performed_not_reported: 'DONE BUT NOT IN REPORT',
  technique_gap: 'TECHNIQUE GAP',
};

const ISSUE_BADGE_STYLES = {
  contradiction: 'bg-rose-600 text-white ring-rose-700',
  rom_gap: 'bg-amber-600 text-white ring-amber-700',
  not_shown: 'bg-purple-600 text-white ring-purple-700',
  performed_not_reported: 'bg-orange-600 text-white ring-orange-700',
  technique_gap: 'bg-slate-600 text-white ring-slate-700',
};

const LOW_PRIORITY = new Set(['general_appearance', 'mental_status']);

// Administrative / transcription noise: hard-banned from findings.
const BANNED_NOISE_RE = new RegExp(
  '\\b(?:'
  + 'name\\s+(?:was\\s+)?(?:recorded|spelled|misspelled|mispronounced|stated)'
  + '|misspell\\w*|spelling|mispronunc\\w*|pronunciation'
  + '|transcription\\s+(?:error|artifact|issue|quality)'
  + '|transcript\\s+(?:error|artifact)'
  + '|audio\\s+quality|recording\\s+quality|inaudible'
  + '|recorded\\s+improperly'
  + '|paperwork|scheduling|check[- ]?in|consent\\s+form'
  + '|small\\s+talk|greeting'
  + ')\\b',
  'i',
);

const DEMEANOR_ONLY_RE = /\b(?:rude|dismissive|condescending|impatient|unprofessional|not\s+nice|bedside\s+manner|tone|demeanor|attitude|empath\w*|rapport)\b/i;
const EXAM_SUBSTANCE_RE = /\b(?:test(?:s|ing)?|rom|range\s+of\s+motion|goniometer|inclinometer|strength|reflex\w*|sensor\w*|sensation|gait|romberg|babinski|hoffmann|palpat\w*|cranial|coordination|duration|minutes?|measure\w*|clothing|clothes|gown|maneuver|instrument)\b/i;

// Mirror of backend is_physical_exam_claim hints.
const PHYSICAL_EXAM_CLAIM_HINTS = [
  'reflex', 'gait', 'romberg', 'cranial', 'rom', 'strength', 'motor', 'sensory',
  'coordination', 'palpation', 'straight_leg', 'slr', 'spurl', 'faber', 'neer',
  'lachman', 'mcmurray', 'babinski', 'hoffmann', 'long_tract', 'pathological',
  'phalens', 'tinel',
];

function isPhysicalExamClaimId(cid) {
  if (['exam_time', 'duration', 'mental_status', 'history'].some((x) => cid.includes(x))) {
    return false;
  }
  return PHYSICAL_EXAM_CLAIM_HINTS.some((h) => cid.includes(h));
}

function claimId(row) {
  return String(row?.claim_id || '').trim().toLowerCase();
}

function verdict(row) {
  return String(row?.verdict || 'insufficient_evidence').trim().toLowerCase();
}

function confidence(row) {
  const c = Number(row?.confidence);
  return Number.isFinite(c) ? c : 0;
}

export function isMetadataClaimId(id) {
  const key = String(id || '').trim().toLowerCase().replace(/-/g, '_');
  if (!key) return true;
  if (METADATA_CLAIM_IDS.has(key)) return true;
  return ['plaintiff_', 'patient_', 'examiner_', 'doctor_', 'attorney_', 'case_'].some(
    (p) => key.startsWith(p),
  );
}

function combinedText(row) {
  const ce = row?.cross_examination || {};
  const parts = [
    row?.report_quote, row?.claim_text, row?.video_shows, row?.reasoning,
    ce.video_finding, ce.leading_question,
  ];
  for (const ev of row?.evidence || []) {
    parts.push(ev?.notes, ev?.quote);
  }
  return parts.filter(Boolean).join(' ');
}

function isRomClaim(row) {
  const cid = claimId(row);
  if (cid.startsWith('rom_') || cid.includes('_rom')) return true;
  const text = combinedText(row).toLowerCase();
  return text.includes('range of motion') || text.includes('flexion contracture');
}

function hasDegrees(row) {
  return /\d+\s*(?:°|degrees?)/i.test(combinedText(row));
}

function lacksGoniometer(row) {
  return /no\s+goniometer|without\s+(?:visible\s+)?goniometer|street\s+clothes|wheelchair/i.test(
    combinedText(row),
  );
}

export function classifyIssueType(row) {
  const v = verdict(row);
  if (v === 'performed_not_reported') return 'performed_not_reported';
  if (v === 'contradicted') return 'contradiction';
  if (isRomClaim(row) && v === 'partially_supported') return 'rom_gap';
  if (v === 'not_shown') return 'not_shown';
  return 'technique_gap';
}

export function issueTypeLabel(row) {
  return ISSUE_TYPE_LABELS[classifyIssueType(row)] || 'TECHNIQUE GAP';
}

export function issueBadgeStyle(row) {
  return ISSUE_BADGE_STYLES[classifyIssueType(row)] || ISSUE_BADGE_STYLES.technique_gap;
}

function isLowPriority(row) {
  if (isMetadataClaimId(claimId(row))) return true;
  const cid = claimId(row);
  const v = verdict(row);
  if (LOW_PRIORITY.has(cid) && v !== 'contradicted') return true;
  if (v === 'supported') return true;
  return false;
}

export function isBannedNoise(row) {
  const text = combinedText(row);
  if (BANNED_NOISE_RE.test(text)) return true;
  if (DEMEANOR_ONLY_RE.test(text) && !EXAM_SUBSTANCE_RE.test(text)) return true;
  return false;
}

export function computeEgregiousScore(row) {
  if (isLowPriority(row) || isBannedNoise(row)) return 0;
  const v = verdict(row);
  const conf = confidence(row);
  const cid = claimId(row);

  if (v === 'contradicted') {
    const bonus = cid.includes('strength') ? 12 : 8;
    return 100 + conf * 10 + bonus;
  }
  // Test claimed in the report but never performed on video: top-tier impeachment.
  if (v === 'not_shown' && isPhysicalExamClaimId(cid)) return 80 + conf * 10;
  if (v === 'performed_not_reported') return 76 + conf * 8;
  if (isRomClaim(row) && v === 'partially_supported' && hasDegrees(row)) {
    let score = 68 + conf * 8;
    if (lacksGoniometer(row)) score += 8;
    return score;
  }
  if (v === 'partially_supported' && conf >= 0.55) return 55 + conf * 15;
  if (v === 'not_shown' && /inspection|palpation|strength|sensation|vascular|feet/.test(cid)) {
    return 35 + conf * 5;
  }
  return 0;
}

export function issuePunchLine(row) {
  const ce = row?.cross_examination || {};
  let report = String(row?.report_quote || row?.claim_text || '').trim();
  if (report.length > 120) report = `${report.slice(0, 117)}…`;
  let video = String(ce.video_finding || row?.video_shows || row?.reasoning || 'Not documented on video.').trim();
  if (video.length > 140) video = `${video.slice(0, 137)}…`;
  return `Report: "${report}" — Video: ${video}`;
}

export function whyItMatters(row) {
  const issue = classifyIssueType(row);
  const test = String(row?.test_name || claimId(row).replace(/_/g, ' ')).trim();
  if (issue === 'contradiction') {
    return `A contradicted ${test} finding undermines the defense doctor's credibility and gives plaintiff counsel a concrete impeachment point at deposition.`;
  }
  if (issue === 'performed_not_reported') {
    return `${test} was performed on camera but omitted from the written report — the record is incomplete and favorable findings may have been left out.`;
  }
  if (issue === 'rom_gap') {
    return 'Degree-specific ROM in the report cannot be verified on video without proper goniometer technique — a core Hunter methodology attack at trial.';
  }
  if (issue === 'not_shown') {
    return `The report documents ${test}, but the deposition video does not show it — counsel can force the doctor to identify the moment or admit it was not done on camera.`;
  }
  return `The video only partially supports the documented ${test}; deposition should pin down exact technique, planes tested, and instruments used.`;
}

export function threeWayRowToVerdict(row) {
  const ts = Number(row?.timestamp_sec) || 0;
  const testName = String(row?.test_name || row?.named_test_key || 'Unnamed test');
  const claimIdKey = `three_way_${row?.named_test_key || testName.toLowerCase().replace(/\s+/g, '_')}`;
  const depositionPrompt = String(
    row?.deposition_prompt
    || `Doctor, ${testName} appears on the deposition video at ${ts.toFixed(0)}s but is not documented in your written report — explain.`,
  );
  const techniqueNotes = (row?.technique_notes || []).slice(0, 2).join(' ');
  return {
    claim_id: claimIdKey,
    test_name: testName,
    claim_text: depositionPrompt,
    report_quote: row?.report_quote || '',
    report_page: row?.report_page,
    verdict: 'performed_not_reported',
    confidence: 0.75,
    reasoning: techniqueNotes || row?.detection_note || '',
    video_shows: techniqueNotes || `${testName} observed on video at ${ts.toFixed(0)}s.`,
    deposition_prompt: depositionPrompt,
    evidence: [{
      kind: 'frame',
      frame_id: (row?.frame_ids || [])[0],
      timestamp_sec: ts,
      notes: techniqueNotes || `${testName} performed on video.`,
    }],
    three_way_status: row?.three_way_status,
    source: 'three_way_ledger',
  };
}

export function mergeThreeWayIssues(verdicts, threeWayLedger) {
  const out = [...(verdicts || [])];
  const existing = new Set(out.map((v) => claimId(v)));
  for (const row of threeWayLedger?.rows || []) {
    if (row?.three_way_status !== 'performed_not_reported') continue;
    const converted = threeWayRowToVerdict(row);
    if (existing.has(claimId(converted))) continue;
    out.push(converted);
    existing.add(claimId(converted));
  }
  return out;
}

export function annotateEgregiousFields(row) {
  const enriched = { ...row };
  enriched.issue_type = classifyIssueType(enriched);
  enriched.issue_type_label = issueTypeLabel(enriched);
  enriched.egregious_score = Math.round(computeEgregiousScore(enriched) * 100) / 100;
  enriched.issue_punch_line = issuePunchLine(enriched);
  enriched.why_it_matters = whyItMatters(enriched);
  enriched.is_main_issue = enriched.egregious_score >= 50;
  return enriched;
}

export function rankMainIssues(verdicts, threeWayLedger = null, { maxIssues = 7, minScore = 50 } = {}) {
  const merged = mergeThreeWayIssues(verdicts, threeWayLedger);
  const candidates = merged
    .filter((v) => !isMetadataClaimId(v?.claim_id))
    .map(annotateEgregiousFields);
  return candidates
    .filter((c) => c.egregious_score >= minScore)
    .sort((a, b) => b.egregious_score - a.egregious_score || claimId(a).localeCompare(claimId(b)))
    .slice(0, maxIssues);
}

export function sortAllFindings(verdicts, threeWayLedger = null) {
  const merged = mergeThreeWayIssues(verdicts, threeWayLedger);
  return merged
    .filter((v) => !isMetadataClaimId(v?.claim_id))
    .map(annotateEgregiousFields)
    .sort((a, b) => b.egregious_score - a.egregious_score || claimId(a).localeCompare(claimId(b)));
}
