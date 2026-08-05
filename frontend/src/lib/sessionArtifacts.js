/** Normalize artifact URL keys from GET /cme/sessions/{id} for UI consumption. */
export function resolveArtifactUrls(session) {
  const raw = session?.artifact_urls || {};
  const artifacts = session?.analysis_artifacts || {};
  const pick = (...keys) => {
    for (const key of keys) {
      if (raw[key]) return raw[key];
    }
    return null;
  };

  return {
    ...raw,
    standard_report_html: pick('standard_report_html', 'report_html', 'cme_report_html'),
    standard_report_pdf: pick('standard_report_pdf', 'report_pdf'),
    comprehensive_analysis_json: pick('comprehensive_analysis_json'),
    behavior_summary_json: pick('behavior_summary_json'),
    behavior_dashboard_html: pick('behavior_dashboard_html'),
    test_ledger_json: pick('test_ledger_json'),
    named_test_index_json: pick('named_test_index_json'),
    three_way_ledger_json: pick('three_way_ledger_json'),
    claim_verdicts_json: pick('claim_verdicts_json'),
    claims_atomic_json: pick('claims_atomic_json'),
    analysis_report_txt: pick('analysis_report_txt'),
    cost_actual_json: pick('cost_actual_json'),
    _artifactKeys: artifacts,
  };
}

export function hasLinkedAnalysis(session) {
  if (!session || session.status !== 'completed') return false;
  const urls = resolveArtifactUrls(session);
  if (session.analysis_summary) return true;
  if (session.metadata?.linked_local_run || session.metadata?.is_backfilled) return true;
  return Boolean(
    urls.comprehensive_analysis_json ||
      urls.behavior_summary_json ||
      urls.standard_report_html ||
      urls.standard_report_pdf ||
      urls.behavior_dashboard_html
  );
}

export function analysisMetrics(session) {
  const summary = session?.analysis_summary || {};
  const meta = session?.metadata || {};
  return {
    plaintiff: summary.plaintiff_name || meta.patient_report_name || session?.patient_name,
    examiner: summary.examiner_name || meta.examiner_report_name || session?.doctor_name,
    examDate: summary.exam_date || session?.exam_date,
    videoDuration: summary.video_duration_label || summary.video_length || null,
    frameCount: summary.frame_count,
    costUsd: summary.cost_usd,
    qualityScore: summary.examination_quality_score,
    professionalismScore: summary.professionalism_score,
    linkedFrom: summary.linked_from || meta.linked_local_run,
  };
}

export function hasDoctorReport(session) {
  const dr = session?.doctor_report;
  return Boolean(dr && (dr.s3_key || dr.uri || dr.download_url));
}

export function doctorReportLabel(session) {
  const dr = session?.doctor_report;
  if (!dr) return null;
  return dr.label || dr.filename || 'Defense examiner report (original)';
}

export function normalizeSession(raw) {
  const session = raw?.session || raw || {};
  return {
    ...session,
    artifact_urls: resolveArtifactUrls(session),
  };
}

/** Resolve presigned PDF URL from session artifacts, with API fallback. */
export async function fetchSessionPdfUrl(sessionId, artifactUrls, apiClient) {
  const direct = artifactUrls?.standard_report_pdf;
  if (direct) return direct;
  if (!sessionId || !apiClient) return null;
  try {
    const response = await apiClient.get(`/cme/sessions/${sessionId}/report`, {
      params: { format: 'pdf' },
    });
    return response.data?.download_url || null;
  } catch {
    return null;
  }
}
