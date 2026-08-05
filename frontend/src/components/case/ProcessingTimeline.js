import React from 'react';
import { motion } from 'framer-motion';

const STAGES = [
  { id: 'ingestion', label: 'File ingestion', detail: 'Videos and reports secured in storage' },
  { id: 'transcription', label: 'Transcription', detail: 'Audio extracted and transcribed' },
  { id: 'nlp', label: 'Transcript analysis', detail: 'Declared tests and conduct patterns extracted' },
  { id: 'vision', label: 'Video review', detail: 'Examination video scanned for tests and technique' },
  { id: 'report', label: 'Report generation', detail: 'Findings compiled into deliverables' },
];

export default function ProcessingTimeline({ currentStage = 'transcription', failed = false }) {
  const currentIdx = STAGES.findIndex((s) => s.id === currentStage);
  const activeIdx = currentIdx >= 0 ? currentIdx : 1;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-5">
        Processing pipeline
      </h2>
      <ol className="relative space-y-0">
        {STAGES.map((stage, i) => {
          const done = i < activeIdx;
          const active = i === activeIdx;
          const pending = i > activeIdx;

          return (
            <li key={stage.id} className="relative flex gap-4 pb-8 last:pb-0">
              {i < STAGES.length - 1 && (
                <div
                  className={`absolute left-[15px] top-8 bottom-0 w-0.5 ${
                    done ? 'bg-emerald-300' : active ? 'bg-gradient-to-b from-indigo-400 to-slate-200' : 'bg-slate-200'
                  }`}
                />
              )}
              <div className="relative z-10 flex-shrink-0">
                {done ? (
                  <div className="w-8 h-8 rounded-full bg-emerald-500 text-white flex items-center justify-center shadow-sm">
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                ) : active && failed ? (
                  <div className="w-8 h-8 rounded-full bg-rose-500 text-white flex items-center justify-center shadow-md shadow-rose-500/30">
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </div>
                ) : active ? (
                  <motion.div
                    className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 text-white flex items-center justify-center shadow-md shadow-indigo-500/30"
                    animate={{ scale: [1, 1.05, 1] }}
                    transition={{ duration: 2, repeat: Infinity }}
                  >
                    <span className="w-2.5 h-2.5 rounded-full bg-white" />
                  </motion.div>
                ) : (
                  <div className="w-8 h-8 rounded-full bg-slate-100 border-2 border-slate-200" />
                )}
              </div>
              <div className={`pt-1 ${pending ? 'opacity-50' : ''}`}>
                <div className={`text-sm font-semibold ${active ? (failed ? 'text-rose-700' : 'text-indigo-700') : done ? 'text-emerald-700' : 'text-slate-700'}`}>
                  {stage.label}
                  {active && (
                    <span className={`ml-2 text-[10px] font-bold uppercase tracking-wide ${failed ? 'text-rose-500' : 'text-indigo-500'}`}>
                      {failed ? 'Failed' : 'In progress'}
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-500 mt-0.5">{stage.detail}</div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
