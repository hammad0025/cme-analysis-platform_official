import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Button from '../components/Button';
import ClaimVerdictIndex from '../components/case/ClaimVerdictIndex';
import OrthopedicTestIndex from '../components/case/OrthopedicTestIndex';

const SAMPLE = '/sample-case';

const fetchJSON = async (path) => {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path} (HTTP ${res.status})`);
  return res.json();
};

export default function SampleCase() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('tests'); // tests | overview | report | dashboard

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [manifest, comprehensive, behavior, testLedger, claimVerdicts, claimsAtomic] = await Promise.all([
          fetchJSON(`${SAMPLE}/MANIFEST.json`),
          fetchJSON(`${SAMPLE}/comprehensive_analysis.json`),
          fetchJSON(`${SAMPLE}/behavior_summary.json`),
          fetchJSON(`${SAMPLE}/test_ledger.json`).catch(() => null),
          fetchJSON(`${SAMPLE}/claim_verdicts.json`).catch(() => null),
          fetchJSON(`${SAMPLE}/claims_atomic.json`).catch(() => null),
        ]);
        if (!cancelled) setData({ manifest, comprehensive, behavior, testLedger, claimVerdicts, claimsAtomic });
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load sample case.');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div className="max-w-2xl mx-auto bg-white border border-rose-200 rounded-2xl p-8 shadow-sm">
          <h1 className="text-lg font-semibold text-slate-900 mb-2">Could not load sample case</h1>
          <p className="text-sm text-slate-600 mb-4">{error}</p>
          <p className="text-xs text-slate-500">
            Make sure <code className="font-mono">frontend/public/sample-case/</code> is populated and the dev server is serving static files.
          </p>
        </div>
    );
  }

  if (!data) {
    return <SampleSkeleton />;
  }

  const { manifest, comprehensive, behavior, testLedger, claimVerdicts, claimsAtomic } = data;
  const highlights = buildHighlights({ comprehensive, behavior });

  return (
    <>
      <CaseHeader manifest={manifest} />

      <Highlights items={highlights} />

      <div className="mt-8 bg-white rounded-2xl border border-slate-200 shadow-sm">
        <div className="border-b border-slate-200 px-6 pt-6 pb-0 flex flex-wrap gap-2">
          <TabButton active={activeTab === 'tests'} onClick={() => setActiveTab('tests')}>
            Report vs video
          </TabButton>
          <TabButton active={activeTab === 'overview'} onClick={() => setActiveTab('overview')}>
            Overview
          </TabButton>
          <TabButton active={activeTab === 'report'} onClick={() => setActiveTab('report')}>
            Standard report
          </TabButton>
          <TabButton active={activeTab === 'dashboard'} onClick={() => setActiveTab('dashboard')}>
            Behavior dashboard
          </TabButton>
        </div>
        <div className="p-6 sm:p-8">
          {activeTab === 'tests' && (
            Array.isArray(claimVerdicts) && claimVerdicts.length ? (
              <ClaimVerdictIndex
                verdicts={claimVerdicts}
                atomicClaims={claimsAtomic}
                videoUrl={null}
                emptyMessage="Run scripts/run_claim_verifier.py to generate frontend/public/sample-case/claim_verdicts.json."
              />
            ) : (
              <OrthopedicTestIndex
                ledger={testLedger}
                videoUrl={null}
                emptyMessage="Run scripts/build_test_ledger.py to generate frontend/public/sample-case/test_ledger.json."
              />
            )
          )}
          {activeTab === 'overview' && <OverviewPanel comprehensive={comprehensive} behavior={behavior} />}
          {activeTab === 'report' && (
            <EmbedPanel
              title="Standard CME report"
              src={`${SAMPLE}/standard_report.html`}
              externalLabel="Open in new tab"
              externalHref={`${SAMPLE}/standard_report.html`}
              downloadLabel="Download PDF"
              downloadHref={`${SAMPLE}/standard_report.pdf`}
            />
          )}
          {activeTab === 'dashboard' && (
            <EmbedPanel
              title="Behavior dashboard"
              src={`${SAMPLE}/behavior_dashboard.html`}
              externalLabel="Open in new tab"
              externalHref={`${SAMPLE}/behavior_dashboard.html`}
            />
          )}
        </div>
      </div>

      <RunMetadata manifest={manifest} />
    </>
  );
}

function buildHighlights({ comprehensive, behavior }) {
  const behaviorIssues = (behavior && behavior.behavior_issues) || [];
  const techniqueIssues = (comprehensive && comprehensive.technique_issues) || [];
  const inattention = behaviorIssues.find(
    (b) => (b.category || '').toString().toUpperCase() === 'INATTENTION'
  );
  const issuesCount = behaviorIssues.length + techniqueIssues.length;
  const eyeContact = behavior && Number.isFinite(behavior.eye_contact_score)
    ? Math.round(behavior.eye_contact_score)
    : null;

  return [
    {
      label: 'Doctor attention',
      value: inattention ? 'Low eye contact' : eyeContact != null ? `${eyeContact}% eye contact` : '—',
      detail: inattention
        ? 'Supplemental behavior note — primary focus is report vs video timestamps.'
        : 'Eye-contact estimate from supplemental behavior review.',
      tone: 'rose',
    },
    {
      label: 'Examination quality',
      value: `${comprehensive.examination_quality_score ?? 0}/100`,
      detail: `Professionalism scored ${comprehensive.professionalism_score ?? 0}/100. Empathy ${comprehensive.doctor_empathy_score ?? 0}/10.`,
      tone: 'amber',
    },
    {
      label: 'Issues identified',
      value: String(issuesCount),
      detail: `${techniqueIssues.length} technique \u00b7 ${behaviorIssues.length} behavior`,
      tone: 'indigo',
    },
  ];
}

function CaseHeader({ manifest }) {
  return (
    <header className="bg-gradient-to-br from-slate-900 via-indigo-950 to-purple-950 rounded-2xl shadow-lg overflow-hidden">
      <div className="p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <span className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-indigo-200 bg-white/10 border border-white/10 rounded-full px-3 py-1 mb-3">
              Sample completed case
            </span>
            <h1 className="text-2xl sm:text-3xl font-semibold text-white tracking-tight">
              {manifest.plaintiff_name}
            </h1>
            <div className="mt-2 text-sm text-indigo-100">
              {manifest.examiner_name} &middot; CME on {manifest.exam_date}
            </div>
            <div className="mt-1 text-xs text-indigo-200/80">
              DOB {manifest.date_of_birth} &middot; Date of injury {manifest.date_of_injury}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href={`${SAMPLE}/standard_report.html`} target="_blank" rel="noreferrer">
              <Button variant="primary" size="md">
                View standard report
              </Button>
            </a>
            <a href={`${SAMPLE}/standard_report.pdf`} target="_blank" rel="noreferrer">
              <Button variant="secondary" size="md">
                Download PDF
              </Button>
            </a>
            <a href={`${SAMPLE}/behavior_dashboard.html`} target="_blank" rel="noreferrer">
              <Button variant="ghost" size="md" className="text-indigo-100 hover:text-white hover:bg-white/10">
                Behavior dashboard
              </Button>
            </a>
          </div>
        </div>
      </div>
    </header>
  );
}

function Highlights({ items }) {
  const toneClass = (tone) => {
    switch (tone) {
      case 'rose':
        return 'from-rose-50 to-rose-100 border-rose-200 text-rose-900';
      case 'amber':
        return 'from-amber-50 to-amber-100 border-amber-200 text-amber-900';
      case 'indigo':
      default:
        return 'from-indigo-50 to-purple-100 border-indigo-200 text-indigo-900';
    }
  };
  return (
    <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
      {items.map((h, i) => (
        <div
          key={i}
          className={`rounded-xl border bg-gradient-to-br ${toneClass(h.tone)} p-5 shadow-sm`}
        >
          <div className="text-[11px] font-semibold uppercase tracking-wide opacity-70 mb-1">{h.label}</div>
          <div className="text-2xl font-semibold tracking-tight">{h.value}</div>
          <div className="text-xs mt-2 opacity-80">{h.detail}</div>
        </div>
      ))}
    </div>
  );
}

function TabButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
        active
          ? 'border-indigo-600 text-indigo-700'
          : 'border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300'
      }`}
    >
      {children}
    </button>
  );
}

