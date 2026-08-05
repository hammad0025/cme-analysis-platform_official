import React from 'react';

const VARIANT_STYLES = {
  primary:
    'bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-md shadow-indigo-500/20 hover:shadow-lg hover:shadow-indigo-500/30 hover:from-indigo-500 hover:to-purple-500 disabled:from-slate-300 disabled:to-slate-300 disabled:shadow-none disabled:cursor-not-allowed',
  secondary:
    'bg-white text-slate-800 border border-slate-300 hover:bg-slate-50 hover:border-slate-400 shadow-sm disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed',
  ghost:
    'bg-transparent text-slate-700 hover:text-slate-900 hover:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed',
  danger:
    'bg-rose-600 text-white hover:bg-rose-500 shadow-sm disabled:bg-slate-300 disabled:cursor-not-allowed',
  emerald:
    'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-md shadow-emerald-500/20 hover:shadow-lg hover:shadow-emerald-500/30 hover:from-emerald-500 hover:to-teal-500 disabled:from-slate-300 disabled:to-slate-300 disabled:shadow-none disabled:cursor-not-allowed',
};

const SIZE_STYLES = {
  sm: 'h-9 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-6 text-sm',
};

export default function Button({
  variant = 'primary',
  size = 'md',
  type = 'button',
  className = '',
  disabled = false,
  onClick,
  children,
  ...rest
}) {
  const variantCls = VARIANT_STYLES[variant] || VARIANT_STYLES.primary;
  const sizeCls = SIZE_STYLES[size] || SIZE_STYLES.md;
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 font-semibold rounded-lg transition-all duration-200 ${variantCls} ${sizeCls} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
