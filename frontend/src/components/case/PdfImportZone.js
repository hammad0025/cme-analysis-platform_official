import React, { useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Button from '../Button';
import { PdfIcon } from './DropZone';
import { PDF_ACCEPT } from '../../lib/caseConstants';
import { formatParsePreview } from '../../lib/pdfCaseParser';

const CONFIDENCE_STYLES = {
  high: 'bg-emerald-50 border-emerald-200 text-emerald-800',
  medium: 'bg-indigo-50 border-indigo-200 text-indigo-800',
  low: 'bg-amber-50 border-amber-200 text-amber-800',
  none: 'bg-slate-50 border-slate-200 text-slate-600',
};

const FIELD_LABELS = {
  plaintiff_name: 'Plaintiff',
  examiner_name: 'Examiner',
  exam_date: 'Exam date',
  date_of_injury: 'Date of injury',
  date_of_birth: 'Date of birth',
  state: 'State',
  case_caption: 'Case caption',
  claim_number: 'Claim / case no.',
};

export default function PdfImportZone({
  loading,
  error,
  preview,
  onImport,
  onDismissPreview,
  disabled,
}) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const onFiles = (files) => {
    const file = files?.[0];
    if (file) onImport(file);
  };

  return (
    <div className="mb-8">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled && !loading) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!disabled && !loading) onFiles(e.dataTransfer.files);
        }}
        className={`relative rounded-xl border-2 border-dashed px-5 py-6 transition-all duration-200 ${
          disabled || loading ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'
        } ${
          dragging
            ? 'border-purple-400 bg-purple-50/80 ring-4 ring-purple-500/20'
            : 'border-slate-200 bg-gradient-to-br from-slate-50 to-indigo-50/30 hover:border-indigo-300 hover:bg-indigo-50/40'
        }`}
        onClick={() => !disabled && !loading && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            if (!disabled && !loading) inputRef.current?.click();
          }
        }}
      >
        <div className="flex items-start gap-4">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-indigo-100 to-purple-100 text-indigo-600 flex items-center justify-center flex-shrink-0 shadow-sm">
            {loading ? (
              <svg className="w-5 h-5 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <PdfIcon className="w-5 h-5" />
            )}
          </div>
          <div className="flex-1 min-w-0 text-left">
            <div className="text-sm font-semibold text-slate-800">
              {loading ? 'Reading report…' : 'Import from PDF'}
            </div>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              {loading
                ? 'Extracting case details from the first few pages of your CME report.'
                : 'Drop a defense expert or IME report to auto-fill plaintiff, examiner, and key dates.'}
            </p>
            {!loading && (
              <Button variant="secondary" size="sm" className="mt-3 pointer-events-none" tabIndex={-1}>
                Choose PDF
              </Button>
            )}
          </div>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={PDF_ACCEPT}
          disabled={disabled || loading}
          onChange={(e) => {
            onFiles(e.target.files);
            e.target.value = '';
          }}
          className="hidden"
        />
      </div>

      {error && (
        <div className="mt-3 p-3 text-xs font-medium text-amber-800 bg-amber-50 border border-amber-200 rounded-xl">
          {error}
        </div>
      )}

      <AnimatePresence>
        {preview && !loading && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
            className={`mt-4 rounded-xl border p-4 ${CONFIDENCE_STYLES[preview.confidence] || CONFIDENCE_STYLES.none}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-xs font-bold uppercase tracking-wide opacity-80">
                  {preview.confidence === 'none' ? 'Limited details found' : 'We found'}
                </div>
                {preview.confidence !== 'none' ? (
                  <p className="text-sm font-semibold mt-1 truncate">{formatParsePreview(preview.fields)}</p>
                ) : (
                  <p className="text-sm mt-1">
                    Couldn&apos;t confidently read case details from this PDF. You can still enter them manually below.
                  </p>
                )}
                {preview.fields_found?.length > 0 && (
                  <ul className="mt-3 flex flex-wrap gap-2">
                    {preview.fields_found.map((key) => (
                      <li
                        key={key}
                        className="text-[10px] font-semibold uppercase tracking-wide bg-white/70 border border-current/10 rounded-full px-2.5 py-1"
                      >
                        {FIELD_LABELS[key] || key}
                      </li>
                    ))}
                  </ul>
                )}
                {preview.sourceFilename && (
                  <p className="text-[11px] mt-2 opacity-70 truncate">
                    From {preview.sourceFilename}
                    {preview.pagesRead ? ` · ${preview.pagesRead} page${preview.pagesRead !== 1 ? 's' : ''} scanned` : ''}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onDismissPreview?.();
                }}
                className="text-xs font-medium opacity-60 hover:opacity-100 flex-shrink-0"
              >
                Dismiss
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
