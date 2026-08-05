import React, { useMemo, useCallback } from 'react';
import { formatTimestamp } from './OrthopedicTestIndex';

const STATUS_STYLES = {
  claimed_and_observed: 'bg-indigo-100 text-indigo-800',
  claimed_not_shown: 'bg-rose-100 text-rose-800',
  performed_not_reported: 'bg-amber-100 text-amber-900 ring-2 ring-amber-300',
  performed_incorrectly: 'bg-orange-100 text-orange-900',
  neither: 'bg-slate-100 text-slate-600',
};

const STATUS_LABELS = {
  claimed_and_observed: 'Claimed & on video',
  claimed_not_shown: 'In report, not on video',
  performed_not_reported: 'Done on video, not in report',
  performed_incorrectly: 'Done incorrectly',
  neither: '—',
};

const VERDICT_LABELS = {
  proper: 'Proper',
  modified: 'Modified',
  improper: 'Improper',
  inconclusive: 'Inconclusive',
  not_shown: 'Not shown',
};

function StatusBadge({ status }) {
  const key = status || 'neither';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${
        STATUS_STYLES[key] || STATUS_STYLES.neither
      }`}
    >
      {STATUS_LABELS[key] || key.replace(/_/g, ' ')}
    </span>
  );
}

/**
 * Named test index + three-way reconciliation (Hunter rules).
 * Surfaces "done on video, not in report" rows for deposition prep.
 */
export default function ThreeWayTestIndex({
  namedIndex = null,
  threeWayLedger = null,
  onSeek,
  loading = false,
  error = null,
}) {
  const rows = useMemo(() => threeWayLedger?.rows || [], [threeWayLedger]);
  const namedTests = useMemo(() => namedIndex?.tests || [], [namedIndex]);

  const notReported = useMemo(
    () => rows.filter((r) => r.three_way_status === 'performed_not_reported'),
    [rows],
  );

  const handleSeek = useCallback(
    (row) => {
      if (row?.timestamp_sec == null || !onSeek) return;
      onSeek(row.timestamp_sec, row);
    },
    [onSeek],
  );

  if (loading) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500 text-center">
        Loading named test index…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
        {error}
      </div>
    );
  }

  if (!rows.length && !namedTests.length) {
    return null;
  }

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-violet-100 bg-gradient-to-br from-violet-50/70 to-white p-4 sm:p-5">
        <h3 className="text-base font-bold text-slate-900">Named tests on video</h3>
        <p className="text-xs text-violet-900/80 mt-1 leading-relaxed">
          Hoffmann, Babinski, Romberg, and cervical ROM by plane — extracted from frame analysis
          using Hunter methodology gates (not category blobs).
        </p>
        {namedIndex?.detection_counts && (
          <dl className="flex flex-wrap gap-4 mt-3 text-center">
            {Object.entries(namedIndex.detection_counts).map(([key, count]) => (
              <div key={key}>
                <dt className="text-[10px] uppercase tracking-wide text-slate-500">{key.replace(/_/g, ' ')}</dt>
                <dd className="text-lg font-bold text-violet-700">{count}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      {notReported.length > 0 && (
        <div className="rounded-xl border-2 border-amber-300 bg-amber-50/90 p-4 sm:p-5 shadow-sm">
          <h4 className="text-sm font-bold text-amber-950">
            Done on video, not documented in report ({notReported.length})
          </h4>
          <p className="text-xs text-amber-900/90 mt-1 mb-3">
            These named tests appear on the deposition recording but have no matching statement in the
            doctor&apos;s written report — strong deposition cross-examination rows.
          </p>
          <ul className="space-y-2">
            {notReported.map((row) => (
              <li
                key={`${row.named_test_key}-${row.plane || 'x'}-${row.timestamp_sec}`}
                className="rounded-lg bg-white/80 border border-amber-200 px-3 py-2 text-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-slate-900">{row.test_name}</span>
                  {row.timestamp_sec != null && (
                    <button
                      type="button"
                      onClick={() => handleSeek(row)}
                      className="font-mono text-xs text-indigo-700 hover:underline"
                    >
                      {formatTimestamp(row.timestamp_sec)}
                      {row.end_sec != null && row.end_sec !== row.timestamp_sec
                        ? `–${formatTimestamp(row.end_sec)}`
                        : ''}
                    </button>
                  )}
                  <StatusBadge status={row.three_way_status} />
                </div>
                {row.deposition_prompt && (
                  <p className="text-xs text-slate-700 mt-1 italic">{row.deposition_prompt}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {rows.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 bg-slate-50/80">
            <h4 className="text-sm font-semibold text-slate-900">Three-way test reconciliation</h4>
            <p className="text-xs text-slate-500 mt-0.5">
              Report claim ↔ named video test ↔ Hunter technique verdict
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500 border-b border-slate-200">
                  <th className="py-2.5 px-3 font-semibold">Named test</th>
                  <th className="py-2.5 px-3 font-semibold">Time</th>
                  <th className="py-2.5 px-3 font-semibold">Reconciliation</th>
                  <th className="py-2.5 px-3 font-semibold">Technique</th>
                  <th className="py-2.5 px-3 font-semibold">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={`${row.named_test_key}-${row.plane || 'na'}-${row.timestamp_sec ?? 'claim'}`}
                    onClick={() => handleSeek(row)}
                    className={`border-b border-slate-100 ${
                      row.timestamp_sec != null ? 'cursor-pointer hover:bg-slate-50' : ''
                    } ${row.three_way_status === 'performed_not_reported' ? 'bg-amber-50/50' : ''}`}
                  >
                    <td className="py-2.5 px-3">
                      <p className="font-medium text-slate-900">{row.test_name}</p>
                      {row.detection_note && (
                        <p className="text-[11px] text-slate-500 mt-0.5 line-clamp-2">{row.detection_note}</p>
                      )}
                    </td>
                    <td className="py-2.5 px-3 font-mono text-xs text-indigo-700 whitespace-nowrap">
                      {row.timestamp_sec != null ? formatTimestamp(row.timestamp_sec) : '—'}
                    </td>
                    <td className="py-2.5 px-3">
                      <StatusBadge status={row.three_way_status} />
                    </td>
                    <td className="py-2.5 px-3 text-xs text-slate-700">
                      {VERDICT_LABELS[row.technique_verdict] || row.technique_verdict || '—'}
                    </td>
                    <td className="py-2.5 px-3 text-xs text-slate-500 capitalize">
                      {row.detection_confidence || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
