import React, { useMemo, useRef, useState, useCallback, useEffect } from 'react';
import { formatTimestamp } from './OrthopedicTestIndex';
import { mergeDepositionRows } from '../../lib/depositionRows';
import {
  evidenceTimestampsFiltered,
  filterUsableEvidence,
  NOT_SHOWN_ON_VIDEO,
} from '../../lib/evidenceQuality';
import {
  issueBadgeStyle,
  rankMainIssues,
  sortAllFindings,
} from '../../lib/egregiousRanking';

const APP_BASE = 'https://cme-analysis-platform-official.vercel.app';

const VERDICT_STYLES = {
  supported: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
  partially_supported: 'bg-amber-100 text-amber-800 ring-amber-200',
  contradicted: 'bg-rose-100 text-rose-800 ring-rose-200',
  not_shown: 'bg-purple-100 text-purple-800 ring-purple-200',
  performed_not_reported: 'bg-orange-100 text-orange-800 ring-orange-200',
  insufficient_evidence: 'bg-slate-100 text-slate-700 ring-slate-200',
};

const VERDICT_LABELS = {
  supported: 'Supported',
  partially_supported: 'Partial',
  contradicted: 'Contradicted',
  not_shown: 'Not on video',
  performed_not_reported: 'Not in report',
  insufficient_evidence: 'Insufficient',
};

