/**
 * Heuristic parser for CME / IME report PDF text.
 *
 * Supported field patterns (case-insensitive, flexible whitespace):
 * - plaintiff_name: "Plaintiff:", "Patient:", "Examinee:", "Claimant:"
 * - examiner_name: "Examiner:", "Physician:", "Doctor:", "Independent Examiner:"
 * - exam_date: "Exam Date:", "Date of Examination:", "Date of CME:", "Examination Date:"
 * - date_of_injury: "Date of Injury:", "DOI:", "Injury Date:"
 * - date_of_birth: "Date of Birth:", "DOB:", "Birth Date:"
 * - state: "State of …", "Jurisdiction:", Florida statute headers
 * - case_caption: "v." / "vs." caption lines
 * - claim_number: "Case No:", "Claim No:", "File No:"
 */

const MONTH_MAP = {
  january: '01',
  february: '02',
  march: '03',
  april: '04',
  may: '05',
  june: '06',
  july: '07',
  august: '08',
  september: '09',
  october: '10',
  november: '11',
  december: '12',
};

const REPORT_TYPE_HINTS = [
  { pattern: /\binitial\s+(?:independent\s+)?medical\s+examination\b/i, type: 'initial_ime' },
  { pattern: /\binitial\s+ime\b/i, type: 'initial_ime' },
  { pattern: /\bcompulsory\s+medical\s+examination\b/i, type: 'cme_report' },
  { pattern: /\bindependent\s+medical\s+examination\b/i, type: 'cme_report' },
  { pattern: /\bdefense\s+(?:expert\s+)?(?:report|examination)\b/i, type: 'cme_report' },
  { pattern: /\b(?:ime|cme)\s+report\b/i, type: 'cme_report' },
];

const US_STATES = new Set([
  'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut',
  'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa',
  'Kansas', 'Kentucky', 'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan',
  'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire',
  'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio',
  'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
  'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington', 'West Virginia',
  'Wisconsin', 'Wyoming',
]);

