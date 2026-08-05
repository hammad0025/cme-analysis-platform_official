import React from 'react';
import { STATUS_CONFIG } from '../../lib/caseConstants';

const TONE_CLASSES = {
  blue: 'bg-blue-50 text-blue-700 ring-blue-200/80',
  amber: 'bg-amber-50 text-amber-700 ring-amber-200/80',
  indigo: 'bg-indigo-50 text-indigo-700 ring-indigo-200/80',
  purple: 'bg-purple-50 text-purple-700 ring-purple-200/80',
  emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200/80',
  rose: 'bg-rose-50 text-rose-700 ring-rose-200/80',
};

export default function StatusBadge({ status, className = '', compact = false }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.created;
  const tone = TONE_CLASSES[cfg.tone] || TONE_CLASSES.blue;
  const sizeCls = compact
    ? 'text-[9px] gap-1 px-1.5 py-0.5 tracking-normal normal-case'
    : 'text-[11px] gap-1.5 px-2.5 py-1 uppercase tracking-wide';

  return (
    <span
      className={`inline-flex items-center font-semibold rounded-full ring-1 ${sizeCls} ${tone} ${className}`}
    >
      {cfg.pulse && (
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-40" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-current" />
        </span>
      )}
      {!cfg.pulse && <span className="w-1.5 h-1.5 rounded-full bg-current" />}
      {cfg.label}
    </span>
  );
}
