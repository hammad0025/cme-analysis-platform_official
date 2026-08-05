import React from 'react';
import Button from '../Button';

function PdfIcon({ className = 'w-5 h-5' }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
      />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 3v6h6M9 13h6M9 17h4" />
    </svg>
  );
}

export function PdfDownloadButton({ pdfUrl, size = 'md', className = '', onClick }) {
  if (!pdfUrl && !onClick) return null;

  const content = (
    <>
      <PdfIcon className={size === 'lg' ? 'w-6 h-6' : 'w-5 h-5'} />
      Final CME Report (PDF)
    </>
  );

  if (pdfUrl) {
    return (
      <a href={pdfUrl} target="_blank" rel="noreferrer" download className={className}>
        <Button variant="primary" size={size} className="!shadow-lg !shadow-indigo-500/30">
          {content}
        </Button>
      </a>
    );
  }

  return (
    <Button variant="primary" size={size} className={`!shadow-lg !shadow-indigo-500/30 ${className}`} onClick={onClick}>
      {content}
    </Button>
  );
}

export default function PdfReportPanel({
  pdfUrl,
  loading = false,
  error = '',
  showEmbed = true,
  title = 'Final CME Report (PDF)',
  className = '',
}) {
  if (loading) {
    return (
      <div className={`rounded-2xl border border-slate-200 bg-white p-6 shadow-sm ${className}`}>
        <div className="h-12 rounded-xl shimmer mb-4" />
        {showEmbed && <div className="h-[min(70vh,720px)] rounded-xl shimmer" />}
      </div>
    );
  }

  if (!pdfUrl) {
    if (!error) return null;
    return (
      <div className={`rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900 ${className}`}>
        {error}
      </div>
    );
  }

  return (
    <div className={`rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50/80 to-purple-50/60 shadow-sm overflow-hidden ${className}`}>
      <div className="p-5 sm:p-6 flex flex-wrap items-center justify-between gap-4 border-b border-indigo-100/80 bg-white/60">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-gradient-to-br from-indigo-600 to-purple-600 text-white shadow-md shadow-indigo-500/30">
            <PdfIcon />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-900">{title}</h3>
            <p className="text-xs text-slate-600 mt-0.5">Official deliverable · ready to share with counsel</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <PdfDownloadButton pdfUrl={pdfUrl} size="md" />
          <a
            href={pdfUrl}
            target="_blank"
            rel="noreferrer"
            className="text-sm font-semibold text-indigo-700 hover:text-indigo-900 underline underline-offset-2"
          >
            Open PDF in new tab
          </a>
        </div>
      </div>
      {showEmbed && (
        <div className="p-4 sm:p-5 bg-slate-100/80">
          <div className="rounded-xl border border-slate-200 overflow-hidden bg-white shadow-inner">
            <iframe
              title={title}
              src={pdfUrl}
              className="w-full bg-white"
              style={{ height: 'min(70vh, 720px)', minHeight: '480px' }}
            />
          </div>
          <p className="mt-3 text-xs text-slate-500 text-center">
            If the preview does not load, use{' '}
            <a href={pdfUrl} target="_blank" rel="noreferrer" className="font-semibold text-indigo-600 hover:text-indigo-800">
              Open PDF in new tab
            </a>
            .
          </p>
        </div>
      )}
    </div>
  );
}