function OverviewPanel({ comprehensive, behavior }) {
  const tests = comprehensive.tests_performed || {};
  const technique = comprehensive.technique_issues || [];
  const behaviorIssues = behavior.behavior_issues || [];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Card title="Examination summary">
        <KeyValue label="Deposition video" value={`${Math.round(comprehensive.total_video_duration_sec / 60)} min`} />
        <KeyValue label="Claimed exam time (report)" value={`${comprehensive.claimed_exam_time_min} min`} />
        <KeyValue label="Observed hands-on time" value={`${Math.round(comprehensive.actual_hands_on_exam_sec / 60)} min`} />
        <KeyValue label="Patient wore gown" value={comprehensive.patient_wore_gown ? 'Yes' : 'No'} highlight={!comprehensive.patient_wore_gown} />
      </Card>
      <Card title="Behavior scores">
        <KeyValue label="Eye contact" value={`${(behavior.eye_contact_score || 0).toFixed(0)}% of time`} />
        <KeyValue label="Attention (focused on patient)" value={`${(behavior.attention_score || 0).toFixed(0)}%`} />
        <KeyValue label="Empathy" value={`${(behavior.empathy_score || 0).toFixed(1)}/10`} />
        <KeyValue label="Professionalism" value={`${(behavior.professionalism_score || 0).toFixed(1)}/10`} />
        <KeyValue label="Overall demeanor" value={behavior.overall_demeanor || '—'} />
      </Card>
      <Card title="Tests documented vs observed">
        <ul className="space-y-1.5">
          {Object.entries(tests).map(([test, count]) => (
            <li key={test} className="flex items-center justify-between text-sm">
              <span className="text-slate-700 capitalize">{test.replace(/_/g, ' ')}</span>
              <span className="font-mono text-xs text-slate-500">{count} video moments</span>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Top issues">
        <IssueList
          title="Technique"
          items={technique.map((t) => ({
            label: (t.issue || '').replace(/_/g, ' '),
            severity: t.severity,
            detail: t.timestamp_sec != null ? `at ${Math.round(t.timestamp_sec)}s` : '',
          }))}
        />
        <IssueList
          title="Behavior"
          items={behaviorIssues.map((b) => ({
            label: (b.category || '').toString().toLowerCase().replace(/_/g, ' '),
            severity: String(b.severity || '').toLowerCase().replace('behaviorseverity.', ''),
            detail: b.description,
          }))}
        />
      </Card>
    </div>
  );
}

function Card({ title, children }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-3">{title}</h3>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function KeyValue({ label, value, highlight }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-slate-600">{label}</span>
      <span className={`font-semibold ${highlight ? 'text-rose-700' : 'text-slate-900'}`}>{value}</span>
    </div>
  );
}

function IssueList({ title, items }) {
  if (!items || !items.length) return null;
  return (
    <div className="mt-2 first:mt-0">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 mb-2">{title}</div>
      <ul className="space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${severityDot(it.severity)}`} />
            <div className="min-w-0">
              <div className="text-slate-800 capitalize">{it.label}</div>
              {it.detail && <div className="text-xs text-slate-500">{it.detail}</div>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function severityDot(severity) {
  const s = String(severity || '').toLowerCase();
  if (s === 'high') return 'bg-rose-500';
  if (s === 'medium') return 'bg-amber-500';
  if (s === 'low') return 'bg-emerald-500';
  return 'bg-slate-400';
}

function EmbedPanel({ title, src, externalLabel, externalHref, downloadLabel, downloadHref }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        <div className="flex items-center gap-2">
          {downloadHref && (
            <a href={downloadHref} target="_blank" rel="noreferrer">
              <Button variant="secondary" size="sm">{downloadLabel}</Button>
            </a>
          )}
          {externalHref && (
            <a href={externalHref} target="_blank" rel="noreferrer">
              <Button variant="primary" size="sm">{externalLabel}</Button>
            </a>
          )}
        </div>
      </div>
      <div className="rounded-xl border border-slate-200 overflow-hidden bg-white">
        <iframe
          src={src}
          title={title}
          className="w-full"
          style={{ height: '70vh', minHeight: '560px' }}
        />
      </div>
    </div>
  );
}

function RunMetadata({ manifest }) {
  return (
    <div className="mt-8 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">Run metadata</h3>
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2 text-xs">
            <Meta label="Model" value={manifest.model} />
            <Meta label="Providers" value={(manifest.providers || []).join(', ')} />
            <Meta label="Video length" value="21:48" />
            <Meta label="CME date" value={manifest.exam_date} />
            <Meta label="Technique prompt" value={manifest.prompt_versions?.technique} />
            <Meta label="Audio prompt" value={manifest.prompt_versions?.audio} />
            <Meta label="Behavior visual" value={manifest.prompt_versions?.behavior_visual} />
            <Meta label="Behavior verbal" value={manifest.prompt_versions?.behavior_verbal} />
            <Meta label="Wall clock" value={`${Math.round((manifest.wall_clock_sec || 0) / 60)} min`} />
            <Meta label="Cost (USD)" value={manifest.cost_usd ? `$${manifest.cost_usd.toFixed(2)}` : '—'} />
            <Meta label="Bundle hash" value={manifest.bundle_hash} mono />
            <Meta label="Recorded" value={manifest.recorded_at?.slice(0, 10)} />
          </dl>
        </div>
        <div className="flex flex-col items-end gap-2">
          <Link to="/cases/new">
            <Button variant="secondary" size="sm">Start a new case</Button>
          </Link>
          <span className="text-[11px] text-slate-400">Static demo bundle &middot; no live API calls</span>
        </div>
      </div>
    </div>
  );
}

function Meta({ label, value, mono }) {
  return (
    <div>
      <dt className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className={`text-slate-800 ${mono ? 'font-mono' : ''}`}>{value || '—'}</dd>
    </div>
  );
}

function SampleSkeleton() {
  return (
    <div className="animate-fade-in">
      <div className="h-40 rounded-2xl shimmer mb-6" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="h-28 rounded-xl shimmer" />
        <div className="h-28 rounded-xl shimmer" />
        <div className="h-28 rounded-xl shimmer" />
      </div>
      <div className="h-96 rounded-2xl shimmer" />
    </div>
  );
}
