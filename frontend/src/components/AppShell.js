import React, { useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import CasesSidebar from './layout/CasesSidebar';
import { isMockMode } from '../services/casesService';

export default function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const mock = isMockMode();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-slate-50 to-indigo-50/30 flex">
      <CasesSidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0 lg:min-h-screen">
        <header className="lg:hidden sticky top-0 z-30 flex items-center gap-3 px-4 h-14 bg-white/90 backdrop-blur-xl border-b border-slate-200/80 shadow-sm">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="p-2 -ml-1 rounded-lg text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors"
            aria-label="Open cases menu"
          >
            <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-slate-900 truncate">CME Analysis</div>
            {mock && (
              <div className="text-[10px] text-indigo-600 font-semibold uppercase tracking-wide">Mock mode</div>
            )}
          </div>
        </header>

        <motion.main
          key={location.pathname}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
          className="flex-1 min-h-0 overflow-y-auto"
        >
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 lg:py-10">
            <Outlet />
          </div>
        </motion.main>

        <footer className="flex-shrink-0 px-4 sm:px-6 lg:px-8 py-4 text-xs text-slate-400 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200/60 bg-white/50">
          <span>CME Analysis Platform · Internal preview</span>
          <span className="font-mono text-[10px]">
            {mock ? 'Mock API' : 'Live API'}
            {process.env.REACT_APP_DEV_MODE === 'true' ? ' · Dev' : ''}
          </span>
        </footer>
      </div>
    </div>
  );
}
