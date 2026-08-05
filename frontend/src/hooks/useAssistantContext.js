import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  detectContextType,
  extractRouteParams,
  loadContextData,
  getSuggestedQuestions,
} from '../services/caseAssistantService';

const AssistantContext = createContext(null);

export function AssistantProvider({ children }) {
  const location = useLocation();
  const pathname = location.pathname;

  const contextType = useMemo(() => detectContextType(pathname), [pathname]);
  const routeParams = useMemo(() => extractRouteParams(pathname), [pathname]);

  const [contextData, setContextData] = useState({
    contextType,
    ...routeParams,
    loadedAt: null,
    error: null,
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      const data = await loadContextData(contextType, routeParams);
      if (!cancelled) {
        setContextData(data);
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [contextType, routeParams]);

  const suggestedQuestions = useMemo(
    () => getSuggestedQuestions(contextType, contextData),
    [contextType, contextData],
  );

  const refreshContext = useCallback(async () => {
    setLoading(true);
    const data = await loadContextData(contextType, routeParams);
    setContextData(data);
    setLoading(false);
  }, [contextType, routeParams]);

  const value = useMemo(
    () => ({
      contextType,
      contextData,
      suggestedQuestions,
      loading,
      refreshContext,
      pathname,
    }),
    [contextType, contextData, suggestedQuestions, loading, refreshContext, pathname],
  );

  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}

export function useAssistantContext() {
  const ctx = useContext(AssistantContext);
  if (!ctx) {
    throw new Error('useAssistantContext must be used within AssistantProvider');
  }
  return ctx;
}
