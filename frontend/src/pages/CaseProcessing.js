import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import Button from '../components/Button';
import StatusBadge from '../components/case/StatusBadge';
import ProcessingTimeline from '../components/case/ProcessingTimeline';
import {
  formatBytes,
  isFailedSessionStatus,
  isReportAvailableSessionStatus,
  isTerminalSessionStatus,
  reportLabel,
  timelineStageForSession,
} from '../lib/caseConstants';
import { getMockCase, isMockMode } from '../services/casesService';
import api from '../services/cmeApi';

const POLL_INTERVAL_MS = 10000;

export default function CaseProcessing() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const [caseData, setCaseData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const pollRef = useRef(null);

  useEffect(() => {
    const mock = getMockCase(caseId);
    if (mock) {
      setCaseData({ ...mock, source: 'mock' });
      setLoading(false);
      return undefined;
    }
    if (isMockMode()) {
      setError('We could not find that case in this browser session.');
      setLoading(false);
      return undefined;
    }

    let cancelled = false;

    const fetchSession = async () => {
      try {
        const res = await api.get(`/cme/sessions/${caseId}`);
        const s = res.data?.session || res.data || {};
        if (cancelled) return;
        if (isReportAvailableSessionStatus(s.status)) {
          navigate(`/sessions/${caseId}`, { replace: true });
          return;
        }
        setCaseData({
          case_id: caseId,
          plaintiff_name: s.patient_name || s.plaintiff_name,
          examiner_name: s.doctor_name || s.examiner_name,
          exam_date: s.exam_date,
          date_of_injury: s.date_of_injury,
          date_of_birth: s.date_of_birth,
          status: s.status,
          processing_stage: s.processing_stage,
          processing_started_at: s.processing_started_at,
          last_error: s.last_error,
          video: s.doctor_report ? null : undefined,
          videos: s.recordings || [],
          reports: s.doctor_report ? [s.doctor_report] : [],
          source: 'live',
        });
        setError('');
        // Stop polling once the session reaches a terminal state.
        if (isTerminalSessionStatus(s.status) && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch (err) {
        if (cancelled) return;
        // Only surface load errors when we have nothing to show; transient
        // poll failures should not blow away the page.
        setCaseData((prev) => {
          if (!prev) {
            setError(err.response?.data?.error || err.message || 'Could not load case.');
          }
          return prev;
        });
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchSession();
    pollRef.current = setInterval(fetchSession, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [caseId, navigate]);

  const expectedFinish = useMemo(() => {
    if (!caseData?.processing_started_at) return null;
    try {
      const started = new Date(caseData.processing_started_at);
      return new Date(started.getTime() + 30 * 60 * 1000).toLocaleString();
    } catch (_) {
      return null;
    }
  }, [caseData]);

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="h-40 rounded-2xl shimmer" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 h-64 rounded-2xl shimmer" />
          <div className="h-64 rounded-2xl shimmer" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-lg mx-auto mt-12">
          <div className="rounded-2xl border border-slate-200 bg-white shadow-xl p-10 text-center">
            <div className="w-14 h-14 mx-auto rounded-2xl bg-rose-100 text-rose-600 flex items-center justify-center mb-5">
              <svg className="w-7 h-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-slate-900 mb-2">Case not found</h1>
            <p className="text-sm text-slate-600 mb-8 leading-relaxed">{error}</p>
            <div className="flex items-center justify-center gap-3">
              <Button variant="secondary" size="md" onClick={() => navigate('/')}>Back to dashboard</Button>
              <Link to="/cases/new"><Button variant="primary" size="md">New case</Button></Link>
            </div>
          </div>
      </div>
    );
  }

  const videos = caseData.videos?.length
    ? caseData.videos
    : caseData.video
    ? [caseData.video]
    : [];

  const reports = caseData.reports || [];
  const failed = isFailedSessionStatus(caseData.status);
  const currentStage = timelineStageForSession(caseData);

  return (
    <div className="max-w-5xl mx-auto">
      <motion.header
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-gradient-to-br from-slate-900 via-indigo-950 to-purple-950 shadow-2xl"
      >
        <div className="absolute inset-0 pointer-events-none">
            <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/20 rounded-full blur-3xl" />
          </div>
          <div className="relative p-6 sm:p-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="mb-3">
                  <StatusBadge status={caseData.status || 'processing'} className="!bg-amber-500/10 !text-amber-200 !ring-amber-400/30" />
                </div>
                <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
                  {caseData.plaintiff_name || 'New case'}
                </h1>
                <p className="mt-2 text-sm text-indigo-100/80">
                  {caseData.examiner_name || 'Examiner pending'} · CME on {caseData.exam_date || 'TBD'}
                </p>
              </div>
              <div className="text-right">
                <div className="text-[10px] font-bold uppercase tracking-wider text-indigo-300/70">Case ID</div>
                <div className="font-mono text-sm text-white/90 mt-0.5">{caseData.case_id}</div>
              </div>
            </div>

            <div className="mt-6 grid sm:grid-cols-3 gap-3">
              <MetricPill icon="clock" label="Expected time" value="15–30 minutes" />
              <MetricPill icon="video" label="Videos" value={String(videos.length || '—')} />
              <MetricPill icon="doc" label="Reports" value={String(reports.length || '—')} />
            </div>

            {expectedFinish && (
              <p className="mt-4 text-xs text-indigo-200/70">
                Earliest expected delivery: {expectedFinish}
              </p>
            )}
          </div>
        </motion.header>

        {failed && (
          <div className="mt-6 rounded-2xl border border-rose-200 bg-rose-50 p-5">
            <div className="flex items-start gap-3">
              <svg className="w-5 h-5 text-rose-500 mt-0.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <h2 className="text-sm font-bold text-rose-800">Processing failed</h2>
                <p className="text-sm text-rose-700 mt-1 leading-relaxed">
                  {caseData.last_error
                    ? caseData.last_error
                    : 'The pipeline hit an error and stopped. Your uploads are safe — contact support or retry processing.'}
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <ProcessingTimeline currentStage={currentStage} failed={failed} />

            <div className="rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50/80 to-purple-50/60 p-6">
              <div className="flex items-start justify-between flex-wrap gap-4">
                <div>
                  <h2 className="text-base font-bold text-slate-900 mb-1">
                    Preview the finished deliverable
                  </h2>
                  <p className="text-sm text-slate-600 leading-relaxed max-w-lg">
                    The Osborne 2021 sample demonstrates the exact report, behavior dashboard, and timestamped findings you will receive when processing completes.
                  </p>
                </div>
                <Link to="/cases/sample">
                  <Button variant="primary" size="md">View sample case</Button>
                </Link>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <DetailsCard caseData={caseData} />
            <MaterialsCard videos={videos} reports={reports} />
          </div>
        </div>

        {caseData.source === 'mock' && (
          <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500 flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
            Mock mode — this case lives only in your browser until site data is cleared.
          </div>
        )}
    </div>
  );
}

function MetricPill({ icon, label, value }) {
  const icons = {
    clock: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
    video: 'M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z',
    doc: 'M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z',
  };
  return (
    <div className="rounded-xl bg-white/5 border border-white/10 px-4 py-3 backdrop-blur-sm">
      <div className="flex items-center gap-2 text-indigo-200/70">
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}>
          <path strokeLinecap="round" strokeLinejoin="round" d={icons[icon]} />
        </svg>
        <span className="text-[10px] font-bold uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-lg font-bold text-white mt-1">{value}</div>
    </div>
  );
}

function DetailsCard({ caseData }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-4">Case details</h2>
      <dl className="space-y-3">
        <DetailRow label="Plaintiff" value={caseData.plaintiff_name} />
        <DetailRow label="Examiner" value={caseData.examiner_name} />
        <DetailRow label="Exam date" value={caseData.exam_date} />
        <DetailRow label="Date of injury" value={caseData.date_of_injury} />
        <DetailRow label="Date of birth" value={caseData.date_of_birth} />
      </dl>
    </div>
  );
}

function MaterialsCard({ videos, reports }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-4">Submitted materials</h2>
      <div className="space-y-2.5">
        {videos.length === 0 && reports.length === 0 && (
          <p className="text-xs text-slate-500">Materials queued for processing.</p>
        )}
        {videos.map((v, i) => (
          <MaterialRow
            key={v.file_key || v.s3_key || i}
            kind="video"
            title={v.label || v.display_label || v.filename || `Video ${v.recording_slot || i + 1}`}
            subtitle={v.size || v.file_size ? formatBytes(v.size || v.file_size) : 'Uploaded'}
          />
        ))}
        {reports.map((r, i) => (
          <MaterialRow
            key={r.file_key || r.s3_key || i}
            kind="pdf"
            title={r.filename}
            subtitle={`${reportLabel(r.tag) || 'Document'}${r.size || r.file_size ? ` · ${formatBytes(r.size || r.file_size)}` : ''}`}
          />
        ))}
      </div>
    </div>
  );
}

function MaterialRow({ kind, title, subtitle }) {
  const isVideo = kind === 'video';
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2.5">
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
        isVideo ? 'bg-indigo-100 text-indigo-600' : 'bg-purple-100 text-purple-600'
      }`}>
        {isVideo ? (
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
        ) : (
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
        )}
      </div>
      <div className="min-w-0">
        <div className="text-sm font-medium text-slate-900 truncate" title={title}>{title}</div>
        <div className="text-xs text-slate-500">{subtitle}</div>
      </div>
    </div>
  );
}

function DetailRow({ label, value }) {
  return (
    <div className="flex items-center justify-between text-sm gap-4">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-slate-900 text-right capitalize">{value || '—'}</span>
    </div>
  );
}