function VerdictBadge({ verdict }) {
  const key = (verdict || 'insufficient_evidence').toLowerCase();
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1 ${
        VERDICT_STYLES[key] || VERDICT_STYLES.insufficient_evidence
      }`}
    >
      {VERDICT_LABELS[key] || key.replace(/_/g, ' ')}
    </span>
  );
}

function displayVideoFinding(row) {
  const ce = row.cross_examination || {};
  const usable = filterUsableEvidence(row.evidence, row.claim_id);
  const fromCe = String(ce.video_finding || '').trim();
  if (fromCe) return fromCe;
  const text = String(row.video_shows || '').trim();
  if (text && text !== '—') return text;
  if (!usable.length) return NOT_SHOWN_ON_VIDEO;
  return String(row.reasoning || NOT_SHOWN_ON_VIDEO);
}

function timestampList(row) {
  const ce = row.cross_examination || {};
  const fromCe = (ce.timestamps || [])
    .map((t) => Number(t?.sec))
    .filter((s) => Number.isFinite(s));
  if (fromCe.length) return fromCe;
  return evidenceTimestampsFiltered(row.evidence, row.claim_id);
}

function LiteratureRefs({ refs = [] }) {
  const links = refs.filter((r) => r && r.url);
  if (!links.length) return null;
  return (
    <div className="mt-3">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 mb-1.5">
        Dr. Hunter methodology references
      </p>
      <div className="flex flex-wrap gap-2">
        {links.map((r) => (
          <a
            key={r.url}
            href={r.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            title={r.url}
            className="inline-flex items-center rounded-lg border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-[11px] font-medium text-indigo-800 hover:bg-indigo-100 hover:border-indigo-300"
          >
            {(r.title || r.url).slice(0, 72)}
          </a>
        ))}
      </div>
    </div>
  );
}

function TimestampChips({ row, sessionId, onSeek }) {
  const stamps = timestampList(row);
  if (!stamps.length) return <span className="text-slate-400 text-xs">No timestamp</span>;

  const base = sessionId
    ? `${APP_BASE}/sessions/${sessionId}`
    : null;

  return (
    <div className="flex flex-wrap gap-2">
      {stamps.map((sec) => (
        <button
          key={`${row._id}-${sec}`}
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onSeek(row, sec);
          }}
          className="inline-flex items-center gap-1 rounded-full bg-indigo-600 px-3 py-1 text-xs font-mono font-semibold text-white hover:bg-indigo-700 shadow-sm"
          title={base ? `Jump to ${formatTimestamp(sec)}` : formatTimestamp(sec)}
        >
          {formatTimestamp(sec)}
        </button>
      ))}
      {base && stamps[0] != null && (
        <a
          href={`${base}?t=${Math.floor(stamps[0])}`}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[10px] text-slate-600 hover:border-indigo-300 hover:text-indigo-700"
        >
          Share link
        </a>
      )}
    </div>
  );
}

function MainIssueCard({ row, sessionId, selected, onSelect, onSeek }) {
  const ce = row.cross_examination || {};
  const leading = ce.leading_question || row.deposition_prompt || '—';
  const reportCite = ce.report_citation
    || (row.report_page != null
      ? `Page ${row.report_page}: "${row.report_quote || row.claim_text || ''}"`
      : `"${row.report_quote || row.claim_text || ''}"`);
  const refs = ce.literature_refs || [];

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onSelect(row)}
      onKeyDown={(e) => { if (e.key === 'Enter') onSelect(row); }}
      className={`rounded-2xl border p-5 transition-all cursor-pointer ${
        selected
          ? 'border-rose-300 bg-rose-50/40 shadow-md ring-2 ring-rose-200'
          : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold tracking-wide ring-1 ${issueBadgeStyle(row)}`}
          >
            {row.issue_type_label || 'ISSUE'}
          </span>
          <h3 className="text-sm font-bold text-slate-900">
            {row.test_name || row.claim_id}
          </h3>
        </div>
        <VerdictBadge verdict={row.verdict} />
      </div>

      <p className="text-xs text-slate-600 leading-relaxed mb-3 font-medium">
        {row.issue_punch_line}
      </p>

      <div className="space-y-3 text-xs leading-relaxed">
        <div className="rounded-lg bg-slate-900/5 border border-slate-200/80 px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 mb-1">
            Cross-examination leading question
          </p>
          <p className="text-slate-800 font-medium">{leading}</p>
        </div>

        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 mb-1">
            Doctor&apos;s report
          </p>
          <p className="text-slate-700 italic">&ldquo;{reportCite}&rdquo;</p>
        </div>

        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 mb-1">
            What video shows
          </p>
          <p className="text-slate-700">{displayVideoFinding(row)}</p>
        </div>

        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 mb-1.5">
            Video timestamps
          </p>
          <TimestampChips row={row} sessionId={sessionId} onSeek={onSeek} />
        </div>

        {row.why_it_matters && (
          <p className="text-slate-600 border-l-2 border-amber-400 pl-3">
            <span className="font-semibold text-slate-700">Why it matters: </span>
            {row.why_it_matters}
          </p>
        )}

        <LiteratureRefs refs={refs} />
      </div>
    </article>
  );
}

/**
 * Main Issues Identified — primary deposition crosswalk view.
 */
export default function ClaimVerdictIndex({
  verdicts = [],
  atomicClaims = null,
  threeWayLedger = null,
  sessionId = null,
  videoUrl,
  loading = false,
  error = null,
  emptyMessage = 'No main issues identified for this case.',
  videoRef: externalVideoRef = null,
}) {
  const internalVideoRef = useRef(null);
  const videoRef = externalVideoRef || internalVideoRef;
  const videoPanelRef = useRef(null);
  const [query, setQuery] = useState('');
  const [verdictFilter, setVerdictFilter] = useState('all');
  const [showAllFindings, setShowAllFindings] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [activeRow, setActiveRow] = useState(null);

  const rows = useMemo(
    () => mergeDepositionRows(verdicts, atomicClaims, threeWayLedger),
    [verdicts, atomicClaims, threeWayLedger],
  );

  const mainIssues = useMemo(
    () => rankMainIssues(verdicts, threeWayLedger, { maxIssues: 7 }),
    [verdicts, threeWayLedger],
  );

  const allSorted = useMemo(
    () => sortAllFindings(verdicts, threeWayLedger),
    [verdicts, threeWayLedger],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return allSorted.filter((row) => {
      if (verdictFilter !== 'all' && (row.verdict || '').toLowerCase() !== verdictFilter) {
        return false;
      }
      if (!q) return true;
      const haystack = [
        row.claim_id,
        row.test_name,
        row.report_quote,
        row.deposition_prompt,
        row.cross_examination?.leading_question,
        row.video_shows,
        row.reasoning,
        row.verdict,
        row.issue_type_label,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [allSorted, query, verdictFilter]);

  useEffect(() => {
    if (!selectedId && mainIssues.length) {
      setSelectedId(mainIssues[0]._id || mainIssues[0].claim_id);
      setActiveRow(mainIssues[0]);
    }
  }, [mainIssues, selectedId]);

  const seekToTimestamp = useCallback((row, ts) => {
    setSelectedId(row._id || row.claim_id);
    setActiveRow(row);
    videoPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (!videoRef.current) return;
    const video = videoRef.current;
    video.currentTime = Math.max(0, ts - 0.25);
    video.play().catch(() => {});
  }, [videoRef]);

  const seekToRow = useCallback(
    (row) => {
      const stamps = timestampList(row);
      if (stamps.length) seekToTimestamp(row, stamps[0]);
      else {
        setSelectedId(row._id || row.claim_id);
        setActiveRow(row);
      }
    },
    [seekToTimestamp],
  );

  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
        Loading main issues…
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

  if (!rows.length) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-rose-200 bg-gradient-to-br from-rose-50 to-amber-50 px-5 py-4">
        <p className="text-lg font-bold text-rose-950">Main Issues Identified</p>
        <p className="text-rose-900/80 mt-1 text-sm leading-relaxed">
          The highest-priority discrepancies between the defense doctor&apos;s written report and the
          deposition video — ranked for cross-examination. Click a timestamp to jump the player.
        </p>
      </div>

      {!videoUrl && sessionId && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
          Video playback requires the live session (
          <code className="text-xs bg-amber-100 px-1 rounded">/sessions/{sessionId}</code>
          ).
        </p>
      )}

      {videoUrl ? (
        <div
          ref={videoPanelRef}
          className="scroll-mt-20 rounded-xl overflow-hidden border border-slate-200 bg-black shadow-lg"
        >
          <div className="px-4 py-3 bg-slate-900/90 border-b border-white/10">
            <p className="text-sm font-semibold text-white truncate">
              {activeRow
                ? `${activeRow.test_name || activeRow.claim_id} — ${
                    timestampList(activeRow).map(formatTimestamp).join(', ') || 'select a timestamp'
                  }`
                : 'Select an issue to preview video'}
            </p>
          </div>
          <video
            ref={videoRef}
            src={videoUrl}
            controls
            className="w-full max-h-[min(50vh,420px)] bg-black"
            playsInline
            preload="metadata"
          />
        </div>
      ) : null}

      {mainIssues.length ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wide">
              {mainIssues.length} key discrepanc{mainIssues.length === 1 ? 'y' : 'ies'}
            </h2>
          </div>
          {mainIssues.map((row) => (
            <MainIssueCard
              key={row._id || row.claim_id}
              row={row}
              sessionId={sessionId}
              selected={(row._id || row.claim_id) === selectedId}
              onSelect={seekToRow}
              onSeek={seekToTimestamp}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
          No issues met the high-priority threshold. Expand all findings below.
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
        <button
          type="button"
          onClick={() => setShowAllFindings((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-3 text-left text-sm font-semibold text-slate-800 hover:bg-slate-50"
        >
          <span>All findings ({filtered.length})</span>
          <span className="text-slate-400 text-xs">{showAllFindings ? 'Collapse' : 'Expand'}</span>
        </button>

        {showAllFindings && (
          <div className="border-t border-slate-100 p-4 space-y-3">
            <div className="flex flex-wrap gap-2">
              <input
                type="search"
                placeholder="Search findings…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="flex-1 min-w-[200px] rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
              />
              <select
                value={verdictFilter}
                onChange={(e) => setVerdictFilter(e.target.value)}
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <option value="all">All verdicts</option>
                <option value="contradicted">Contradicted</option>
                <option value="partially_supported">Partial</option>
                <option value="performed_not_reported">Not in report</option>
                <option value="not_shown">Not on video</option>
                <option value="supported">Supported</option>
                <option value="insufficient_evidence">Insufficient</option>
              </select>
            </div>

            <div className="overflow-x-auto rounded-lg border border-slate-100">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Issue</th>
                    <th className="px-3 py-2">Score</th>
                    <th className="px-3 py-2">Report</th>
                    <th className="px-3 py-2">Timestamp</th>
                    <th className="px-3 py-2">Verdict</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filtered.map((row) => {
                    const stamps = timestampList(row);
                    const selected = (row._id || row.claim_id) === selectedId;
                    return (
                      <tr
                        key={row._id || row.claim_id}
                        onClick={() => seekToRow(row)}
                        className={`cursor-pointer transition-colors ${
                          selected ? 'bg-indigo-50' : 'hover:bg-slate-50'
                        }`}
                      >
                        <td className="px-3 py-2 align-top text-xs font-semibold text-slate-800">
                          {row.test_name || row.claim_id}
                        </td>
                        <td className="px-3 py-2 align-top text-xs font-mono text-slate-500">
                          {row.egregious_score ?? 0}
                        </td>
                        <td className="px-3 py-2 align-top text-xs text-slate-600 max-w-xs truncate">
                          {row.report_quote || '—'}
                        </td>
                        <td className="px-3 py-2 align-top whitespace-nowrap font-mono text-xs">
                          {stamps.length
                            ? stamps.map((s) => formatTimestamp(s)).join(', ')
                            : '—'}
                        </td>
                        <td className="px-3 py-2 align-top">
                          <VerdictBadge verdict={row.verdict} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {!filtered.length && (
              <p className="text-center text-sm text-slate-500 py-4">No rows match filters.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
