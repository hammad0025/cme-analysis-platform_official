import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Link, useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import Button from '../components/Button';
import StatusBadge from '../components/case/StatusBadge';
import PdfReportPanel, { PdfDownloadButton } from '../components/case/PdfReportPanel';
import ClaimVerdictIndex from '../components/case/ClaimVerdictIndex';
import OrthopedicTestIndex from '../components/case/OrthopedicTestIndex';
import ThreeWayTestIndex from '../components/case/ThreeWayTestIndex';
import { useSessionPdfUrl } from '../hooks/useSessionPdfUrl';
import api from '../services/cmeApi';
import { inferContentType } from '../services/casesService';
import { isReportAvailableSessionStatus } from '../lib/caseConstants';
import {
  analysisMetrics,
  doctorReportLabel,
  fetchSessionPdfUrl,
  hasDoctorReport,
  hasLinkedAnalysis,
  normalizeSession,
  resolveArtifactUrls,
} from '../lib/sessionArtifacts';

function sortRecordings(recs) {
  if (!recs || !recs.length) return [];
  return [...recs].sort((a, b) => {
    const sa = a.recording_slot != null && a.recording_slot !== '' ? Number(a.recording_slot) : 1e12;
    const sb = b.recording_slot != null && b.recording_slot !== '' ? Number(b.recording_slot) : 1e12;
    if (sa !== sb) return sa - sb;
    return (Number(a.uploaded_at) || 0) - (Number(b.uploaded_at) || 0);
  });
}

