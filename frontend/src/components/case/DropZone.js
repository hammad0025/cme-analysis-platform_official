import React, { useState } from 'react';
import Button from '../Button';

export default function DropZone({
  accept,
  multiple = false,
  onFiles,
  inputRef,
  icon: Icon,
  title,
  subtitle,
  accent = 'indigo',
  disabled = false,
}) {
  const [dragging, setDragging] = useState(false);

  const accentMap = {
    indigo: {
      border: dragging ? 'border-indigo-400 bg-indigo-50/80' : 'border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/40',
      icon: 'bg-indigo-100 text-indigo-600',
      ring: 'ring-indigo-500/20',
    },
    purple: {
      border: dragging ? 'border-purple-400 bg-purple-50/80' : 'border-slate-200 hover:border-purple-300 hover:bg-purple-50/40',
      icon: 'bg-purple-100 text-purple-600',
      ring: 'ring-purple-500/20',
    },
  };
  const accentClasses = accentMap[accent] || accentMap.indigo;

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    onFiles(e.dataTransfer.files);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`relative rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-all duration-200 ${
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
      } ${accentClasses.border} ${dragging ? `ring-4 ${accentClasses.ring}` : ''}`}
      onClick={() => !disabled && inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          if (!disabled) inputRef.current?.click();
        }
      }}
    >
      {Icon && (
        <div className={`mx-auto w-14 h-14 rounded-2xl ${accentClasses.icon} flex items-center justify-center mb-4 shadow-sm`}>
          <Icon className="w-7 h-7" />
        </div>
      )}
      <div className="text-sm font-semibold text-slate-800">{title}</div>
      {subtitle && <div className="text-xs text-slate-500 mt-1.5 max-w-sm mx-auto">{subtitle}</div>}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        onChange={(e) => {
          onFiles(e.target.files);
          e.target.value = '';
        }}
        className="hidden"
      />
      <Button
        variant="secondary"
        size="md"
        className="mt-5 pointer-events-none"
        tabIndex={-1}
      >
        Browse files
      </Button>
    </div>
  );
}

export function VideoIcon({ className = 'w-7 h-7' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
    </svg>
  );
}

export function PdfIcon({ className = 'w-7 h-7' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 13h6M9 17h4" />
    </svg>
  );
}