/** Collapse PDF line breaks and odd spacing for regex matching. */
export function normalizeReportText(raw) {
  if (!raw || typeof raw !== 'string') return '';
  return raw
    .replace(/\r\n/g, '\n')
    .replace(/\u00a0/g, ' ')
    .replace(/([a-z])-\n([a-z])/gi, '$1$2')
    .replace(/\n+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

/** Parse common US date strings to ISO YYYY-MM-DD. Returns null if unparseable. */
export function parseReportDate(raw) {
  if (!raw || typeof raw !== 'string') return null;
  const s = raw.trim().replace(/[.,]$/, '');

  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (m) return isoFromParts(m[1], m[2], m[3]);

  m = s.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$/);
  if (m) {
    let [, a, b, y] = m;
    if (y.length === 2) y = Number(y) > 50 ? `19${y}` : `20${y}`;
    const n1 = Number(a);
    const n2 = Number(b);
    // Prefer MM/DD when ambiguous (typical in US medical reports)
    const month = n1 <= 12 ? n1 : n2;
    const day = n1 <= 12 ? n2 : n1;
    return isoFromParts(y, month, day);
  }

  m = s.match(
    /^([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$/i
  );
  if (m) {
    const month = MONTH_MAP[m[1].toLowerCase()];
    if (month) return isoFromParts(m[3], month, m[2]);
  }

  m = s.match(/^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$/i);
  if (m) {
    const month = MONTH_MAP[m[2].toLowerCase()];
    if (month) return isoFromParts(m[3], month, m[1]);
  }

  return null;
}

function isoFromParts(year, month, day) {
  const y = String(year).padStart(4, '0');
  const mo = String(Number(month)).padStart(2, '0');
  const d = String(Number(day)).padStart(2, '0');
  const dt = new Date(`${y}-${mo}-${d}T12:00:00`);
  if (Number.isNaN(dt.getTime())) return null;
  if (dt.getFullYear() !== Number(y) || dt.getMonth() + 1 !== Number(mo) || dt.getDate() !== Number(d)) {
    return null;
  }
  return `${y}-${mo}-${d}`;
}

function firstMatch(text, patterns) {
  for (const { re, group = 1, transform = (v) => v?.trim() } of patterns) {
    const m = text.match(re);
    if (m && m[group]) {
      const val = transform(m[group]);
      if (val) return val;
    }
  }
  return null;
}

function cleanPersonName(name) {
  if (!name) return null;
  return name
    .replace(/\s{2,}/g, ' ')
    .replace(/[,;]+$/, '')
    .replace(/\b(?:ssn|social security).*$/i, '')
    .trim();
}

function cleanExaminerName(name) {
  if (!name) return null;
  let n = cleanPersonName(name);
  if (!n) return null;
  if (!/^dr\.?\s/i.test(n) && /\b(?:DO|MD|D\.O\.|M\.D\.)\b/i.test(n)) {
    n = `Dr. ${n}`;
  }
  return n;
}

const DATE_CAPTURE =
  '(\\d{4}-\\d{1,2}-\\d{1,2}|\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4}|[A-Za-z]+\\s+\\d{1,2}(?:st|nd|rd|th)?,?\\s+\\d{4}|\\d{1,2}\\s+[A-Za-z]+\\s+\\d{4})';

const LABEL_VALUE =
  '[:\\s]*([^\\n|]{2,120}?)(?=\\s*(?:\\||\\n|$|\\b(?:DOB|Date|Examiner|Plaintiff|Patient|Case|Claim|File)\\b))';

const FIELD_PATTERNS = {
  plaintiff_name: [
    { re: new RegExp(`\\bPlaintiff${LABEL_VALUE}`, 'i'), transform: cleanPersonName },
    { re: new RegExp(`\\bPatient${LABEL_VALUE}`, 'i'), transform: cleanPersonName },
    { re: new RegExp(`\\bExaminee${LABEL_VALUE}`, 'i'), transform: cleanPersonName },
    { re: new RegExp(`\\bClaimant${LABEL_VALUE}`, 'i'), transform: cleanPersonName },
  ],
  examiner_name: [
    { re: new RegExp(`\\bExaminer${LABEL_VALUE}`, 'i'), transform: cleanExaminerName },
    { re: new RegExp(`\\b(?:Independent\\s+)?(?:Medical\\s+)?Examiner${LABEL_VALUE}`, 'i'), transform: cleanExaminerName },
    { re: new RegExp(`\\bPhysician${LABEL_VALUE}`, 'i'), transform: cleanExaminerName },
    { re: /(?:^|\s)(Dr\.?\s+[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,4},?\s+(?:DO|MD|D\.O\.|M\.D\.)(?:[^|\n]{0,40})?)/i, group: 1, transform: cleanExaminerName },
  ],
  exam_date: [
    { re: new RegExp(`\\bExam(?:ination)?\\s+Date[:\\s]+${DATE_CAPTURE}`, 'i'), transform: parseReportDate },
    { re: new RegExp(`\\bDate\\s+of\\s+(?:Examination|CME|IME)[:\\s]+${DATE_CAPTURE}`, 'i'), transform: parseReportDate },
    { re: new RegExp(`\\bCME\\s+Date[:\\s]+${DATE_CAPTURE}`, 'i'), transform: parseReportDate },
  ],
  date_of_injury: [
    { re: new RegExp(`\\bDate\\s+of\\s+Injury[:\\s]+${DATE_CAPTURE}`, 'i'), transform: parseReportDate },
    { re: new RegExp(`\\bDOI[:\\s]+${DATE_CAPTURE}`, 'i'), transform: parseReportDate },
    { re: new RegExp(`\\bInjury\\s+Date[:\\s]+${DATE_CAPTURE}`, 'i'), transform: parseReportDate },
  ],
  date_of_birth: [
    { re: new RegExp(`\\b(?:Date\\s+of\\s+Birth|DOB)[:\\s]+${DATE_CAPTURE}`, 'i'), transform: parseReportDate },
    { re: new RegExp(`\\bBirth\\s+Date[:\\s]+${DATE_CAPTURE}`, 'i'), transform: parseReportDate },
  ],
  claim_number: [
    {
      re: /\b(?:Case|Claim|File)\s+(?:No\.?|Number|#)[:\s]+([A-Za-z0-9][A-Za-z0-9 .#-]{2,38}[A-Za-z0-9])(?=\s|$|\||\bExaminer\b|\bPatient\b|\bPlaintiff\b)/i,
    },
  ],
  state: [
    { re: /\bState\s+of\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b/ },
    { re: /\bJurisdiction[:\\s]+([^|\n]{2,30})/i },
    { re: /\b(?:in|for)\s+the\s+State\s+of\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b/i },
  ],
};

function detectReportType(text) {
  for (const { pattern, type } of REPORT_TYPE_HINTS) {
    if (pattern.test(text)) return type;
  }
  return 'cme_report';
}

function detectCaseCaption(text) {
  const m = text.match(
    /\b([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,4})\s+(?:v\.?|vs\.?)\s+([A-Z][A-Za-z.&' -]{2,60})/
  );
  if (!m) return null;
  return `${cleanPersonName(m[1])} v. ${cleanPersonName(m[2])}`;
}

function computeConfidence(fieldsFound, coreFields = ['plaintiff_name', 'examiner_name', 'exam_date']) {
  const coreHit = coreFields.filter((f) => fieldsFound.includes(f)).length;
  const total = fieldsFound.length;
  if (coreHit >= 3) return 'high';
  if (coreHit >= 2 || total >= 4) return 'medium';
  if (total >= 1) return 'low';
  return 'none';
}

/**
 * Parse normalized CME/IME report text into structured case metadata.
 * @returns {{ fields: object, fields_found: string[], confidence: string, report_type_hint: string }}
 */
export function parseCaseMetadataFromText(rawText) {
  const text = normalizeReportText(rawText);
  const fields = {};
  const fields_found = [];

  for (const [key, patterns] of Object.entries(FIELD_PATTERNS)) {
    const val = firstMatch(text, patterns);
    if (val) {
      if (key === 'state' && !US_STATES.has(val) && !/^Florida$/i.test(val)) {
        // keep loose jurisdiction strings only if they look like a state name
        if (val.length > 20) continue;
      }
      fields[key] = val;
      fields_found.push(key);
    }
  }

  const caption = detectCaseCaption(text);
  if (caption) {
    fields.case_caption = caption;
    fields_found.push('case_caption');
    if (!fields.plaintiff_name) {
      const plaintiffFromCaption = caption.split(/\s+v\.?\s/i)[0];
      if (plaintiffFromCaption) {
        fields.plaintiff_name = plaintiffFromCaption;
        if (!fields_found.includes('plaintiff_name')) fields_found.push('plaintiff_name');
      }
    }
  }

  const report_type_hint = detectReportType(text);

  return {
    fields,
    fields_found,
    confidence: computeConfidence(fields_found),
    report_type_hint,
  };
}

/** Build a short human-readable summary of parsed fields. */
export function formatParsePreview(fields) {
  const parts = [];
  if (fields.plaintiff_name) parts.push(fields.plaintiff_name);
  if (fields.examiner_name) parts.push(fields.examiner_name);
  if (fields.exam_date) parts.push(`Exam ${fields.exam_date}`);
  return parts.join(' · ');
}

/** Map parser output to NewCase wizard metadata shape. */
export function toWizardMetadata(parsedFields) {
  return {
    plaintiff_name: parsedFields.plaintiff_name || '',
    examiner_name: parsedFields.examiner_name || '',
    exam_date: parsedFields.exam_date || '',
    date_of_injury: parsedFields.date_of_injury || '',
    date_of_birth: parsedFields.date_of_birth || '',
  };
}
