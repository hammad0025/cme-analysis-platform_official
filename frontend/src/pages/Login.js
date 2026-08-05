import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const DEV_MODE = process.env.REACT_APP_DEV_MODE === 'true';

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const from = location.state?.from?.pathname || '/';

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(DEV_MODE ? username || 'demo' : username, DEV_MODE ? password || 'demo' : password);
      navigate(from, { replace: true });
    } catch (err) {
      console.error('Login error:', err);
      
      if (err.code === 'UserNotFoundException') {
        setError('User not found. Please check your email.');
      } else if (err.code === 'NotAuthorizedException') {
        setError('Incorrect password. Please try again.');
      } else if (err.code === 'NewPasswordRequired' || err.code === 'PasswordResetRequiredException') {
        setError('Password reset required. Please contact your administrator.');
      } else {
        setError(err.message || 'Failed to login. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-950 to-purple-950 flex items-center justify-center p-4">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-indigo-500 rounded-full mix-blend-screen filter blur-3xl opacity-25 animate-blob"></div>
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-purple-600 rounded-full mix-blend-screen filter blur-3xl opacity-20 animate-blob animation-delay-2000"></div>
        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-80 h-80 bg-fuchsia-600 rounded-full mix-blend-screen filter blur-3xl opacity-15 animate-blob animation-delay-4000"></div>
      </div>

      <div className="relative w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-2xl shadow-xl mb-4">
            <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h1 className="text-2xl font-semibold text-white mb-1 tracking-tight">CME Analysis Platform</h1>
          <p className="text-sm text-indigo-200">Defense scrutiny for plaintiff counsel</p>
        </div>

        <div className="bg-white/95 backdrop-blur-xl rounded-2xl shadow-2xl p-8 border border-white/20">
          {DEV_MODE && (
            <div className="mb-5 p-3 rounded-lg bg-indigo-50 border border-indigo-200 text-xs text-indigo-800 leading-relaxed">
              <strong className="font-semibold">Dev mode is active.</strong> Press <em>Sign in</em> with anything (or nothing) — credentials are not validated locally.
            </div>
          )}
          <h2 className="text-xl font-semibold text-slate-900 mb-1">Welcome back</h2>
          <p className="text-sm text-slate-600 mb-6">Sign in to access your dashboard</p>

          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-800 flex items-start gap-3">
                <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{error}</span>
              </div>
            )}

            <div>
              <label htmlFor="username" className="block text-xs font-semibold uppercase tracking-wide text-slate-700 mb-1.5">
                Email address
              </label>
              <input
                id="username"
                type={DEV_MODE ? 'text' : 'email'}
                required={!DEV_MODE}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full h-11 px-3 text-sm bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                placeholder={DEV_MODE ? 'demo' : 'counsel@lawfirm.com'}
                disabled={loading}
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-xs font-semibold uppercase tracking-wide text-slate-700 mb-1.5">
                Password
              </label>
              <input
                id="password"
                type="password"
                required={!DEV_MODE}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full h-11 px-3 text-sm bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                placeholder={DEV_MODE ? 'demo' : '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022'}
                disabled={loading}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full h-11 bg-gradient-to-r from-indigo-600 to-purple-600 text-white text-sm font-semibold rounded-lg shadow-md hover:shadow-lg hover:from-indigo-500 hover:to-purple-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Signing in…
                </>
              ) : (
                'Sign in'
              )}
            </button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-xs text-slate-500">
              {DEV_MODE
                ? 'Set REACT_APP_DEV_MODE=false to enforce Cognito auth.'
                : 'Contact your administrator for access credentials.'}
            </p>
          </div>
        </div>

        <div className="mt-8 text-center">
          <p className="text-xs text-indigo-200">
            {DEV_MODE ? 'Local development build' : 'Secure authentication powered by AWS Cognito'}
          </p>
        </div>
      </div>
    </div>
  );
}

