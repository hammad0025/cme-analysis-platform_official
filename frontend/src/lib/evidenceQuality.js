/**
 * Client-side mirror of backend cme_evidence_quality gates (last line of defense).
 * Keep in sync with BROLL_NOTE_PHRASES / NON_EXAM patterns in Python module.
 */

export const BROLL_NOTE_PHRASES = [
  'exterior',
  'building',
  'establishing shot',
  'no medical examination',
  'no examination activity',
  'no patient',
  'waiting area',
  'waiting room',
  'transitional footage',
  'empty hallway',
  'empty medical facility',
  'hallway rather than',
  'conducted in hallway',
];

const ATTIRE_PHRASES = [
  'street clothes',
  'street cloth',
  'medical gown',
  'examination gown',
  'blue scrubs',
  'wearing scrubs',
  'regular clothes',
  'fully clothed',
  'through clothing',
  'through cloth',
  'thoroughness',
];

const GAIT_ONLY_MARKERS = [
  'gait assessment',
  'during gait',
  'walking in hallway',
  'walking alongside',
  'walking behind',
  'walking ahead',
  'heel walk',
  'toe walk',
  'tandem gait',
];

const CRANIAL_EXAM_MARKERS = [
  'cranial nerve',
  'cranial examination',
  'head/cranial',
  'eye movement',
  'extraocular',
  'pupil',
  'pupillary',
  'facial nerve',
  'smile test',
];

const PATHOLOGICAL_MARKERS = [
  'hoffmann',
  'babinski',
  'plantar response',
  'plantar reflex',
  'pathological reflex',
  'long tract',
  'reflex hammer',
  'reflex test',
];

const TEST_VERB_MARKERS = [
  'performing',
  'resistance',
  'manual muscle',
  'mmt',
  'muscle test',
  'strength test',
  'hoffmann',
  'babinski',
  'reflex hammer',
  'cranial',
  'pupil',
  'eye movement',
  'plantar',
];

const WEAK_TEST_MENTIONS = [
  'compromise accuracy of strength testing',
  'could impact thoroughness',
  'could limit thoroughness',
  'problematic for complete examination',
];

export function notesIndicateBroll(notes) {
  const n = String(notes || '').toLowerCase();
  return BROLL_NOTE_PHRASES.some((p) => n.includes(p));
}

function hasDescribedTestAction(notes) {
  const lower = String(notes || '').toLowerCase();
  if (WEAK_TEST_MENTIONS.some((w) => lower.includes(w))) return false;
  return TEST_VERB_MARKERS.some((v) => lower.includes(v));
}

function notesPrimarilyAttireComplaint(notes) {
  const lower = String(notes || '').toLowerCase().trim();
  if (!lower) return false;
  if (!ATTIRE_PHRASES.some((p) => lower.includes(p))) return false;
  const attireHits = (lower.match(
    /street\s*clothes?|scrubs|gown|clothed|clothing|attire|thoroughness/g,
  ) || []).reduce((sum, m) => sum + m.length, 0);
  const ratio = attireHits / Math.max(lower.length, 1);
  return ratio > 0.6 && !hasDescribedTestAction(lower);
}

function isPureGaitNote(notes) {
  const lower = String(notes || '').toLowerCase();
  if (GAIT_ONLY_MARKERS.some((m) => lower.includes(m))) return true;
  return (lower.includes('gait') || lower.includes('walking')) && lower.includes('hallway');
}

function hasCranialSignal(notes) {
  const lower = String(notes || '').toLowerCase();
  if (
    (lower.includes('hallway') || lower.includes('corridor') || lower.includes('during gait'))
    && !CRANIAL_EXAM_MARKERS.some((m) => lower.includes(m))
  ) {
    return false;
  }
  return CRANIAL_EXAM_MARKERS.some((m) => lower.includes(m));
}

function hasPathologicalSignal(notes) {
  const lower = String(notes || '').toLowerCase();
  return PATHOLOGICAL_MARKERS.some((m) => lower.includes(m));
}

export function noteSupportsClaim(notes, claimId) {
  const cid = String(claimId || '').toLowerCase();
  const lower = String(notes || '').toLowerCase();
  if (!cid) return true;
  if (cid.includes('cranial') && isPureGaitNote(lower) && !hasCranialSignal(lower)) {
    return false;
  }
  if (
    (cid.includes('hoffmann') || cid.includes('babinski') || cid.includes('long_tract'))
    && isPureGaitNote(lower)
    && !hasPathologicalSignal(lower)
  ) {
    return false;
  }
  return true;
}

export function evidenceNotesAreUsable(notes, claimId = '') {
  const text = String(notes || '').trim();
  if (!text) return false;
  const lower = text.toLowerCase();
  if (notesIndicateBroll(lower)) return false;
  if (
    lower.includes('doctor not visible')
    && !/(doctor in|doctor wearing|doctor is|doctor appears|examiner|alongside|walking behind|walking ahead|positioned close|hands on|goniometer|reflex hammer)/.test(
      lower,
    )
  ) {
    return false;
  }
  if (notesPrimarilyAttireComplaint(text)) return false;
  if (!noteSupportsClaim(text, claimId)) return false;
  return true;
}

/**
 * Filter deposition evidence items (timestamps / notes) for display.
 */
export function filterUsableEvidence(evidence = [], claimId = '') {
  return (evidence || []).filter((ev) => {
    const notes = String(ev?.notes || ev?.quote || '').trim();
    return evidenceNotesAreUsable(notes, claimId);
  });
}

export function evidenceTimestampsFiltered(evidence, claimId = '') {
  const stamps = [];
  for (const ev of filterUsableEvidence(evidence, claimId)) {
    const ts = ev?.timestamp_sec;
    if (ts != null && !Number.isNaN(Number(ts))) {
      stamps.push(Math.round(Number(ts)));
    }
  }
  return [...new Set(stamps)].sort((a, b) => a - b);
}

export const NOT_SHOWN_ON_VIDEO = 'Not shown on video';
