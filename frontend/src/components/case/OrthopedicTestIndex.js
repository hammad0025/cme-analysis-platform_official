import React, { useMemo, useRef, useState, useCallback, useEffect } from 'react';

const VERDICT_STYLES = {
  proper: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
  modified: 'bg-amber-100 text-amber-800 ring-amber-200',
  improper: 'bg-rose-100 text-rose-800 ring-rose-200',
  inconclusive: 'bg-slate-100 text-slate-700 ring-slate-200',
  not_shown: 'bg-purple-100 text-purple-800 ring-purple-200',
};

const STATUS_STYLES = {
  claimed_and_observed: 'bg-indigo-100 text-indigo-800',
  claimed_not_observed: 'bg-rose-100 text-rose-800',
  observed_not_reported: 'bg-amber-100 text-amber-900',
  neither: 'bg-slate-100 text-slate-600',
};

const STATUS_LABELS = {
  claimed_and_observed: 'Claimed & observed',
  claimed_not_observed: 'Claimed, not on video',
  observed_not_reported: 'Done, not reported',
  neither: 'Video only',
};

const VERDICT_LABELS = {
  proper: 'Proper',
  modified: 'Modified',
  improper: 'Improper',
  inconclusive: 'Inconclusive',
  not_shown: 'Not shown',
};

export function formatTimestamp(sec) {
  if (sec == null || Number.isNaN(Number(sec))) return '—';
  const total = Math.max(0, Math.floor(Number(sec)));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function formatClipHeader(event) {
  if (event?.start_sec == null) {
    return `Report claim — ${event?.test_name || 'Test'}`;
  }
  const end = event.end_sec != null ? formatTimestamp(event.end_sec) : formatTimestamp(event.start_sec);
  return `Deposition clip: ${formatTimestamp(event.start_sec)}–${end} — ${event.test_name}`;
}

function BoolBadge({ value, trueLabel, falseLabel }) {
  const on = Boolean(value);
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${
        on ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' : 'bg-slate-50 text-slate-500 ring-1 ring-slate-200'
      }`}
    >
      {on ? trueLabel : falseLabel}
    </span>
  );
}

function VerdictBadge({ verdict }) {
  const key = verdict || 'inconclusive';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1 ${
        VERDICT_STYLES[key] || VERDICT_STYLES.inconclusive
      }`}
    >
      {VERDICT_LABELS[key] || key}
    </span>
  );
}

