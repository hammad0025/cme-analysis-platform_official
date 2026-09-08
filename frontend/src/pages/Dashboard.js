import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import Button from '../components/Button';
import StatusBadge from '../components/case/StatusBadge';
import { caseDetailPath } from '../lib/caseRoutes';
import { isReportAvailableSessionStatus } from '../lib/caseConstants';
import { listCases, isMockMode } from '../services/casesService';

export default function Dashboard() {
  const navigate = useNavigate();
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const { cases: list, source: src, error: err } = await listCases();
        if (cancelled) return;
        setCases(list);
        setSource(src);
        if (err) setError('Live API unavailable. Showing local cases only.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const stats = useMemo(() => ({
    total: cases.length,
    processing: cases.filter((c) => ['processing', 'uploading', 'recording_uploaded'].includes(c.status)).length,
    completed: cases.filter((c) => isReportAvailableSessionStatus(c.status)).length,
  }), [cases]);

  const sourceLabel = {
    mock: 'Local cases only',
    'mock-fallback': 'Live API unreachable — local cases shown',
    live: 'Synced with live API',
  }[source] || '';

  return (
    <>
      <Hero stats={stats} isEmpty={!loading && cases.length === 0} />

      {error && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 flex items-start gap-3"
        >
          <svg className="w-5 h-5 flex-shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {error}
        </motion.div>
      )}

      <div className="mt-10 flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Your cases</h2>
          <p className="text-sm text-slate-500 mt-1">{sourceLabel}</p>
        </div>
        <Link to="/cases/new">
          <Button variant="primary" size="md">
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            New case
          </Button>
        </Link>
      </div>

      {loading ? (
        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-44 rounded-2xl shimmer" />
          ))}
        </div>
      ) : cases.length === 0 ? (
        <EmptyState onNew={() => navigate('/cases/new')} source={source} />
      ) : (
        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {cases.map((c, i) => (
            <CaseCard key={`${c.case_id}-${c.is_mock ? 'm' : 'l'}`} caseData={c} index={i} />
          ))}
        </div>
      )}

      {isMockMode() && (
        <p className="mt-8 text-center text-xs text-slate-400">
          Mock mode — cases persist in this browser until reset from the sidebar or site data is cleared.
        </p>
      )}
    </>
  );
}

function Hero({ stats, isEmpty }) {
  return (
    <section className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-gradient-to-br from-slate-900 via-indigo-950 to-purple-950 shadow-2xl">
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-32 -right-32 w-96 h-96 rounded-full bg-indigo-500/30 blur-3xl animate-blob" />
        <div className="absolute -bottom-32 -left-32 w-96 h-96 rounded-full bg-purple-600/25 blur-3xl animate-blob animation-delay-2000" />
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: 'radial-gradient(circle at 1px 1px, white 1px, transparent 0)',
            backgroundSize: '24px 24px',
          }}
        />
      </div>
      <div className="relative p-8 sm:p-10 lg:p-12">
        <div className="grid lg:grid-cols-5 gap-8 items-center">
          <div className="lg:col-span-3">
            <div className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-indigo-300 mb-4">
              <span className="w-8 h-px bg-indigo-400/50" />
              CME Analysis Platform
            </div>
            {isEmpty ? (
              <div className="inline-flex items-center gap-2 rounded-full bg-emerald-500/20 border border-emerald-400/30 px-3 py-1 text-xs font-semibold text-emerald-200 mb-4">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                Fresh start — no cases on file
              </div>
            ) : null}
            <h1 className="text-3xl sm:text-4xl font-bold text-white tracking-tight leading-tight">
              {isEmpty ? 'Your workspace is clear.' : 'Defense-side CME scrutiny, structured for trial.'}
            </h1>
            <p className="mt-4 text-indigo-100/90 text-sm sm:text-base max-w-2xl leading-relaxed">
              {isEmpty
                ? 'Live sessions and local demo cases have been cleared. Start with a new case upload or open the offline sample to preview deliverables.'
                : 'Upload examination videos and the insurance doctor\'s written report. The platform compares what the doctor documented to what the video shows — with deposition timestamps you can cite in cross-examination.'}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/cases/new">
                <Button variant="primary" size="lg">Start a new case</Button>
              </Link>
              <Link to="/cases/sample">
                <Button variant="secondary" size="lg">View sample case</Button>
              </Link>
            </div>
          </div>
          <div className="lg:col-span-2 grid grid-cols-3 gap-3">
            <StatTile label="Total cases" value={stats.total} />
            <StatTile label="In progress" value={stats.processing} accent="amber" />
            <StatTile label="Completed" value={stats.completed} accent="emerald" />
          </div>
        </div>
      </div>
    </section>
  );
}

