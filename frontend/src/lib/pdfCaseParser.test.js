import {
  normalizeReportText,
  parseReportDate,
  parseCaseMetadataFromText,
  toWizardMetadata,
} from './pdfCaseParser';

const SCAMMON_SAMPLE = `
COMPULSORY MEDICAL EXAMINATION
Patient: Wendy Scammon
DOB: 1964-10-01
Examiner: Dr. Brett Osborn DO
Date of CME: 2021-03-09
Date of Injury: 2014-12-06
State of Florida
`;

const HARDECKER_SAMPLE = `
CME ANALYSIS REPORT
Plaintiff: Stephanie Hardecker
DOB: 10/16/1979
Date of Injury: 4/20/2021
Case No: 56 2021 CA 001905
Examiner: Dr. Brett A. Osborn, DO, FAANS, CSCS
Exam Date: 5/27/2022
Independent Medical Examination
`;

describe('pdfCaseParser', () => {
  test('normalizeReportText collapses line breaks', () => {
    expect(normalizeReportText('Patient:\nWendy\nScammon')).toBe('Patient: Wendy Scammon');
  });

  test('parseReportDate handles ISO and US formats', () => {
    expect(parseReportDate('2021-03-09')).toBe('2021-03-09');
    expect(parseReportDate('10/16/1979')).toBe('1979-10-16');
    expect(parseReportDate('4/20/2021')).toBe('2021-04-20');
    expect(parseReportDate('March 9, 2021')).toBe('2021-03-09');
  });

  test('parses Scammon CME report patterns', () => {
    const { fields, fields_found, confidence } = parseCaseMetadataFromText(SCAMMON_SAMPLE);
    expect(fields.plaintiff_name).toBe('Wendy Scammon');
    expect(fields.examiner_name).toMatch(/Brett Osborn/i);
    expect(fields.exam_date).toBe('2021-03-09');
    expect(fields.date_of_injury).toBe('2014-12-06');
    expect(fields.date_of_birth).toBe('1964-10-01');
    expect(fields.state).toBe('Florida');
    expect(fields_found).toEqual(expect.arrayContaining(['plaintiff_name', 'examiner_name', 'exam_date']));
    expect(confidence).toBe('high');
  });

  test('parses Hardecker IME-style report patterns', () => {
    const { fields, fields_found, report_type_hint } = parseCaseMetadataFromText(HARDECKER_SAMPLE);
    expect(fields.plaintiff_name).toBe('Stephanie Hardecker');
    expect(fields.examiner_name).toMatch(/Brett A\. Osborn/i);
    expect(fields.exam_date).toBe('2022-05-27');
    expect(fields.date_of_injury).toBe('2021-04-20');
    expect(fields.date_of_birth).toBe('1979-10-16');
    expect(fields.claim_number).toBe('56 2021 CA 001905');
    expect(fields_found).toContain('claim_number');
    expect(report_type_hint).toBe('cme_report');
  });

  test('toWizardMetadata maps to form shape', () => {
    const meta = toWizardMetadata({
      plaintiff_name: 'Wendy Scammon',
      exam_date: '2021-03-09',
    });
    expect(meta.plaintiff_name).toBe('Wendy Scammon');
    expect(meta.exam_date).toBe('2021-03-09');
    expect(meta.examiner_name).toBe('');
  });
});
