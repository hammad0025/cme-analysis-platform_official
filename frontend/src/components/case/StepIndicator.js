import React from 'react';
import { motion } from 'framer-motion';

export default function StepIndicator({ steps, currentStep, onJump }) {
  const progress = ((currentStep - 1) / (steps.length - 1)) * 100;

  return (
    <div className="w-full">
      <div className="hidden sm:block relative mb-8">
        <div className="absolute top-5 left-0 right-0 h-0.5 bg-slate-200 rounded-full" />
        <motion.div
          className="absolute top-5 left-0 h-0.5 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full"
          initial={false}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
        />
        <ol className="relative flex justify-between">
          {steps.map((step) => {
            const active = currentStep === step.id;
            const done = currentStep > step.id;
            return (
              <li key={step.id} className="flex flex-col items-center">
                <button
                  type="button"
                  onClick={() => onJump(step.id)}
                  className={`group relative z-10 w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold transition-all duration-200 ${
                    active
                      ? 'bg-gradient-to-br from-indigo-600 to-purple-600 text-white shadow-lg shadow-indigo-500/30 ring-4 ring-indigo-100'
                      : done
                      ? 'bg-emerald-500 text-white shadow-md shadow-emerald-500/20'
                      : 'bg-white text-slate-400 border-2 border-slate-200 group-hover:border-indigo-300 group-hover:text-indigo-600'
                  }`}
                >
                  {done ? (
                    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    step.id
                  )}
                </button>
                <div className="mt-3 text-center max-w-[7rem]">
                  <div
                    className={`text-xs font-semibold ${
                      active ? 'text-indigo-700' : done ? 'text-emerald-700' : 'text-slate-500'
                    }`}
                  >
                    {step.title}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5 hidden lg:block">{step.description}</div>
                </div>
              </li>
            );
          })}
        </ol>
      </div>

      <div className="sm:hidden flex items-center gap-3 p-4 rounded-xl bg-white border border-slate-200 shadow-sm">
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-600 to-purple-600 text-white flex items-center justify-center text-sm font-bold shadow-md">
          {currentStep}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-slate-900">
            {steps.find((s) => s.id === currentStep)?.title}
          </div>
          <div className="text-xs text-slate-500">
            Step {currentStep} of {steps.length}
          </div>
        </div>
        <div className="text-xs font-mono text-slate-400">
          {Math.round((currentStep / steps.length) * 100)}%
        </div>
      </div>
    </div>
  );
}
