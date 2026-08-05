import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useAssistantContext } from '../../hooks/useAssistantContext';
import ChatMessage, { TypingIndicator } from './ChatMessage';
import ChatInput from './ChatInput';
import {
  answerQuestion,
  getWelcomeMessage,
  loadChatHistory,
  saveChatHistory,
} from '../../services/caseAssistantService';

const MIN_TYPING_MS = 400;

export default function CaseAssistant() {
  const { user } = useAuth();
  const location = useLocation();
  const { contextType, contextData, suggestedQuestions, loading: contextLoading } = useAssistantContext();

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState(() => loadChatHistory());
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [unread, setUnread] = useState(0);

  const scrollRef = useRef(null);
  const prevContextRef = useRef(contextType);

  const isLogin = location.pathname === '/login';
  const visible = !!user && !isLogin;

  useEffect(() => {
    saveChatHistory(messages);
  }, [messages]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, typing, open]);

  useEffect(() => {
    if (prevContextRef.current !== contextType && open) {
      setMessages((prev) => [
        ...prev,
        {
          id: `ctx-${Date.now()}`,
          role: 'assistant',
          content: getWelcomeMessage(contextType),
          timestamp: Date.now(),
        },
      ]);
    }
    prevContextRef.current = contextType;
  }, [contextType, open]);

  const handleOpen = () => {
    setOpen(true);
    setUnread(0);
    if (messages.length === 0) {
      setMessages([
        {
          id: 'welcome',
          role: 'assistant',
          content: getWelcomeMessage(contextType),
          timestamp: Date.now(),
        },
      ]);
    }
  };

  const sendMessage = useCallback(
    async (text) => {
      const trimmed = (text || input).trim();
      if (!trimmed || typing) return;

      const userMsg = {
        id: `u-${Date.now()}`,
        role: 'user',
        content: trimmed,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setInput('');
      setTyping(true);

      const started = Date.now();
      try {
        const { answer } = await answerQuestion(trimmed, contextData);
        const elapsed = Date.now() - started;
        if (elapsed < MIN_TYPING_MS) {
          await new Promise((r) => setTimeout(r, MIN_TYPING_MS - elapsed));
        }
        const assistantMsg = {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: answer,
          timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
        if (!open) setUnread((n) => n + 1);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            id: `e-${Date.now()}`,
            role: 'error',
            content: err.message || 'Something went wrong. Please try again.',
            timestamp: Date.now(),
          },
        ]);
      } finally {
        setTyping(false);
      }
    },
    [input, typing, contextData, open],
  );

  const handleClear = () => {
    setMessages([
      {
        id: 'welcome-reset',
        role: 'assistant',
        content: getWelcomeMessage(contextType),
        timestamp: Date.now(),
      },
    ]);
  };

  if (!visible) return null;

  return (
    <>
      <AnimatePresence>
        {open && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-slate-900/20 backdrop-blur-[2px] z-40 sm:hidden"
              onClick={() => setOpen(false)}
              aria-hidden
            />
            <motion.section
              initial={{ opacity: 0, y: 24, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 24, scale: 0.96 }}
              transition={{ type: 'spring', damping: 26, stiffness: 320 }}
              className="fixed z-[100] flex flex-col bg-white shadow-2xl shadow-indigo-900/10 border border-slate-200/80 overflow-hidden
                inset-x-3 bottom-20 top-auto h-[min(70vh,520px)] rounded-2xl
                sm:inset-auto sm:bottom-24 sm:right-6 sm:w-[400px] sm:h-[min(560px,calc(100vh-7rem))] sm:rounded-2xl"
              role="dialog"
              aria-label="Case Assistant chat"
              aria-modal="true"
            >
              <header className="flex-shrink-0 flex items-center justify-between gap-3 px-4 py-3.5 bg-gradient-to-r from-indigo-600 via-indigo-600 to-purple-600 text-white">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-9 h-9 rounded-xl bg-white/15 backdrop-blur flex items-center justify-center flex-shrink-0">
                    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                  </div>
                  <div className="min-w-0">
                    <h2 className="text-sm font-bold leading-tight truncate">Case Assistant</h2>
                    <p className="text-[11px] text-indigo-100/80 leading-tight truncate">
                      {contextLoading ? 'Loading context…' : 'Context-aware · Rule-based v1'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button
                    type="button"
                    onClick={handleClear}
                    className="p-2 rounded-lg text-indigo-100 hover:text-white hover:bg-white/10 transition-colors"
                    aria-label="Clear conversation"
                    title="Clear conversation"
                  >
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="p-2 rounded-lg text-indigo-100 hover:text-white hover:bg-white/10 transition-colors"
                    aria-label="Close Case Assistant"
                  >
                    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </header>

              <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4 bg-gradient-to-b from-slate-50/80 to-white">
                {messages.length <= 1 && !typing && (
                  <EmptyState
                    suggestedQuestions={suggestedQuestions}
                    onSelect={(q) => sendMessage(q)}
                  />
                )}
                {messages.map((msg) => (
                  <ChatMessage key={msg.id} message={msg} />
                ))}
                {typing && <TypingIndicator />}
              </div>

              {suggestedQuestions.length > 0 && messages.length > 1 && !typing && (
                <div className="flex-shrink-0 px-3 py-2 border-t border-slate-100 bg-slate-50/50 overflow-x-auto">
                  <div className="flex gap-2">
                    {suggestedQuestions.slice(0, 2).map((q) => (
                      <button
                        key={q}
                        type="button"
                        onClick={() => sendMessage(q)}
                        className="flex-shrink-0 text-[11px] font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200/60 rounded-full px-3 py-1.5 transition-colors whitespace-nowrap"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <ChatInput
                value={input}
                onChange={setInput}
                onSend={() => sendMessage(input)}
                disabled={typing}
              />
            </motion.section>
          </>
        )}
      </AnimatePresence>

      <motion.button
        type="button"
        onClick={open ? () => setOpen(false) : handleOpen}
        className="fixed bottom-6 right-6 z-[100] w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-600 to-purple-600 text-white shadow-xl shadow-indigo-500/30 hover:shadow-2xl hover:shadow-indigo-500/40 flex items-center justify-center transition-shadow ring-2 ring-white/80"
        whileHover={{ scale: 1.04 }}
        whileTap={{ scale: 0.96 }}
        aria-label={open ? 'Close Case Assistant' : 'Open Case Assistant'}
        aria-expanded={open}
      >
        {unread > 0 && !open && (
          <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-rose-500 text-[10px] font-bold flex items-center justify-center ring-2 ring-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
        <AnimatePresence mode="wait">
          {open ? (
            <motion.svg
              key="close"
              initial={{ rotate: -90, opacity: 0 }}
              animate={{ rotate: 0, opacity: 1 }}
              exit={{ rotate: 90, opacity: 0 }}
              className="w-6 h-6"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </motion.svg>
          ) : (
            <motion.svg
              key="chat"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              className="w-6 h-6"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </motion.svg>
          )}
        </AnimatePresence>
      </motion.button>
    </>
  );
}

function EmptyState({ suggestedQuestions, onSelect }) {
  return (
    <div className="text-center py-6 px-2">
      <div className="w-14 h-14 mx-auto rounded-2xl bg-gradient-to-br from-indigo-100 to-purple-100 flex items-center justify-center mb-4">
        <svg className="w-7 h-7 text-indigo-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
      <p className="text-sm font-semibold text-slate-800 mb-1">Ask anything about this case</p>
      <p className="text-xs text-slate-500 mb-5 max-w-[260px] mx-auto leading-relaxed">
        I pull answers from loaded case data and platform knowledge — no API keys required.
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        {suggestedQuestions.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onSelect(q)}
            className="text-xs font-medium text-indigo-700 bg-white hover:bg-indigo-50 border border-indigo-200/70 rounded-full px-3.5 py-2 shadow-sm transition-all hover:shadow-md hover:border-indigo-300"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
