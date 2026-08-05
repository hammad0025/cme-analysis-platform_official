import React, { useRef, useEffect } from 'react';
import Button from '../Button';

export default function ChatInput({ value, onChange, onSend, disabled, placeholder }) {
  const inputRef = useRef(null);

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 120)}px`;
    }
  }, [value]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !disabled) onSend();
    }
  };

  return (
    <div className="flex items-end gap-2 p-3 border-t border-slate-200/80 bg-white/95 backdrop-blur-sm">
      <label htmlFor="case-assistant-input" className="sr-only">
        Ask the Case Assistant
      </label>
      <textarea
        id="case-assistant-input"
        ref={inputRef}
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder || 'Ask about this case…'}
        className="flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 disabled:opacity-50 min-h-[42px] max-h-[120px]"
      />
      <Button
        type="button"
        size="md"
        disabled={disabled || !value.trim()}
        onClick={onSend}
        aria-label="Send message"
        className="!rounded-xl flex-shrink-0"
      >
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
        </svg>
      </Button>
    </div>
  );
}