function StatusBadge({ status }) {
  const key = status || 'neither';
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_STYLES[key] || STATUS_STYLES.neither}`}>
      {STATUS_LABELS[key] || key}
    </span>
  );
}

/**
 * Primary v2 UI: searchable orthopedic test index with synced deposition video.
 */
export default function OrthopedicTestIndex({
  ledger,
  videoUrl,
  loading = false,
  error = null,
  emptyMessage = 'No test ledger available for this case.',
}) {
  const videoRef = useRef(null);
  const videoPanelRef = useRef(null);
  const [query, setQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [verdictFilter, setVerdictFilter] = useState('all');
  const [reconciliationFilter, setReconciliationFilter] = useState('all');
  const [viewFilter, setViewFilter] = useState('report');
  const [selectedId, setSelectedId] = useState(null);
  const [activeEvent, setActiveEvent] = useState(null);

  const events = useMemo(() => ledger?.events || [], [ledger]);

  const eventRows = useMemo(
    () =>
      events.map((event, idx) => ({
        ...event,
        _id: `${event.test_type}-${event.body_region}-${event.start_sec ?? 'claim'}-${idx}`,
      })),
    [events],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return eventRows.filter((event) => {
      if (viewFilter === 'report' && event.row_kind && event.row_kind !== 'report_summary') return false;
      if (viewFilter === 'clips' && event.row_kind && event.row_kind !== 'video_clip') return false;
      if (categoryFilter === 'ortho' && event.category !== 'orthopedic_neurologic') return false;
      if (categoryFilter === 'general' && event.category !== 'general_examination') return false;
      if (verdictFilter !== 'all' && event.technique_verdict !== verdictFilter) return false;
      if (reconciliationFilter === 'technique_issues') {
        const v = event.technique_verdict;
        if (v !== 'modified' && v !== 'improper') return false;
      } else if (reconciliationFilter !== 'all' && event.three_way_status !== reconciliationFilter) {
        return false;
      }
      if (!q) return true;
      const haystack = [
        event.test_name,
        event.body_region_label,
        event.test_type,
        event.variant,
        event.three_way_status,
        ...(event.technique_issues || []),
        ...(event.technique_notes || []),
        event.report_claim_text,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [eventRows, query, categoryFilter, verdictFilter, reconciliationFilter, viewFilter]);

  const applyTimDemoPreset = useCallback(() => {
    setViewFilter('report');
    setCategoryFilter('all');
    setReconciliationFilter('claimed_not_observed');
    setVerdictFilter('all');
    setQuery('');
  }, []);

  useEffect(() => {
    if (!selectedId && filtered.length) {
      setSelectedId(filtered[0]._id);
      setActiveEvent(filtered[0]);
    }
  }, [filtered, selectedId]);

  const seekToEvent = useCallback(
    (event) => {
      setSelectedId(event._id);
      setActiveEvent(event);
      if (event.start_sec == null) return;
      videoPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      if (!videoRef.current) return;
      const video = videoRef.current;
      video.currentTime = Math.max(0, event.start_sec - 0.25);
      video.play().catch(() => {
        // autoplay may be blocked until user gesture
      });
    },
    [],
  );

  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
        Loading test ledger…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">
        {error}
      </div>
    );
  }

  if (!events.length) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
        {emptyMessage}
      </div>
    );
  }

  const summary = ledger || {};

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50/80 via-white to-purple-50/60 p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Orthopedic & neurologic tests</h2>
            <p className="text-sm text-indigo-600 mt-1 max-w-2xl">
              Report-level reconciliation: one row per defense-report statement vs. whether the examination
              video shows that test. Switch to Video clips for timestamp drill-down by body region.
            </p>
          </div>
          <dl className="flex flex-wrap gap-4 text-center">
            <div>
              <dt className="text-[10px] uppercase tracking-wide text-slate-500">Events</dt>
              <dd className="text-xl font-bold text-indigo-700">{summary.total_events ?? events.length}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wide text-slate-500">On video</dt>
              <dd className="text-xl font-bold text-emerald-700">{summary.observed_event_count ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wide text-slate-500">Not reported</dt>
              <dd className="text-xl font-bold text-amber-700">{summary.observed_not_reported_count ?? '—'}</dd>
            </div>
          </dl>
        </div>
      </div>

      {videoUrl ? (
        <div
          ref={videoPanelRef}
          className="scroll-mt-20 rounded-2xl border border-slate-200 bg-black overflow-hidden shadow-lg"
        >
          <div className="px-4 py-3 bg-slate-900/90 border-b border-white/10">
            <p className="text-sm font-semibold text-white truncate">
              {activeEvent ? formatClipHeader(activeEvent) : 'Select a test to preview deposition clip'}
            </p>
          </div>
          <video
            ref={videoRef}
            controls
            preload="metadata"
            className="w-full max-h-[min(50vh,420px)] bg-black"
            src={videoUrl}
          >
            Your browser does not support HTML5 video.
          </video>
        </div>
      ) : (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Video playback is not available in this view. Open the live Osborne session (
          <code className="text-xs bg-amber-100 px-1 rounded">/sessions/cme_6f506df9ebf9</code>
          ) Materials tab for synced deposition video, or use the Report vs video tab there.
        </div>
      )}

      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="px-4 sm:px-5 pt-4 flex flex-wrap gap-2 items-center">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 mr-1">View</span>
          {[
            { value: 'report', label: 'Report summary' },
            { value: 'clips', label: 'Video clips' },
            { value: 'all', label: 'All rows' },
          ].map(({ value, label }) => (
            <button
              key={value}
              type="button"
              onClick={() => setViewFilter(value)}
              className={`inline-flex items-center rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                viewFilter === value
                  ? 'bg-slate-900 text-white'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              {label}
            </button>
          ))}
          <span className="w-px h-5 bg-slate-200 mx-1 hidden sm:block" />
          <button
            type="button"
            onClick={applyTimDemoPreset}
            className="inline-flex items-center rounded-full px-3 py-1.5 text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
          >
            Tim demo
          </button>
          <button
            type="button"
            onClick={() => {
              setCategoryFilter('all');
              setReconciliationFilter('all');
              setVerdictFilter('all');
              setQuery('');
            }}
            className="inline-flex items-center rounded-full px-3 py-1.5 text-xs font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
          >
            Clear filters
          </button>
        </div>
        <div className="p-4 sm:p-5 border-b border-slate-100 flex flex-col lg:flex-row gap-3 lg:items-center lg:justify-between">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tests, body region, issues…"
            className="w-full lg:max-w-md rounded-xl border border-slate-300 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400"
          />
          <div className="flex flex-wrap gap-2">
            <FilterSelect
              label="Category"
              value={categoryFilter}
              onChange={setCategoryFilter}
              options={[
                { value: 'all', label: 'All tests' },
                { value: 'ortho', label: 'Ortho / neuro' },
                { value: 'general', label: 'General exam' },
              ]}
            />
            <FilterSelect
              label="Verdict"
              value={verdictFilter}
              onChange={setVerdictFilter}
              options={[
                { value: 'all', label: 'All verdicts' },
                ...Object.entries(VERDICT_LABELS).map(([value, label]) => ({ value, label })),
              ]}
            />
            <FilterSelect
              label="Reconciliation"
              value={reconciliationFilter}
              onChange={setReconciliationFilter}
              options={[
                { value: 'all', label: 'All' },
                { value: 'observed_not_reported', label: 'Done not reported' },
                { value: 'claimed_not_observed', label: 'Claimed not on video' },
                { value: 'claimed_and_observed', label: 'Claimed & observed' },
                { value: 'technique_issues', label: 'Technique issues' },
              ]}
            />
          </div>
        </div>

        <p className="px-5 py-2 text-xs text-slate-500 border-b border-slate-50">
          Showing {filtered.length} of {events.length} tests
        </p>

        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500 bg-slate-50/80 border-b border-slate-200">
                <th className="py-3 px-4 font-semibold">Test</th>
                <th className="py-3 px-3 font-semibold">Time</th>
                <th className="py-3 px-3 font-semibold">Claimed?</th>
                <th className="py-3 px-3 font-semibold">On video?</th>
                <th className="py-3 px-3 font-semibold">Reconciliation</th>
                <th className="py-3 px-4 font-semibold">Technique</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((event) => {
                const isSelected = event._id === selectedId;
                const hasTime = event.start_sec != null;
                return (
                  <tr
                    key={event._id}
                    onClick={() => seekToEvent(event)}
                    className={`border-b border-slate-100 cursor-pointer transition-colors ${
                      isSelected ? 'bg-indigo-50/90 ring-1 ring-inset ring-indigo-200' : 'hover:bg-slate-50'
                    }`}
                  >
                    <td className="py-3 px-4">
                      <p className="font-semibold text-slate-900">{event.test_name}</p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {event.row_kind === 'report_summary' && event.video_clip_count != null
                          ? `${event.video_clip_count} video segment(s) · `
                          : ''}
                        {event.variant ? `${event.variant} · ` : ''}
                        {(event.technique_issues || []).length > 0 && (
                          <span className="text-amber-700">
                            {' '}
                            · {(event.technique_issues || []).slice(0, 2).join(', ')}
                          </span>
                        )}
                      </p>
                    </td>
                    <td className="py-3 px-3 font-mono text-xs text-indigo-700 whitespace-nowrap">
                      {hasTime ? (
                        <>
                          {formatTimestamp(event.start_sec)}
                          {event.end_sec != null && event.end_sec !== event.start_sec
                            ? `–${formatTimestamp(event.end_sec)}`
                            : ''}
                        </>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="py-3 px-3">
                      <BoolBadge value={event.claimed_in_report} trueLabel="Yes" falseLabel="No" />
                    </td>
                    <td className="py-3 px-3">
                      <BoolBadge value={event.observed_on_video} trueLabel="Yes" falseLabel="No" />
                    </td>
                    <td className="py-3 px-3">
                      <StatusBadge status={event.three_way_status} />
                    </td>
                    <td className="py-3 px-4">
                      <VerdictBadge verdict={event.technique_verdict} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {activeEvent && (
          <div className="border-t border-slate-200 bg-slate-50/50 p-4 sm:p-5">
            <h3 className="text-sm font-semibold text-slate-900">{activeEvent.test_name}</h3>
            {activeEvent.report_claim_text && (
              <p className="text-xs text-slate-600 mt-2">
                <span className="font-semibold text-slate-700">Report claim:</span> {activeEvent.report_claim_text}
              </p>
            )}
            {(activeEvent.technique_notes || []).length > 0 && (
              <p className="text-xs text-slate-600 mt-2">
                <span className="font-semibold text-slate-700">Observation:</span>{' '}
                {activeEvent.technique_notes[0]}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function FilterSelect({ label, value, onChange, options }) {
  return (
    <label className="inline-flex items-center gap-2 text-xs text-slate-600">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}