function DoctorReportPanel({ doctorReport, title, subtitle, compact = false }) {
  if (!hasDoctorReport({ doctor_report: doctorReport })) return null;
  const label = doctorReportLabel({ doctor_report: doctorReport });
  const url = doctorReport.download_url;
  const isPdf = (doctorReport.content_type || '').includes('pdf');
  const uploadedAt = doctorReport.uploaded_at
    ? new Date(Number(doctorReport.uploaded_at) * 1000).toLocaleDateString()
    : null;

  return (
    <div
      className={
        compact
          ? 'rounded-xl border border-emerald-200 bg-emerald-50/80 p-4'
          : 'rounded-xl border border-slate-200 bg-gradient-to-br from-slate-50 to-indigo-50/40 p-5'
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-900">{title || label}</p>
          {subtitle && <p className="text-xs text-slate-600 mt-1">{subtitle}</p>}
          <p className="text-sm text-slate-700 mt-2">{doctorReport.filename || label}</p>
          {uploadedAt && (
            <p className="text-xs text-slate-500 mt-1">Uploaded {uploadedAt}</p>
          )}
        </div>
        {url && (
          <div className="flex flex-wrap gap-2">
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
            >
              {isPdf ? 'View PDF' : 'View report'}
            </a>
            <a
              href={url}
              download={doctorReport.filename || undefined}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-xl border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 transition-colors"
            >
              Download
            </a>
          </div>
        )}
      </div>
      {!url && (
        <p className="text-xs text-amber-700 mt-3">
          Report is stored on file. Refresh the page after the API update to enable download links.
        </p>
      )}
    </div>
  );
}

export default function SessionDetail() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Deep-link support: /sessions/{id}?t={seconds} (from PDF report timestamps)
  // opens the Report-vs-video tab and seeks the video to that moment.
  const deepLinkSeekSec = useMemo(() => {
    const raw = searchParams.get('t');
    if (raw == null || raw === '') return null;
    const sec = Number(raw);
    return Number.isFinite(sec) && sec >= 0 ? sec : null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [activeTab, setActiveTab] = useState(deepLinkSeekSec != null ? 'tests' : 'overview');
  const [uploading, setUploading] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const defaultTabApplied = useRef(deepLinkSeekSec != null);

  const loadSession = useCallback(async () => {
    try {
      setLoading(true);
      setNotFound(false);
      const response = await api.get(`/cme/sessions/${sessionId}`);
      setSession(normalizeSession(response.data.session || response.data));
    } catch (error) {
      const status = error.response?.status;
      if (status === 404) {
        setSession(null);
        setNotFound(true);
      } else {
        console.error('Failed to load session:', error);
        setSession(null);
      }
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  const sessionStatus = session?.status;
  useEffect(() => {
    if (sessionStatus !== 'processing') return undefined;
    const id = setInterval(loadSession, 15000);
    return () => clearInterval(id);
  }, [sessionStatus, loadSession]);

  const isTerminalFailure = ['cancelled', 'failed', 'error'].includes(session?.status);
  const reportAvailable = isReportAvailableSessionStatus(session?.status);
  const linkedAnalysis = session ? hasLinkedAnalysis(session) : false;
  const artifactUrls = session ? resolveArtifactUrls(session) : {};

  useEffect(() => {
    if (!session || defaultTabApplied.current) return;
    if (isReportAvailableSessionStatus(session.status) && hasLinkedAnalysis(session)) {
      setActiveTab('tests');
    }
    defaultTabApplied.current = true;
  }, [session]);
  const metrics = session ? analysisMetrics(session) : null;
  const { pdfUrl, loading: pdfLoading, error: pdfError } = useSessionPdfUrl(sessionId, artifactUrls);
  const showPdfReport = reportAvailable && (pdfUrl || pdfLoading || linkedAnalysis);

  const onUploadReport = async (file) => {
    setUploading(true);
    try {
      // Presign and PUT must use the identical content type, or S3
      // rejects the upload with SignatureDoesNotMatch.
      const ct = inferContentType(file) || 'application/pdf';
      const res = await api.post('/cme/upload', {
        session_id: sessionId,
        upload_kind: 'doctor_report',
        filename: file.name,
        content_type: ct,
        file_size: file.size,
      });
      const putRes = await fetch(res.data.upload_url, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': ct },
      });
      if (!putRes.ok) throw new Error(`Upload failed (HTTP ${putRes.status})`);
      await loadSession();
    } catch (error) {
      console.error(error);
      const msg = error.response?.data?.error || error.message || 'Failed to upload report';
      alert(msg);
    } finally {
      setUploading(false);
    }
  };

  const onUploadVideos = async (rows) => {
    setUploading(true);
    try {
      for (const { file, slot } of rows) {
        const ct = inferContentType(file) || 'video/mp4';
        const res = await api.post('/cme/upload', {
          session_id: sessionId,
          upload_kind: 'recording',
          filename: file.name,
          content_type: ct,
          file_size: file.size,
          recording_slot: slot,
        });
        const putRes = await fetch(res.data.upload_url, {
          method: 'PUT',
          body: file,
          headers: { 'Content-Type': ct },
        });
        if (!putRes.ok) throw new Error(`Upload of ${file.name} failed (HTTP ${putRes.status})`);
      }
      await loadSession();
    } catch (error) {
      console.error(error);
      const msg = error.response?.data?.error || error.message || 'Failed to upload video(s)';
      alert(msg);
    } finally {
      setUploading(false);
    }
  };

  const onStartProcessing = async () => {
    try {
      await api.post('/cme/process', { session_id: sessionId });
      await loadSession();
    } catch (error) {
      console.error(error);
      alert(error.response?.data?.error || 'Failed to start processing');
    }
  };

  const onRestartProcessing = async () => {
    setRestarting(true);
    try {
      await api.post('/cme/process', { session_id: sessionId });
      await loadSession();
    } catch (error) {
      console.error(error);
      alert(error.response?.data?.error || 'Failed to restart processing');
    } finally {
      setRestarting(false);
    }
  };

  const handleOpenPdfReport = async () => {
    if (pdfUrl) {
      window.open(pdfUrl, '_blank');
      return;
    }
    try {
      const url = await fetchSessionPdfUrl(sessionId, artifactUrls, api);
      if (url) window.open(url, '_blank');
      else alert('PDF report not available yet.');
    } catch (error) {
      console.error('Report download failed:', error);
      alert('Failed to download report');
    }
  };

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="h-32 rounded-2xl shimmer" />
        <div className="h-12 rounded-xl shimmer" />
        <div className="grid grid-cols-2 gap-6">
          <div className="h-64 rounded-2xl shimmer" />
          <div className="h-64 rounded-2xl shimmer" />
        </div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="max-w-lg mx-auto mt-8">
        <div className="rounded-2xl border border-slate-200 bg-white shadow-xl p-10 text-center">
          <div className="w-16 h-16 bg-gradient-to-br from-red-100 to-red-200 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-lg font-bold text-slate-900 mb-2">Session not found</h2>
          <p className="text-sm text-slate-600 mb-8 leading-relaxed">
            {notFound
              ? 'This session was removed or never existed. Start fresh with a new case or explore the sample deliverable.'
              : 'The session could not be loaded. Check your connection and try again.'}
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Button variant="secondary" size="md" onClick={() => navigate('/')}>
              Dashboard
            </Button>
            <Link to="/cases/new">
              <Button variant="primary" size="md">New case</Button>
            </Link>
            <Link to="/cases/sample">
              <Button variant="ghost" size="md">Sample case</Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const canEditMaterials = !linkedAnalysis && (
    session.status === 'created'
    || session.status === 'recording_uploaded'
    || session.status === 'error'
    || session.status === 'failed'
  );
  const hasRecordings = Boolean(
    (session.recordings && session.recordings.length > 0) ||
      (session.video_uri && session.video_uri !== '') ||
      linkedAnalysis
  );

  const tabs = [
    { id: 'overview', label: 'Overview', description: 'Case summary & status', icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' },
    { id: 'tests', label: 'Main issues', description: 'Key report vs video discrepancies', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
    { id: 'analysis', label: 'Analysis', description: 'Findings & discrepancies', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
    { id: 'timeline', label: 'Timeline', description: 'Chronological events', icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
    { id: 'recording', label: 'Materials', description: 'Upload videos & reports', icon: 'M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z' },
  ];

  return (
    <div className="max-w-5xl mx-auto">
      <motion.header
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-gradient-to-br from-slate-900 via-indigo-950 to-purple-950 shadow-2xl"
      >
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-0 right-0 w-72 h-72 bg-indigo-500/20 rounded-full blur-3xl" />
        </div>
        <div className="relative p-6 sm:p-8">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="mb-3">
                <StatusBadge status={session.status} className="!bg-white/10 !text-white !ring-white/20" />
              </div>
              <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
                {session.patient_name || 'CME Session'}
              </h1>
              <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-indigo-100/80">
                <span>{session.doctor_name || 'Examiner pending'}</span>
                <span className="text-indigo-300/50">·</span>
                <span>{session.state || 'State pending'}</span>
                <span className="text-indigo-300/50">·</span>
                <span>{session.exam_date || 'Date not set'}</span>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {showPdfReport && (
                <PdfDownloadButton
                  pdfUrl={pdfUrl}
                  size="lg"
                  onClick={!pdfUrl ? handleOpenPdfReport : undefined}
                />
              )}
              {canEditMaterials && (
                <Button variant="secondary" size="md" onClick={() => setActiveTab('recording')}>
                  {hasRecordings ? 'Manage materials' : 'Add materials'}
                </Button>
              )}
            </div>
          </div>

          {!hasRecordings && canEditMaterials && (
            <div className="mt-6 rounded-xl bg-white/10 border border-white/15 backdrop-blur-sm p-4 flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-white">No materials uploaded yet</p>
                <p className="text-xs text-indigo-100/70 mt-1">
                  Use the guided wizard for the best experience, or upload directly on the Materials tab.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link to="/cases/new">
                  <Button variant="primary" size="sm">Open new case wizard</Button>
                </Link>
                <Button variant="ghost" size="sm" className="!text-white hover:!bg-white/10" onClick={() => setActiveTab('recording')}>
                  Upload here
                </Button>
              </div>
            </div>
          )}
        </div>
      </motion.header>

      <div className="mt-6 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <nav className="flex overflow-x-auto p-2 gap-1" role="tablist" aria-label="Case sections">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                aria-controls={`panel-${tab.id}`}
                id={`tab-${tab.id}`}
                onClick={() => setActiveTab(tab.id)}
                className={`group flex-shrink-0 flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-all duration-200 cursor-pointer ${
                  isActive
                    ? 'bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200 shadow-sm'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <span
                  className={`flex items-center justify-center w-9 h-9 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/30'
                      : 'bg-slate-100 text-slate-500 group-hover:bg-indigo-100 group-hover:text-indigo-600'
                  }`}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={tab.icon} />
                  </svg>
                </span>
                <span>
                  <span className="block text-sm font-semibold">{tab.label}</span>
                  <span className={`block text-[11px] ${isActive ? 'text-indigo-500' : 'text-slate-400'}`}>
                    {tab.description}
                  </span>
                </span>
              </button>
            );
          })}
        </nav>
      </div>

      <main className="mt-6">
        {isTerminalFailure && (
          <TerminalStatusBanner
            session={session}
            canRetry={session.status !== 'cancelled' && hasRecordings}
            restarting={restarting}
            onRetry={onRestartProcessing}
          />
        )}
        <div role="tabpanel" id={`panel-${activeTab}`} aria-labelledby={`tab-${activeTab}`}>
          {activeTab === 'overview' && (
            <OverviewTab
              session={session}
              metrics={metrics}
              linkedAnalysis={linkedAnalysis}
              artifactUrls={artifactUrls}
              hasRecordings={hasRecordings}
              canEdit={canEditMaterials}
              onGoToTab={setActiveTab}
              pdfUrl={pdfUrl}
              pdfLoading={pdfLoading}
              pdfError={pdfError}
            />
          )}
          {activeTab === 'tests' && (
            <TestsTab
              session={session}
              sessionId={sessionId}
              artifactUrls={artifactUrls}
              linkedAnalysis={linkedAnalysis}
              initialSeekSec={deepLinkSeekSec}
            />
          )}
          {activeTab === 'analysis' && (
            <AnalysisTab
              session={session}
              sessionId={sessionId}
              artifactUrls={artifactUrls}
              linkedAnalysis={linkedAnalysis}
              pdfUrl={pdfUrl}
              pdfLoading={pdfLoading}
              pdfError={pdfError}
            />
          )}
          {activeTab === 'timeline' && (
            <TimelineTab
              session={session}
              artifactUrls={artifactUrls}
              linkedAnalysis={linkedAnalysis}
              pdfUrl={pdfUrl}
              pdfLoading={pdfLoading}
              pdfError={pdfError}
            />
          )}
          {activeTab === 'recording' && (
            <RecordingTab
              session={session}
              linkedAnalysis={linkedAnalysis}
              metrics={metrics}
              canEdit={canEditMaterials}
              hasRecordings={hasRecordings}
              uploading={uploading}
              onUploadReport={onUploadReport}
              onUploadVideos={onUploadVideos}
              onStartProcessing={onStartProcessing}
            />
          )}
        </div>
      </main>
    </div>
  );
}

function OverviewTab({ session, metrics, linkedAnalysis, artifactUrls, hasRecordings, canEdit, onGoToTab, pdfUrl, pdfLoading, pdfError }) {
  const dr = session.doctor_report;
  const recordingCount = session.recordings?.length || (session.video_uri ? 1 : linkedAnalysis ? 1 : 0);
  const reportAvailable = isReportAvailableSessionStatus(session.status);
  const showPdf = reportAvailable && (pdfUrl || pdfLoading);

  return (
    <div className="space-y-6">
      {showPdf && (
        <PdfReportPanel pdfUrl={pdfUrl} loading={pdfLoading} error={pdfError} showEmbed />
      )}
      {hasDoctorReport(session) && (
        <DoctorReportPanel
          doctorReport={session.doctor_report}
          title="Defense examiner report (original)"
          subtitle={session.doctor_name ? `${session.doctor_name} — written CME report for this case.` : undefined}
          compact
        />
      )}
      {linkedAnalysis && metrics && (
        <div className="rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50 to-teal-50 p-6 shadow-sm">
          <h3 className="text-base font-bold text-emerald-900 mb-2">Analysis complete</h3>
          <p className="text-sm text-emerald-800">
            {metrics.plaintiff || 'Patient'} — {metrics.examiner || session.doctor_name}
            {metrics.videoDuration && ` · ${metrics.videoDuration} deposition video`}
            {metrics.costUsd != null && ` · $${Number(metrics.costUsd).toFixed(2)} run cost`}
            {metrics.qualityScore != null && ` · quality ${metrics.qualityScore}/100`}
          </p>
          {metrics.linkedFrom && (
            <p className="text-xs text-emerald-700/80 mt-2 font-mono">
              Linked from {metrics.linkedFrom}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="primary" size="sm" onClick={() => onGoToTab('tests')}>
              Report vs video
            </Button>
            <Button variant="secondary" size="sm" onClick={() => onGoToTab('analysis')}>
              View findings
            </Button>
            {pdfUrl && <PdfDownloadButton pdfUrl={pdfUrl} size="sm" />}
            {artifactUrls.standard_report_html && (
              <Button variant="ghost" size="sm" onClick={() => onGoToTab('timeline')}>
                Open timeline
              </Button>
            )}
          </div>
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { id: 'overview', label: 'Overview', sub: 'You are here', icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' },
          { id: 'tests', label: 'Main issues', sub: linkedAnalysis ? 'Key discrepancies' : 'After analysis', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
          { id: 'analysis', label: 'Analysis', sub: reportAvailable ? 'View findings' : 'After processing', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
          { id: 'timeline', label: 'Timeline', sub: 'Chronology', icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
          { id: 'recording', label: 'Materials', sub: `${recordingCount} video(s)`, icon: 'M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z' },
        ].map((card) => (
          <button
            key={card.id}
            type="button"
            onClick={() => onGoToTab(card.id)}
            className="group text-left rounded-2xl border border-slate-200 bg-white p-4 shadow-sm hover:shadow-md hover:border-indigo-200 hover:-translate-y-0.5 transition-all duration-200"
          >
            <div className="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center group-hover:bg-indigo-600 group-hover:text-white transition-colors">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={card.icon} />
              </svg>
            </div>
            <div className="mt-3 text-sm font-semibold text-slate-900 group-hover:text-indigo-700">{card.label}</div>
            <div className="text-xs text-slate-500 mt-0.5">{card.sub}</div>
          </button>
        ))}
      </div>

      {!hasRecordings && canEdit && (
        <div className="rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-purple-50 p-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">Ready to add examination materials?</h3>
            <p className="text-sm text-slate-600 mt-1 max-w-xl">
              The new case wizard walks you through metadata, videos, and reports step-by-step. You can also upload directly from the Materials tab.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to="/cases/new">
              <Button variant="primary" size="md">Start new case wizard</Button>
            </Link>
            <Button variant="secondary" size="md" onClick={() => onGoToTab('recording')}>
              Upload on this session
            </Button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <InfoCard
        title="Session Information"
        icon="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
        items={[
          { label: 'Patient ID', value: session.patient_id },
          { label: 'Patient Name', value: session.patient_name },
          { label: 'Examiner', value: session.doctor_name },
          { label: 'Exam Date', value: session.exam_date },
          { label: 'Attorney', value: session.attorney_name },
          { label: 'Case ID', value: session.case_id },
        ]}
      />

      <InfoCard
        title="Recording Details"
        icon="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
        items={[
          { label: 'State', value: session.state },
          { label: 'Recording Mode', value: session.mode },
          { label: 'Legal Basis', value: session.recording_allowed?.rule },
          { label: 'Video Permitted', value: session.recording_allowed?.video ? 'Yes' : 'No' },
          { label: 'Audio Permitted', value: session.recording_allowed?.audio ? 'Yes' : 'No' },
          {
            label: "Doctor's report",
            value: dr
              ? dr.download_url
                ? (
                    <a
                      href={dr.download_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-indigo-600 hover:text-indigo-800 font-medium"
                    >
                      {dr.filename || 'View defense report'}
                    </a>
                  )
                : dr.filename || 'On file'
              : 'Not uploaded',
          },
        ]}
      />
      </div>
    </div>
  );
}

function TerminalStatusBanner({ session, canRetry, restarting, onRetry }) {
  const isCancelled = session.status === 'cancelled';
  const defaultMessage = isCancelled
    ? 'This session was cancelled and will not continue processing.'
    : 'Processing failed for this session.';
  const message = session.error_message || session.last_error || defaultMessage;

  return (
    <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-6 shadow-sm">
      <div className="flex items-start gap-4">
        <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-red-100 flex items-center justify-center">
          <svg className="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-red-900 mb-1">
            {isCancelled ? 'Session cancelled' : 'Processing failed'}
          </h3>
          <p className="text-sm text-red-800 leading-relaxed">{message}</p>
          {session.processing_stage && (
            <p className="text-xs text-red-600 mt-2 font-mono">Stage: {session.processing_stage}</p>
          )}
          <div className="mt-4 flex flex-wrap gap-3">
            {canRetry && (
              <button
                type="button"
                onClick={onRetry}
                disabled={restarting}
                className="inline-flex items-center justify-center h-9 px-4 text-sm font-semibold rounded-lg bg-red-700 text-white hover:bg-red-800 disabled:opacity-60 transition-colors"
              >
                {restarting ? 'Restarting...' : 'Retry processing'}
              </button>
            )}
            <Link
              to="/"
              className="inline-flex items-center justify-center h-9 px-4 text-sm font-semibold rounded-lg bg-white text-slate-800 border border-slate-300 hover:bg-slate-50 transition-colors"
            >
              Back to dashboard
            </Link>
            <Link
              to="/cases/sample"
              className="inline-flex items-center justify-center h-9 px-4 text-sm font-semibold rounded-lg bg-white text-slate-800 border border-slate-300 hover:bg-slate-50 transition-colors"
            >
              View sample case
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

function PendingPanel({ status, title, body }) {
  const isProcessing = status === 'processing';
  const isTerminal = ['cancelled', 'failed', 'error'].includes(status);
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-10">
      <div className="flex flex-col items-center text-center max-w-xl mx-auto">
        <div className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-5 ${
          isProcessing
            ? 'bg-gradient-to-br from-indigo-500 to-purple-600 shadow-md'
            : isTerminal
              ? 'bg-red-100'
              : 'bg-slate-100'
        }`}>
          {isProcessing ? (
            <svg className="w-7 h-7 text-white animate-spin" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" opacity="0.25" />
              <path d="M22 12a10 10 0 00-10-10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          ) : isTerminal ? (
            <svg className="w-7 h-7 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg className="w-7 h-7 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          )}
        </div>
        <h3 className="text-lg font-semibold text-slate-900 mb-2">{title}</h3>
        <p className="text-sm text-slate-600 leading-relaxed">{body}</p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Link
            to="/cases/sample"
            className="inline-flex items-center justify-center h-10 px-4 text-sm font-semibold rounded-lg bg-white text-slate-800 border border-slate-300 hover:bg-slate-50 transition-colors"
          >
            See an example completed case
          </Link>
        </div>
      </div>
    </div>
  );
}

function AnalysisTab({ session, sessionId, artifactUrls, linkedAnalysis, pdfUrl, pdfLoading, pdfError }) {
  if (!isReportAvailableSessionStatus(session.status)) {
    const isProcessing = session.status === 'processing';
    const isTerminal = ['cancelled', 'failed', 'error'].includes(session.status);
    return (
      <PendingPanel
        status={session.status}
        title={
          isTerminal
            ? 'Analysis not available'
            : isProcessing
              ? 'Analysis in progress'
              : 'Analysis not yet started'
        }
        body={
          isTerminal
            ? (session.error_message || 'This session will not produce analysis results. Start a new session or view the sample case.')
            : isProcessing
              ? 'Video review and report cross-check typically take 15–30 minutes for a 20–30 minute CME recording. Report-vs-video findings with deposition timestamps will appear here once processing completes.'
              : 'No analysis has been kicked off for this session yet. Upload the materials and start processing to populate this tab.'
        }
      />
    );
  }

  if (!linkedAnalysis) {
    return (
      <div className="space-y-6">
        <CompletedReportsPanel urls={artifactUrls} sessionId={sessionId} pdfUrl={pdfUrl} pdfLoading={pdfLoading} pdfError={pdfError} />
        <InfoCard
          title="Declared Tests"
          icon="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          items={[{ label: '', value: 'Test declarations detected from audio transcript will appear here.' }]}
        />
        <InfoCard
          title="Observed Actions"
          icon="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
          items={[{ label: '', value: 'Visual analysis of performed tests will appear here.' }]}
        />
        <InfoCard
          title="Discrepancies"
          icon="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          items={[{ label: '', value: 'Mismatches between declared and observed tests will appear here.' }]}
        />
      </div>
    );
  }

  if (artifactUrls.comprehensive_analysis_json || artifactUrls.behavior_summary_json) {
    return (
      <LinkedAnalysisPanel
        urls={artifactUrls}
        summary={session.analysis_summary}
        sessionId={sessionId}
        pdfUrl={pdfUrl}
        pdfLoading={pdfLoading}
        pdfError={pdfError}
      />
    );
  }

  return (
    <div className="space-y-6">
      <CompletedReportsPanel urls={artifactUrls} sessionId={sessionId} pdfUrl={pdfUrl} pdfLoading={pdfLoading} pdfError={pdfError} />
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
        Analysis is marked complete but structured JSON summaries are unavailable. Use the report links above or download the PDF.
      </div>
    </div>
  );
}

async function fetchArtifactJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load analysis (${res.status})`);
  return res.json();
}

const SAMPLE_TEST_LEDGER = '/sample-case/test_ledger.json';
const SAMPLE_CLAIM_VERDICTS = '/sample-case/claim_verdicts.json';
const SAMPLE_CLAIMS_ATOMIC = '/sample-case/claims_atomic.json';
const SAMPLE_NAMED_TEST_INDEX = '/sample-case/named_test_index.json';
const SAMPLE_THREE_WAY_LEDGER = '/sample-case/three_way_ledger.json';
const OSBORNE_SESSION_IDS = new Set(['cme_6f506df9ebf9']);

function resolveSessionVideoUrl(session) {
  const recordings = sortRecordings(session?.recordings || []);
  if (recordings.length) {
    return recordings[0].video_playback_url || session?.video_playback_url || null;
  }
  return session?.video_playback_url || null;
}

async function loadClaimsAtomic({ artifactUrls, sessionId, linkedAnalysis }) {
  if (artifactUrls?.claims_atomic_json) {
    return fetchArtifactJson(artifactUrls.claims_atomic_json);
  }
  if (linkedAnalysis && (OSBORNE_SESSION_IDS.has(sessionId) || artifactUrls?.comprehensive_analysis_json)) {
    const res = await fetch(SAMPLE_CLAIMS_ATOMIC);
    if (res.ok) return res.json();
  }
  return null;
}

async function loadClaimVerdicts({ artifactUrls, sessionId, linkedAnalysis }) {
  if (artifactUrls?.claim_verdicts_json) {
    return fetchArtifactJson(artifactUrls.claim_verdicts_json);
  }
  if (linkedAnalysis && (OSBORNE_SESSION_IDS.has(sessionId) || artifactUrls?.comprehensive_analysis_json)) {
    const res = await fetch(SAMPLE_CLAIM_VERDICTS);
    if (res.ok) return res.json();
  }
  return null;
}

async function loadTestLedger({ artifactUrls, sessionId, linkedAnalysis }) {
  if (artifactUrls?.test_ledger_json) {
    return fetchArtifactJson(artifactUrls.test_ledger_json);
  }
  if (linkedAnalysis && (OSBORNE_SESSION_IDS.has(sessionId) || artifactUrls?.comprehensive_analysis_json)) {
    const res = await fetch(SAMPLE_TEST_LEDGER);
    if (res.ok) return res.json();
  }
  return null;
}

async function loadNamedTestIndex({ artifactUrls, sessionId, linkedAnalysis }) {
  if (artifactUrls?.named_test_index_json) {
    return fetchArtifactJson(artifactUrls.named_test_index_json);
  }
  if (linkedAnalysis && (OSBORNE_SESSION_IDS.has(sessionId) || artifactUrls?.comprehensive_analysis_json)) {
    const res = await fetch(SAMPLE_NAMED_TEST_INDEX);
    if (res.ok) return res.json();
  }
  return null;
}

async function loadThreeWayLedger({ artifactUrls, sessionId, linkedAnalysis }) {
  if (artifactUrls?.three_way_ledger_json) {
    return fetchArtifactJson(artifactUrls.three_way_ledger_json);
  }
  if (linkedAnalysis && (OSBORNE_SESSION_IDS.has(sessionId) || artifactUrls?.comprehensive_analysis_json)) {
    const res = await fetch(SAMPLE_THREE_WAY_LEDGER);
    if (res.ok) return res.json();
  }
  return null;
}

/** Prefer claim_verdicts (report vs video); fall back to test_ledger. */
async function loadTestsTabData({ artifactUrls, sessionId, linkedAnalysis }) {
  const [verdicts, atomicClaims, namedIndex, threeWayLedger] = await Promise.all([
    loadClaimVerdicts({ artifactUrls, sessionId, linkedAnalysis }),
    loadClaimsAtomic({ artifactUrls, sessionId, linkedAnalysis }),
    loadNamedTestIndex({ artifactUrls, sessionId, linkedAnalysis }),
    loadThreeWayLedger({ artifactUrls, sessionId, linkedAnalysis }),
  ]);
  if (Array.isArray(verdicts) && verdicts.length) {
    return { mode: 'claims', verdicts, atomicClaims, namedIndex, threeWayLedger };
  }
  const ledger = await loadTestLedger({ artifactUrls, sessionId, linkedAnalysis });
  if (ledger?.events?.length) {
    return { mode: 'ledger', ledger, namedIndex, threeWayLedger };
  }
  return { mode: 'empty', verdicts: null, ledger: null, atomicClaims: null, namedIndex, threeWayLedger };
}

function TestsTab({ session, sessionId, artifactUrls, linkedAnalysis, initialSeekSec = null }) {
  const [testsData, setTestsData] = useState({
    mode: 'empty',
    verdicts: null,
    ledger: null,
    atomicClaims: null,
    namedIndex: null,
    threeWayLedger: null,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const videoRef = useRef(null);

  const videoUrl = resolveSessionVideoUrl(session);

  const seekVideo = useCallback((sec) => {
    if (!videoRef.current || sec == null) return;
    videoRef.current.currentTime = Math.max(0, sec - 0.25);
    videoRef.current.play().catch(() => {});
  }, []);

  // Apply the ?t= deep-link once the tab data (and thus the <video>) is mounted.
  const deepLinkApplied = useRef(false);
  useEffect(() => {
    if (initialSeekSec == null || deepLinkApplied.current || loading) return undefined;
    const video = videoRef.current;
    if (!video) return undefined;
    deepLinkApplied.current = true;
    const apply = () => {
      video.currentTime = Math.max(0, initialSeekSec - 0.25);
      video.play().catch(() => {});
      video.scrollIntoView({ behavior: 'smooth', block: 'center' });
    };
    if (video.readyState >= 1) {
      apply();
      return undefined;
    }
    video.addEventListener('loadedmetadata', apply, { once: true });
    return () => video.removeEventListener('loadedmetadata', apply);
  }, [initialSeekSec, loading]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const data = await loadTestsTabData({ artifactUrls, sessionId, linkedAnalysis });
        if (!cancelled) setTestsData(data);
      } catch (err) {
        if (!cancelled) setError(err.message || 'Could not load tests data.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [artifactUrls, sessionId, linkedAnalysis]);

  if (!linkedAnalysis && !isReportAvailableSessionStatus(session.status)) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <h3 className="text-base font-semibold text-slate-900 mb-2">Report vs video available after analysis</h3>
        <p className="text-sm text-slate-600 max-w-md mx-auto">
          Once processing completes, each statement from the insurance doctor&apos;s report will be checked against the deposition video with clickable timestamps.
        </p>
      </div>
    );
  }

  const threeWayBlock = (
    <ThreeWayTestIndex
      namedIndex={testsData.namedIndex}
      threeWayLedger={testsData.threeWayLedger}
      onSeek={seekVideo}
      loading={loading}
      error={error}
    />
  );

  if (testsData.mode === 'claims') {
    return (
      <div className="space-y-6">
        {threeWayBlock}
        <ClaimVerdictIndex
          verdicts={testsData.verdicts}
          atomicClaims={testsData.atomicClaims}
          threeWayLedger={testsData.threeWayLedger}
          sessionId={sessionId}
          videoUrl={videoUrl}
          loading={loading}
          error={error}
          emptyMessage="Claim verdicts not found. Run scripts/extract_report_claims.py and scripts/run_claim_verifier.py, then link artifacts."
          videoRef={videoRef}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {threeWayBlock}
      <OrthopedicTestIndex
        ledger={testsData.ledger}
        videoUrl={videoUrl}
        loading={loading}
        error={error}
        emptyMessage="Test ledger not found. Run scripts/build_test_ledger.py and link artifacts to this session."
      />
    </div>
  );
}

function LinkedAnalysisPanel({ urls, summary, sessionId, pdfUrl, pdfLoading, pdfError }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [comprehensive, behavior] = await Promise.all([
          urls.comprehensive_analysis_json
            ? fetchArtifactJson(urls.comprehensive_analysis_json)
            : Promise.resolve(null),
          urls.behavior_summary_json
            ? fetchArtifactJson(urls.behavior_summary_json)
            : Promise.resolve(null),
        ]);
        if (!cancelled) setData({ comprehensive, behavior });
      } catch (err) {
        if (!cancelled) setError(err.message || 'Could not load analysis data.');
      }
    })();
    return () => { cancelled = true; };
  }, [urls.comprehensive_analysis_json, urls.behavior_summary_json]);

  if (error) {
    return (
      <div className="space-y-4">
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">
          {error} Refresh the page to request fresh download links from the server.
        </div>
        <CompletedReportsPanel urls={urls} sessionId={sessionId} pdfUrl={pdfUrl} pdfLoading={pdfLoading} pdfError={pdfError} />
      </div>
    );
  }
  if (!data) {
    return <div className="h-48 rounded-2xl shimmer" />;
  }

  const { comprehensive, behavior } = data;
  const behaviorIssues = (behavior && behavior.behavior_issues) || [];
  const techniqueIssues = (comprehensive && comprehensive.technique_issues) || [];

  return (
    <div className="space-y-6">
      {summary && (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50/80 px-5 py-4 text-sm text-emerald-900">
          Linked analysis for {summary.plaintiff_name || 'patient'}
          {summary.exam_date && ` · CME ${summary.exam_date}`}
          {summary.cost_usd != null && ` · $${Number(summary.cost_usd).toFixed(2)} actual cost`}
        </div>
      )}
      <CompletedReportsPanel urls={urls} sessionId={sessionId} pdfUrl={pdfUrl} pdfLoading={pdfLoading} pdfError={pdfError} />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <HighlightCard
          label="Doctor attention"
          value={
            behaviorIssues.find((b) => (b.category || '').toUpperCase() === 'INATTENTION')
              ? 'Low eye contact'
              : behavior?.eye_contact_score != null
                ? `${Math.round(behavior.eye_contact_score)}% eye contact`
                : '—'
          }
          detail="Supplemental behavior review — not the primary report crosswalk."
          tone="rose"
        />
        <HighlightCard
          label="Examination quality"
          value={`${comprehensive?.examination_quality_score ?? 0}/100`}
          detail={`Professionalism ${comprehensive?.professionalism_score ?? 0}/100`}
          tone="amber"
        />
        <HighlightCard
          label="Issues identified"
          value={String((techniqueIssues?.length || 0) + behaviorIssues.length)}
          detail={`${techniqueIssues?.length || 0} technique · ${behaviorIssues.length} behavior`}
          tone="indigo"
        />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <InfoCard
          title="Technique issues (sample)"
          icon="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          items={(techniqueIssues || []).slice(0, 8).map((t) => ({
            label: (t.issue || '').replace(/_/g, ' '),
            value: `${t.severity || ''}${t.timestamp_sec != null ? ` @ ${Math.round(t.timestamp_sec)}s` : ''}`,
          }))}
        />
        <InfoCard
          title="Behavior issues (sample)"
          icon="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
          items={behaviorIssues.slice(0, 8).map((b) => ({
            label: (b.category || '').toString().replace(/BehaviorSeverity\./i, ''),
            value: b.description || '',
          }))}
        />
      </div>
    </div>
  );
}

function HighlightCard({ label, value, detail, tone }) {
  const toneClass =
    tone === 'rose'
      ? 'from-rose-50 to-rose-100 border-rose-200'
      : tone === 'amber'
        ? 'from-amber-50 to-amber-100 border-amber-200'
        : 'from-indigo-50 to-purple-100 border-indigo-200';
  return (
    <div className={`rounded-xl border bg-gradient-to-br ${toneClass} p-5 shadow-sm`}>
      <div className="text-[11px] font-semibold uppercase tracking-wide opacity-70 mb-1">{label}</div>
      <div className="text-2xl font-semibold tracking-tight text-slate-900">{value}</div>
      <div className="text-xs mt-2 opacity-80 text-slate-700">{detail}</div>
    </div>
  );
}

function CompletedReportsPanel({ urls, sessionId, pdfUrl, pdfLoading, pdfError }) {
  const html = urls.standard_report_html;
  const pdf = pdfUrl || urls.standard_report_pdf;
  const dashboard = urls.behavior_dashboard_html;
  if (!html && !pdf && !dashboard && !pdfLoading) return null;

  return (
    <div className="space-y-6">
      {(pdf || pdfLoading) && (
        <PdfReportPanel pdfUrl={pdf} loading={pdfLoading} error={pdfError} showEmbed={false} />
      )}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
      <h3 className="text-base font-bold text-slate-900 mb-4">Reports & dashboards</h3>
      <div className="flex flex-wrap gap-3">
        {html && (
          <a
            href={html}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center h-10 px-4 text-sm font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
          >
            Standard report (HTML)
          </a>
        )}
        {pdf && <PdfDownloadButton pdfUrl={pdf} size="md" />}
        {dashboard && (
          <a
            href={dashboard}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center h-10 px-4 text-sm font-semibold rounded-lg bg-white text-slate-800 border border-slate-300 hover:bg-slate-50 transition-colors"
          >
            Behavior dashboard
          </a>
        )}
        {sessionId && html && (
          <p className="w-full text-xs text-slate-500 font-mono mt-2">
            Session {sessionId} · artifacts in S3 cme-reports/
          </p>
        )}
      </div>
      {html && (
        <div className="mt-6 rounded-xl border border-slate-200 overflow-hidden bg-slate-50">
          <iframe title="Standard CME report" src={html} className="w-full h-[min(70vh,720px)] bg-white" />
        </div>
      )}
      </div>
    </div>
  );
}

function TimelineTab({ session, artifactUrls, linkedAnalysis, pdfUrl, pdfLoading, pdfError }) {
  const reportHtml = artifactUrls.standard_report_html;
  const pdf = pdfUrl || artifactUrls.standard_report_pdf;
  if (linkedAnalysis && reportHtml) {
    return (
      <div className="space-y-4">
        {(pdf || pdfLoading) && (
          <PdfReportPanel pdfUrl={pdf} loading={pdfLoading} error={pdfError} showEmbed={false} />
        )}
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
          <h3 className="text-base font-semibold text-slate-900 mb-2">Examination timeline</h3>
          <p className="text-sm text-slate-600 mb-4">
            Chronological findings are embedded in the standard CME report below.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            {pdf && <PdfDownloadButton pdfUrl={pdf} size="sm" />}
            <a
              href={reportHtml}
              target="_blank"
              rel="noreferrer"
              className="text-sm font-semibold text-indigo-600 hover:text-indigo-800"
            >
              Open full report in new tab
            </a>
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 overflow-hidden bg-slate-50">
          <iframe title="Timeline via standard report" src={reportHtml} className="w-full h-[min(60vh,600px)] bg-white" />
        </div>
      </div>
    );
  }
  if (!isReportAvailableSessionStatus(session.status)) {
    const isProcessing = session.status === 'processing';
    const isTerminal = ['cancelled', 'failed', 'error'].includes(session.status);
    return (
      <PendingPanel
        status={session.status}
        title={
          isTerminal
            ? 'Timeline not available'
            : isProcessing
              ? 'Timeline being built'
              : 'Timeline not yet available'
        }
        body={
          isTerminal
            ? 'No timeline was generated for this session.'
            : isProcessing
              ? 'The chronological timeline is built from timestamped observations during video review. It will appear here once the run completes.'
              : 'The timeline view is generated alongside the analysis once processing has been started and completed.'
        }
      />
    );
  }
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-10 text-center">
      <h3 className="text-base font-semibold text-slate-900 mb-2">Timeline view</h3>
      <p className="text-sm text-slate-600 max-w-md mx-auto">
        A chronological timeline of the examination is generated after processing.
      </p>
    </div>
  );
}

function formatBytes(n) {
  if (n == null || !Number.isFinite(Number(n))) return null;
  const b = Number(n);
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1024 * 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MB`;
  return `${(b / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatTimestamp(ts) {
  if (!ts) return null;
  const d = new Date(Number(ts) * 1000);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString();
}

function RecordingTab({ session, linkedAnalysis, metrics, canEdit, hasRecordings, uploading, onUploadReport, onUploadVideos, onStartProcessing }) {
  const [pendingVideos, setPendingVideos] = useState([]);

  const recordings = useMemo(() => {
    const raw = session.recordings;
    if (raw && raw.length) return sortRecordings(raw);
    if (session.video_uri) {
      return [{ uri: session.video_uri, filename: 'recording.mp4', display_label: 'Video 1' }];
    }
    return [];
  }, [session.recordings, session.video_uri]);

  const onVideoFilesChosen = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setPendingVideos([{
        key: `${file.name}-${Date.now()}`,
        file,
        slot: 1,
      }]);
    }
    e.target.value = '';
  };

  const removePending = (key) => {
    setPendingVideos((rows) => rows.filter((r) => r.key !== key));
  };

  const submitPendingVideos = async () => {
    if (!pendingVideos.length) return;
    await onUploadVideos(pendingVideos.map(({ file, slot }) => ({ file, slot })));
    setPendingVideos([]);
  };

  const dr = session.doctor_report;
  const hasDr = hasDoctorReport(session);

  return (
    <div className="space-y-8">
      {hasDr && (
        <div className="bg-white rounded-2xl shadow-lg border border-emerald-300 p-8 ring-1 ring-emerald-100">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900">Defense examiner report (original)</h2>
              <p className="text-sm text-slate-600">
                The defense doctor&apos;s written CME report provided for this case.
              </p>
            </div>
          </div>
          <DoctorReportPanel doctorReport={dr} />
        </div>
      )}

      {linkedAnalysis && (
        <div className="bg-white rounded-2xl shadow-lg border border-emerald-200 p-8">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900">Linked analysis materials</h2>
              <p className="text-sm text-slate-600">
                This session uses a completed linked analysis run — no new uploads are required.
              </p>
            </div>
          </div>
          <dl className="grid sm:grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Plaintiff (analysis)</dt>
              <dd className="text-slate-900 mt-1">{metrics?.plaintiff || '—'}</dd>
            </div>
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Examiner (analysis)</dt>
              <dd className="text-slate-900 mt-1">{metrics?.examiner || '—'}</dd>
            </div>
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Exam date (video)</dt>
              <dd className="text-slate-900 mt-1">{metrics?.examDate || session?.exam_date || '—'}</dd>
            </div>
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Source run</dt>
              <dd className="text-slate-900 mt-1 font-mono text-xs">{metrics?.linkedFrom || '—'}</dd>
            </div>
          </dl>
        </div>
      )}

      <div className="bg-white rounded-2xl shadow-lg border border-slate-200 p-8">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-gradient-to-br from-slate-600 to-slate-800 rounded-xl">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">Doctor's written report</h2>
            <p className="text-sm text-slate-600">Upload the defense examiner's CME report (PDF or Word).</p>
          </div>
        </div>
        {hasDr ? (
          <div className="mb-4">
            <DoctorReportPanel
              doctorReport={dr}
              title={dr.filename || 'Report on file'}
              subtitle={dr.label || undefined}
            />
          </div>
        ) : (
          <p className="text-sm text-slate-500 mb-4">No report uploaded yet.</p>
        )}
        {canEdit && (
          <label className="inline-flex items-center gap-2 px-5 py-2.5 bg-slate-800 text-white text-sm font-semibold rounded-xl cursor-pointer hover:bg-slate-900 transition-colors">
            {uploading ? 'Working…' : hasDr ? 'Replace report' : 'Upload report'}
            <input
              type="file"
              accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="hidden"
              disabled={uploading}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onUploadReport(f);
                e.target.value = '';
              }}
            />
          </label>
        )}
      </div>

      <div className="bg-white rounded-2xl shadow-lg border border-slate-200 p-8">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">CME recordings</h2>
            <p className="text-sm text-slate-600">
              One combined recording is supported per live case. Uploading a new file replaces Video 1 before processing starts.
            </p>
          </div>
        </div>

        {recordings.length > 0 ? (
          <ul className="space-y-4 mb-6">
            {recordings.map((rec, idx) => {
              const playbackUrl = rec.video_playback_url || session.video_playback_url;
              const slotLabel = rec.display_label || `Video ${rec.recording_slot != null ? rec.recording_slot : idx + 1}`;
              return (
                <li
                  key={`${rec.s3_key || rec.uri}-${idx}`}
                  className="rounded-xl border border-slate-200 bg-slate-50/80 overflow-hidden"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-b border-slate-200/80 bg-white/60">
                    <span className="text-sm font-semibold text-indigo-700">{slotLabel}</span>
                    <span className="text-sm text-slate-700">{rec.filename || 'recording'}</span>
                    {rec.file_size != null && (
                      <span className="text-xs text-slate-500">{formatBytes(rec.file_size)}</span>
                    )}
                    {rec.uploaded_at && (
                      <span className="text-xs text-slate-500">{formatTimestamp(rec.uploaded_at)}</span>
                    )}
                  </div>
                  {playbackUrl ? (
                    <div className="p-4 bg-black">
                      <video
                        controls
                        preload="metadata"
                        className="w-full max-h-[min(60vh,480px)] rounded-lg bg-black"
                        src={playbackUrl}
                      >
                        Your browser does not support HTML5 video playback.
                      </video>
                    </div>
                  ) : (
                    <p className="px-4 py-3 text-xs font-mono text-slate-500 truncate">{rec.uri || rec.s3_key}</p>
                  )}
                </li>
              );
            })}
          </ul>
        ) : linkedAnalysis ? (
          <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 mb-6">
            Analysis is linked but no recording is attached yet. Refresh after the session bundle script completes.
          </p>
        ) : (
          <p className="text-sm text-slate-500 mb-6">No recording yet. Add one video or audio file below.</p>
        )}

        {canEdit && (
          <>
            <div className="border border-dashed border-slate-300 rounded-xl p-4 mb-4">
              <p className="text-sm text-slate-600 mb-3">Choose one combined recording. Selecting a new file replaces the pending upload.</p>
              <label className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg cursor-pointer hover:bg-blue-700">
                Choose recording
                <input
                  type="file"
                  accept="video/*,audio/*,.mp4,.mov,.m4v,.webm,.mp3,.m4a,.wav,.flac,.ogg,.amr"
                  className="hidden"
                  disabled={uploading}
                  onChange={onVideoFilesChosen}
                />
              </label>
            </div>

            {pendingVideos.length > 0 && (
              <div className="mb-4 overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-500 border-b border-slate-200">
                      <th className="py-2 pr-4">File</th>
                      <th className="py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {pendingVideos.map((row) => (
                      <tr key={row.key} className="border-b border-slate-100">
                        <td className="py-2 pr-4 max-w-xs truncate">{row.file.name}</td>
                        <td className="py-2">
                          <button type="button" onClick={() => removePending(row.key)} className="text-red-600 hover:underline">
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <button
                  type="button"
                  disabled={uploading}
                  onClick={submitPendingVideos}
                  className="mt-4 px-6 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-semibold rounded-xl disabled:opacity-50"
                >
                  {uploading ? 'Uploading...' : 'Upload recording'}
                </button>
              </div>
            )}
          </>
        )}

        {!canEdit && hasRecordings && (
          <p className="text-sm text-slate-500">Processing has started or finished; uploads are closed for this session.</p>
        )}
      </div>

      {canEdit && hasRecordings && (
        <div className="bg-white rounded-2xl shadow-lg border border-slate-200 p-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">Start analysis</h3>
            <p className="text-sm text-slate-600 mt-1">
              Run transcription and the analysis pipeline after all videos (and optional report) are uploaded.
            </p>
          </div>
          <button
            type="button"
            onClick={onStartProcessing}
            className="px-8 py-3 bg-gradient-to-r from-emerald-600 to-teal-600 text-white text-sm font-semibold rounded-xl shadow-lg hover:shadow-xl transition-all"
          >
            Start processing
          </button>
        </div>
      )}
    </div>
  );
}

function InfoCard({ title, icon, items }) {
  return (
    <div className="bg-white rounded-2xl shadow-lg border border-slate-200 p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl">
          <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={icon} />
          </svg>
        </div>
        <h3 className="text-lg font-bold text-slate-900">{title}</h3>
      </div>
      <dl className="space-y-4">
        {items.map((item, index) => (
          <div key={index}>
            {item.label && <dt className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">{item.label}</dt>}
            <dd className={`text-sm text-slate-900 ${item.mono ? 'font-mono text-xs bg-slate-50 p-2 rounded-lg' : ''}`}>
              {item.value || '—'}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