function StatTile({ label, value, accent }) {
  const accentCls = { amber: 'text-amber-300', emerald: 'text-emerald-300' }[accent] || 'text-indigo-200';
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl px-4 py-4 backdrop-blur-sm hover:bg-white/10 transition-colors">
      <div className="text-[10px] font-bold uppercase tracking-wider text-white/50">{label}</div>
      <div className={`text-3xl font-bold mt-1 tabular-nums ${accentCls}`}>{value}</div>
    </div>
  );
}

function CaseCard({ caseData, index }) {
  const navigate = useNavigate();
  const target = caseDetailPath(caseData);
  const plaintiff = caseData.plaintiff_name || caseData.patient_name || 'Unnamed plaintiff';
  const examiner = caseData.examiner_name || caseData.doctor_name || 'Examiner pending';

  return (
    <motion.button
      type="button"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.25 }}
      onClick={() => navigate(target)}
      className="group text-left w-full rounded-2xl border border-slate-200 bg-white p-5 shadow-sm hover:shadow-lg hover:border-indigo-200 hover:-translate-y-0.5 transition-all duration-200"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white flex items-center justify-center text-sm font-bold shadow-sm">
          {plaintiff.charAt(0).toUpperCase()}
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <StatusBadge status={caseData.status} />
          {caseData.is_mock && (
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
              local
            </span>
          )}
        </div>
      </div>

      <h3 className="text-base font-bold text-slate-900 truncate group-hover:text-indigo-700 transition-colors">
        {plaintiff}
      </h3>
      <p className="text-sm text-slate-600 mt-1 truncate">{examiner}</p>

      <div className="mt-4 pt-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
        <span>{caseData.exam_date ? `Exam ${caseData.exam_date}` : 'Date pending'}</span>
        <span className="font-mono text-[10px] text-slate-400 truncate max-w-[8rem]">{caseData.case_id}</span>
      </div>

      <div className="mt-3 flex items-center gap-1 text-xs font-medium text-indigo-600 opacity-0 group-hover:opacity-100 transition-opacity">
        Open case
        <svg className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </div>
    </motion.button>
  );
}

function EmptyState({ onNew, source }) {
  const liveEmpty = source === 'live' || source === 'mock-fallback';
  return (
    <div className="mt-6 rounded-2xl border-2 border-dashed border-emerald-200/80 bg-gradient-to-b from-white to-emerald-50/30 p-12 sm:p-16 text-center">
      <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/20">
        <svg className="w-8 h-8 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <h3 className="mt-6 text-lg font-bold text-slate-900">Fresh start</h3>
      <p className="mt-2 text-sm text-slate-500 max-w-md mx-auto leading-relaxed">
        {liveEmpty
          ? 'No sessions in the live API — the dashboard is empty. Create your first case or preview the offline sample report.'
          : 'No local mock cases saved. Create your first case or preview the offline sample report.'}
      </p>
      <div className="mt-8 flex items-center justify-center gap-3 flex-wrap">
        <Button variant="primary" size="md" onClick={onNew}>Start a new case</Button>
        <Link to="/cases/sample">
          <Button variant="secondary" size="md">View sample case</Button>
        </Link>
      </div>
    </div>
  );
}
