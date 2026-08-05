import React from 'react';
import Button from '../Button';
import { formatBytes, reportShortLabel } from '../../lib/caseConstants';

const TYPE_BADGE = {
  video: 'bg-indigo-100 text-indigo-700 ring-indigo-200',
  cme_report: 'bg-indigo-100 text-indigo-700 ring-indigo-200',
  initial_ime: 'bg-purple-100 text-purple-700 ring-purple-200',
  medical_history: 'bg-violet-100 text-violet-700 ring-violet-200',
  other: 'bg-slate-100 text-slate-600 ring-slate-200',
};

export default function FileCard({
  kind = 'video',
  name,
  size,
  badge,
  badgeType,
  onRemove,
  onReplace,
  children,
  index,
}) {
  const isVideo = kind === 'video';
  const badgeCls = TYPE_BADGE[badgeType || kind] || TYPE_BADGE.other;

  return (
    <div className="group rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:shadow-md hover:border-slate-300 transition-all duration-200 animate-fade-in">
      <div className="flex items-start gap-3">
        <div
          className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${
            isVideo ? 'bg-gradient-to-br from-indigo-500 to-indigo-600 text-white shadow-sm' : 'bg-gradient-to-br from-purple-500 to-purple-600 text-white shadow-sm'
          }`}
        >
          {isVideo ? (
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          ) : (
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
            </svg>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {typeof index === 'number' && (
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                #{index + 1}
              </span>
            )}
            <span className={`inline-flex text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full ring-1 ${badgeCls}`}>
              {badge || (isVideo ? 'Video' : reportShortLabel(badgeType))}
            </span>
          </div>
          <div className="text-sm font-semibold text-slate-900 truncate mt-1" title={name}>
            {name}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">{formatBytes(size)}</div>
          {children && <div className="mt-3">{children}</div>}
        </div>

        <div className="flex flex-col sm:flex-row items-end sm:items-center gap-1.5 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
          {onReplace && (
            <Button variant="ghost" size="sm" onClick={onReplace}>
              Replace
            </Button>
          )}
          {onRemove && (
            <Button variant="ghost" size="sm" onClick={onRemove} className="text-rose-600 hover:text-rose-700 hover:bg-rose-50">
              Remove
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export function ProgressBar({ percent, variant = 'indigo', size = 'md' }) {
  const pct = Math.max(0, Math.min(100, percent || 0));
  const fill = variant === 'emerald' ? 'bg-emerald-500' : 'bg-gradient-to-r from-indigo-500 to-purple-500';
  const height = size === 'sm' ? 'h-1.5' : 'h-2';
  return (
    <div className={`w-full rounded-full bg-slate-200 overflow-hidden ${height}`}>
      <div className={`h-full ${fill} transition-all duration-150 rounded-full`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function FileProgressRow({ label, percent }) {
  const pct = Number.isFinite(percent) ? percent : 0;
  const done = pct >= 100;
  return (
    <li className="space-y-1.5">
      <div className="flex items-center justify-between text-xs gap-3">
        <span className="text-slate-700 truncate" title={label}>{label}</span>
        <span className={`font-mono flex-shrink-0 ${done ? 'text-emerald-600' : 'text-slate-500'}`}>
          {done ? 'Done' : `${Math.round(pct)}%`}
        </span>
      </div>
      <ProgressBar percent={pct} variant={done ? 'emerald' : 'indigo'} size="sm" />
    </li>
  );
}
