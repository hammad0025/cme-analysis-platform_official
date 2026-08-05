import { hasLinkedAnalysis, normalizeSession, resolveArtifactUrls } from './sessionArtifacts';

describe('sessionArtifacts', () => {
  const sampleSession = {
    status: 'completed',
    analysis_summary: { frame_count: 2617, cost_usd: 47.45 },
    artifact_urls: {
      report_html: 'https://example.com/report.html',
      standard_report_pdf: 'https://example.com/report.pdf',
      comprehensive_analysis_json: 'https://example.com/comp.json',
    },
    metadata: { linked_local_run: 'osborn_2021_03/analysis_run_halfsec' },
  };

  it('resolves report_html fallback to standard_report_html', () => {
    const urls = resolveArtifactUrls(sampleSession);
    expect(urls.standard_report_html).toBe('https://example.com/report.html');
    expect(urls.standard_report_pdf).toBe('https://example.com/report.pdf');
  });

  it('detects linked analysis on completed sessions', () => {
    expect(hasLinkedAnalysis(sampleSession)).toBe(true);
    expect(hasLinkedAnalysis({ status: 'processing' })).toBe(false);
  });

  it('normalizes nested API response', () => {
    const normalized = normalizeSession({ session: sampleSession });
    expect(normalized.artifact_urls.standard_report_html).toBe('https://example.com/report.html');
  });
});
