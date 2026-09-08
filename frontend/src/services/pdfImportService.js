import * as pdfjsLib from 'pdfjs-dist/legacy/build/pdf.mjs';
import { parseCaseMetadataFromText } from '../lib/pdfCaseParser';

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/legacy/build/pdf.worker.min.mjs',
  import.meta.url
).toString();

const DEFAULT_MAX_PAGES = 5;

/**
 * Extract plain text from the first N pages of a PDF File (client-side).
 * @param {File} file
 * @param {{ maxPages?: number }} options
 * @returns {Promise<{ text: string, pagesRead: number }>}
 */
export async function extractTextFromPdf(file, { maxPages = DEFAULT_MAX_PAGES } = {}) {
  if (!file) throw new Error('No PDF file provided.');

  const buffer = await file.arrayBuffer();
  const loadingTask = pdfjsLib.getDocument({ data: buffer, useSystemFonts: true });
  const pdf = await loadingTask.promise;

  const pageCount = Math.min(pdf.numPages, maxPages);
  const chunks = [];

  for (let i = 1; i <= pageCount; i += 1) {
    const page = await pdf.getPage(i);
    const content = await page.getTextContent();
    const pageText = content.items.map((item) => item.str).join(' ');
    chunks.push(pageText);
  }

  return {
    text: chunks.join('\n\n'),
    pagesRead: pageCount,
  };
}

/**
 * Full import pipeline: PDF file → parsed case metadata.
 * @param {File} file
 * @returns {Promise<object>}
 */
export async function importCaseFromPdf(file) {
  const { text, pagesRead } = await extractTextFromPdf(file);
  const parsed = parseCaseMetadataFromText(text);

  return {
    ...parsed,
    pagesRead,
    sourceFilename: file.name,
    rawTextLength: text.length,
  };
}
