import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';

export default function Dashboard() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [stateFilter, setStateFilter] = useState('');
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    try {
      setLoading(true);
      const response = await api.get('/cme/sessions');
      setSessions(response.data.sessions || []);
    } catch (error) {
      console.error('Failed to load sessions:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredSessions = sessions.filter(session => {
    const matchesSearch = !searchQuery || 
      session.patient_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      session.doctor_name?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesState = !stateFilter || session.state === stateFilter;
    return matchesSearch && matchesState;
  });

  const stats = {
    total: sessions.length,
    completed: sessions.filter(s => s.status === 'completed').length,
    processing: sessions.filter(s => s.status === 'processing').length,
    pending: sessions.filter(s => ['created', 'recording_uploaded'].includes(s.status)).length,
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md border-b border-slate-200/60 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-slate-900 via-blue-900 to-indigo-900 bg-clip-text text-transparent">
                CME Analysis Platform
              </h1>
              <p className="text-sm text-slate-600 mt-1">Medical Examination Analysis & Reporting</p>
            </div>
            <button
              onClick={() => setShowModal(true)}
              className="group relative px-6 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-semibold rounded-xl shadow-lg shadow-blue-500/25 hover:shadow-xl hover:shadow-blue-500/40 hover:scale-105 active:scale-95 transition-all duration-200"
            >
              <span className="flex items-center gap-2">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                New Session
              </span>
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-8 py-8">
        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <StatCard 
            label="Total Sessions" 
            value={stats.total}
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            }
            gradient="from-slate-500 to-slate-600"
          />
          <StatCard 
            label="Completed" 
            value={stats.completed}
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            }
            gradient="from-emerald-500 to-green-600"
          />
          <StatCard 
            label="Processing" 
            value={stats.processing}
            icon={
              <svg className="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            }
            gradient="from-blue-500 to-indigo-600"
          />
          <StatCard 
            label="Pending" 
            value={stats.pending}
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            }
            gradient="from-amber-500 to-orange-600"
          />
        </div>

        {/* Search and Filters */}
        <div className="flex items-center gap-4 mb-6">
          <div className="flex-1 relative">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search sessions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full h-11 pl-10 pr-4 text-sm bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent shadow-sm"
            />
          </div>
          <select
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            className="h-11 px-4 text-sm bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent shadow-sm"
          >
            <option value="">All States</option>
            <option value="FL">Florida</option>
            <option value="CA">California</option>
            <option value="PA">Pennsylvania</option>
            <option value="TX">Texas</option>
          </select>
          {(searchQuery || stateFilter) && (
            <button
              onClick={() => {
                setSearchQuery('');
                setStateFilter('');
              }}
              className="h-11 px-4 text-sm font-medium text-slate-600 hover:text-slate-900 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors shadow-sm"
            >
              Clear
            </button>
          )}
        </div>

        {/* Sessions Grid */}
        <div className="bg-white rounded-2xl shadow-lg border border-slate-200 overflow-hidden">
          {loading ? (
            <div className="p-16 text-center">
              <div className="w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="mt-4 text-sm text-slate-500">Loading sessions...</p>
            </div>
          ) : filteredSessions.length === 0 ? (
            <div className="p-16 text-center">
              <div className="w-16 h-16 bg-gradient-to-br from-slate-100 to-slate-200 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-slate-900 mb-2">No sessions found</h3>
              <p className="text-sm text-slate-500 mb-6">Get started by creating your first CME session</p>
              <button
                onClick={() => setShowModal(true)}
                className="px-6 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-semibold rounded-xl hover:shadow-lg transition-shadow"
              >
                Create Session
              </button>
            </div>
          ) : (
            <div className="divide-y divide-slate-200">
              {filteredSessions.map((session) => (
                <div
                  key={session.session_id}
                  className="px-6 py-5 hover:bg-gradient-to-r hover:from-blue-50/50 hover:to-indigo-50/50 cursor-pointer transition-all group"
                  onClick={() => navigate(`/sessions/${session.session_id}`)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="text-base font-semibold text-slate-900 group-hover:text-blue-600 transition-colors">
                          {session.patient_name || 'Unnamed Patient'}
                        </h3>
                        <StatusBadge status={session.status} />
                        <span className="text-xs font-medium px-2.5 py-1 bg-slate-100 text-slate-600 rounded-lg">
                          {session.state}
                        </span>
                      </div>
                      <div className="flex items-center gap-6 text-sm text-slate-600">
                        <span className="flex items-center gap-2">
                          <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                          </svg>
                          {session.doctor_name || 'N/A'}
                        </span>
                        <span className="flex items-center gap-2">
                          <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                          </svg>
                          {session.exam_date || 'Not set'}
                        </span>
                        <span className="flex items-center gap-2">
                          <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                          </svg>
                          {session.mode || 'N/A'}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/sessions/${session.session_id}`);
                      }}
                      className="ml-4 px-4 py-2 text-sm font-medium text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded-lg transition-colors"
                    >
                      View Details →
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {showModal && (
        <CreateSessionModal
          onClose={() => setShowModal(false)}
          onSuccess={() => {
            setShowModal(false);
            loadSessions();
          }}
        />
      )}
    </div>
  );
}

function StatCard({ label, value, icon, gradient }) {
  return (
    <div className="relative group">
      <div className="absolute -inset-0.5 bg-gradient-to-r opacity-75 rounded-2xl blur transition group-hover:opacity-100" style={{ background: `linear-gradient(to right, var(--tw-gradient-stops))` }}></div>
      <div className="relative bg-white rounded-2xl p-6 shadow-lg border border-slate-200">
        <div className="flex items-center justify-between mb-3">
          <div className={`p-3 bg-gradient-to-br ${gradient} rounded-xl shadow-lg`}>
            <div className="text-white">
              {icon}
            </div>
          </div>
        </div>
        <div className="text-3xl font-bold text-slate-900 mb-1">{value}</div>
        <div className="text-sm font-medium text-slate-600">{label}</div>
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  const configs = {
    created: { label: 'Created', classes: 'bg-blue-100 text-blue-700 ring-1 ring-blue-200' },
    recording_uploaded: { label: 'Uploaded', classes: 'bg-amber-100 text-amber-700 ring-1 ring-amber-200' },
    processing: { label: 'Processing', classes: 'bg-purple-100 text-purple-700 ring-1 ring-purple-200 animate-pulse' },
    completed: { label: 'Completed', classes: 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200' },
    error: { label: 'Error', classes: 'bg-red-100 text-red-700 ring-1 ring-red-200' },
  };

  const config = configs[status] || configs.created;

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-lg ${config.classes}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current"></span>
      {config.label}
    </span>
  );
}

function CreateSessionModal({ onClose, onSuccess }) {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    patient_id: '',
    patient_name: '',
    doctor_name: '',
    state: 'FL',
    exam_date: new Date().toISOString().split('T')[0],
    case_id: '',
    attorney_name: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const response = await api.post('/cme/sessions', formData);
      if (response.data.session_id) {
        navigate(`/sessions/${response.data.session_id}`);
        onSuccess();
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to create session');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <form onSubmit={handleSubmit}>
          <div className="px-6 py-5 border-b border-slate-200">
            <h2 className="text-xl font-bold text-slate-900">Create New Session</h2>
            <p className="text-sm text-slate-600 mt-1">Enter the examination details below</p>
          </div>

          <div className="px-6 py-6">
            <div className="grid grid-cols-2 gap-4">
              {[
                { id: 'patient_id', label: 'Patient ID', required: true },
                { id: 'patient_name', label: 'Patient Name', required: true },
                { id: 'doctor_name', label: 'Examiner Name', required: true },
                { id: 'exam_date', label: 'Exam Date', type: 'date', required: true },
              ].map((field) => (
                <div key={field.id}>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">
                    {field.label} {field.required && <span className="text-red-500">*</span>}
                  </label>
                  <input
                    type={field.type || 'text'}
                    required={field.required}
                    value={formData[field.id]}
                    onChange={(e) => setFormData({ ...formData, [field.id]: e.target.value })}
                    className="w-full h-10 px-3 text-sm bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>
              ))}

              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-2">
                  State <span className="text-red-500">*</span>
                </label>
                <select
                  required
                  value={formData.state}
                  onChange={(e) => setFormData({ ...formData, state: e.target.value })}
                  className="w-full h-10 px-3 text-sm bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="FL">Florida</option>
                  <option value="CA">California</option>
                  <option value="PA">Pennsylvania</option>
                  <option value="TX">Texas</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-2">Case ID</label>
                <input
                  type="text"
                  value={formData.case_id}
                  onChange={(e) => setFormData({ ...formData, case_id: e.target.value })}
                  className="w-full h-10 px-3 text-sm bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>

              <div className="col-span-2">
                <label className="block text-sm font-semibold text-slate-700 mb-2">Attorney Name</label>
                <input
                  type="text"
                  value={formData.attorney_name}
                  onChange={(e) => setFormData({ ...formData, attorney_name: e.target.value })}
                  className="w-full h-10 px-3 text-sm bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
            </div>

            {error && (
              <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-800">
                {error}
              </div>
            )}
          </div>

          <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex justify-end gap-3 rounded-b-2xl">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="h-10 px-5 text-sm font-medium text-slate-700 hover:bg-white border border-slate-300 rounded-lg transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="h-10 px-5 bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-semibold rounded-lg hover:shadow-lg transition-shadow disabled:opacity-50"
            >
              {submitting ? 'Creating...' : 'Create Session'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
