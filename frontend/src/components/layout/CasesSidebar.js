import React, { useCallback, useEffect, useState } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../../contexts/AuthContext';
import StatusBadge from '../case/StatusBadge';
import { caseDetailPath, isCaseDetailActive } from '../../lib/caseRoutes';
import { clearAllMockCases, isMockMode, listCases } from '../../services/casesService';
import { DEV_MODE } from '../../config/runtime';

const PRIMARY_NAV = [
  {
    to: '/',
    label: 'Dashboard',
    end: true,
    icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6',
  },
  {
    to: '/cases/new',
    label: 'New case',
    end: false,
    icon: 'M12 4v16m8-8H4',
    accent: true,
  },
  {
    to: '/cases/sample',
    label: 'Sample case',
    end: false,
    icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
  },
];

function NavIcon({ d, className = 'w-5 h-5' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  );
}

export default function CasesSidebar({ mobileOpen, onClose }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const mock = isMockMode();

  const [cases, setCases] = useState([]);
  const [loadingCases, setLoadingCases] = useState(true);
  const [resetting, setResetting] = useState(false);

  const refreshCases = useCallback(async () => {
    setLoadingCases(true);
    try {
      const { cases: list } = await listCases();
      setCases(list);
    } catch (_err) {
      setCases([]);
    } finally {
      setLoadingCases(false);
    }
  }, []);

  useEffect(() => {
    refreshCases();
  }, [refreshCases, location.pathname]);

  useEffect(() => {
    if (mobileOpen) onClose?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const onResetDemo = async () => {
    if (!window.confirm('Clear all local mock cases from this browser?')) return;
    setResetting(true);
    clearAllMockCases();
    await refreshCases();
    setResetting(false);
    if (location.pathname !== '/') navigate('/');
  };

  const sidebarContent = (
    <div className="flex flex-col h-full">
      <div className="flex-shrink-0 px-4 pt-5 pb-4 border-b border-slate-200/80">
        <Link to="/" className="flex items-center gap-3 group" onClick={onClose}>
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-600 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/25 group-hover:shadow-indigo-500/40 transition-shadow">
            <NavIcon d="M9 11h6M9 15h6M9 7h6M5 7v14a1 1 0 001 1h12a1 1 0 001-1V5a1 1 0 00-1-1H8L5 7z" className="w-5 h-5 text-white" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-bold text-slate-900 leading-tight truncate">CME Analysis</div>
            <div className="text-[11px] text-slate-500 leading-tight">Defense scrutiny platform</div>
          </div>
        </Link>
        {mock && (
          <div className="mt-3 inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-full px-2.5 py-1">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
            Mock API
          </div>
        )}
      </div>

      <nav className="flex-shrink-0 px-3 py-4 space-y-1">
        {PRIMARY_NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={onClose}
            className={({ isActive }) =>
              `group flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
                isActive
                  ? item.accent
                    ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-md shadow-indigo-500/25'
                    : 'bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200/80'
                  : item.accent
                    ? 'text-indigo-700 hover:bg-indigo-50 hover:text-indigo-800'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={`flex items-center justify-center w-8 h-8 rounded-lg transition-colors ${
                    isActive && item.accent
                      ? 'bg-white/15'
                      : isActive
                        ? 'bg-indigo-100 text-indigo-600'
                        : 'bg-slate-100 text-slate-500 group-hover:bg-slate-200 group-hover:text-slate-700'
                  }`}
                >
                  <NavIcon d={item.icon} className="w-4 h-4" />
                </span>
                {item.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="flex-1 min-h-0 flex flex-col px-3 pb-3">
        <div className="flex items-center justify-between px-2 mb-2">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Your cases</span>
          <button
            type="button"
            onClick={refreshCases}
            className="p-1 rounded-md text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
            aria-label="Refresh cases"
            title="Refresh cases"
          >
            <NavIcon d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-1 pr-1 -mr-1 scrollbar-thin">
          {loadingCases ? (
            <div className="px-2 space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-14 rounded-xl shimmer" />
              ))}
            </div>
          ) : cases.length === 0 ? (
            <div className="mx-1 rounded-xl border border-dashed border-slate-200 bg-slate-50/80 p-4 text-center">
              <p className="text-xs text-slate-500 leading-relaxed">No cases yet</p>
              <Link
                to="/cases/new"
                onClick={onClose}
                className="mt-2 inline-flex text-xs font-semibold text-indigo-600 hover:text-indigo-800"
              >
                Create your first case →
              </Link>
            </div>
          ) : (
            cases.map((c) => {
              const path = caseDetailPath(c);
              const plaintiff = c.plaintiff_name || c.patient_name || 'Unnamed case';
              const isActive = isCaseDetailActive(location.pathname, c.case_id, c.is_mock);

              return (
                <Link
                  key={`${c.case_id}-${c.is_mock ? 'm' : 'l'}`}
                  to={path}
                  onClick={onClose}
                  className={`block rounded-xl px-3 py-2.5 transition-all duration-200 border ${
                    isActive
                      ? 'bg-indigo-50 border-indigo-200 shadow-sm'
                      : 'border-transparent hover:bg-slate-100 hover:border-slate-200'
                  }`}
                >
                  <div className="flex items-start gap-2.5">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-slate-600 to-slate-800 text-white flex items-center justify-center text-xs font-bold flex-shrink-0">
                      {plaintiff.charAt(0).toUpperCase()}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-slate-900 truncate">{plaintiff}</div>
                      <div className="text-[11px] text-slate-500 truncate mt-0.5">
                        {c.examiner_name || c.doctor_name || 'Examiner pending'}
                      </div>
                      <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
                        <StatusBadge status={c.status} compact />
                        {c.is_mock && (
                          <span className="text-[9px] font-bold uppercase text-slate-400">local</span>
                        )}
                      </div>
                    </div>
                  </div>
                </Link>
              );
            })
          )}
        </div>
      </div>

      <div className="flex-shrink-0 border-t border-slate-200/80 p-4 space-y-3">
        {user && (
          <div className="flex items-center gap-3 px-1">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 text-white flex items-center justify-center text-sm font-bold flex-shrink-0">
              {(user.given_name || user.email || 'U').charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-xs font-semibold text-slate-900 truncate">
                {user.email || user.username || 'Signed in'}
              </div>
              <div className="text-[10px] text-slate-500 truncate">
                {user.given_name ? `${user.given_name} ${user.family_name || ''}`.trim() : 'Authenticated'}
              </div>
            </div>
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <button
            type="button"
            onClick={handleLogout}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm font-medium text-slate-600 rounded-lg hover:bg-slate-100 hover:text-slate-900 transition-colors"
          >
            <NavIcon d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" className="w-4 h-4" />
            Sign out
          </button>

          {DEV_MODE && (
            <button
              type="button"
              onClick={onResetDemo}
              disabled={resetting}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-slate-400 rounded-lg hover:bg-rose-50 hover:text-rose-600 transition-colors disabled:opacity-50"
            >
              <NavIcon d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" className="w-3.5 h-3.5" />
              {resetting ? 'Resetting…' : 'Reset demo data'}
            </button>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <>
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-40 lg:hidden"
            onClick={onClose}
            aria-hidden
          />
        )}
      </AnimatePresence>

      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-[min(100vw-3rem,18rem)] lg:w-72 flex-shrink-0 bg-white border-r border-slate-200/80 shadow-xl lg:shadow-none transform transition-transform duration-300 ease-out ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
        aria-label="Cases navigation"
      >
        {sidebarContent}
      </aside>
    </>
  );
}
