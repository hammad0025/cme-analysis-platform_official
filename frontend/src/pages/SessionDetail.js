import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../services/api';

export default function SessionDetail() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [uploading, setUploading] = useState(false);

  const loadSession = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get(`/cme/sessions/${sessionId}`);
      setSession(response.data);
    } catch (error) {
      console.error('Failed to load session:', error);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    try {
      setUploading(true);
      const response = await api.post('/cme/upload', {
        session_id: sessionId,
        filename: file.name,
        content_type: file.type,
        file_size: file.size,
      });

      await fetch(response.data.upload_url, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': file.type },
      });

      await api.post('/cme/process', { session_id: sessionId });
      loadSession();
    } catch (error) {
      console.error('Upload failed:', error);
      alert('Failed to upload recording');
    } finally {
      setUploading(false);
    }
  };

  const handleGenerateReport = async () => {
    try {
      const response = await api.get(`/cme/sessions/${sessionId}/report`);
      if (response.data.download_url) {
        window.open(response.data.download_url, '_blank');
      }
    } catch (error) {
      console.error('Report generation failed:', error);
      alert('Failed to generate report');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="mt-4 text-sm text-slate-600">Loading session...</p>
        </div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 bg-gradient-to-br from-red-100 to-red-200 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-lg font-bold text-slate-900 mb-2">Session Not Found</h2>
          <p className="text-sm text-slate-600 mb-6">The session you're looking for doesn't exist.</p>
          <button
            onClick={() => navigate('/')}
            className="px-6 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-semibold rounded-xl hover:shadow-lg transition-shadow"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const tabs = [
    { id: 'overview', label: 'Overview', icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' },
    { id: 'analysis', label: 'Analysis', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
    { id: 'timeline', label: 'Timeline', icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
    { id: 'recording', label: 'Recording', icon: 'M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z' },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md border-b border-slate-200/60 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-8 py-6">
          <button
            onClick={() => navigate('/')}
            className="flex items-center text-sm font-medium text-slate-600 hover:text-slate-900 mb-4 transition-colors"
          >
            <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Dashboard
          </button>

          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-bold text-slate-900 mb-2">{session.patient_name || 'CME Session'}</h1>
              <div className="flex items-center gap-3">
                <StatusBadge status={session.status} />
                <span className="inline-flex items-center gap-2 text-sm text-slate-600">
                  <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  {session.state}
                </span>
                <span className="inline-flex items-center gap-2 text-sm text-slate-600">
                  <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  {session.exam_date || 'Date not set'}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {session.status === 'completed' && (
                <button
                  onClick={handleGenerateReport}
                  className="px-6 py-2.5 bg-gradient-to-r from-emerald-600 to-green-600 text-white text-sm font-semibold rounded-xl shadow-lg shadow-emerald-500/25 hover:shadow-xl hover:shadow-emerald-500/40 hover:scale-105 active:scale-95 transition-all duration-200"
                >
                  Generate Report
                </button>
              )}
              {session.status === 'created' && (
                <label className="px-6 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-semibold rounded-xl shadow-lg shadow-blue-500/25 hover:shadow-xl hover:shadow-blue-500/40 hover:scale-105 active:scale-95 transition-all duration-200 cursor-pointer">
                  {uploading ? 'Uploading...' : 'Upload Recording'}
                  <input
                    type="file"
                    accept="video/*,audio/*"
                    onChange={handleFileUpload}
                    className="hidden"
                    disabled={uploading}
                  />
                </label>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="bg-white/80 backdrop-blur-md border-b border-slate-200/60">
        <div className="max-w-7xl mx-auto px-8">
          <nav className="flex space-x-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-6 py-4 text-sm font-medium border-b-2 transition-all ${
                  activeTab === tab.id
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300'
                }`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={tab.icon} />
                </svg>
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </div>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-8 py-8">
        {activeTab === 'overview' && <OverviewTab session={session} />}
        {activeTab === 'analysis' && <AnalysisTab session={session} />}
        {activeTab === 'timeline' && <TimelineTab session={session} />}
        {activeTab === 'recording' && <RecordingTab session={session} />}
      </main>
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
    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl ${config.classes}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current"></span>
      {config.label}
    </span>
  );
}

function OverviewTab({ session }) {
  return (
    <div className="grid grid-cols-2 gap-6">
      <InfoCard
        title="Session Information"
        icon="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
        items={[
          { label: 'Patient ID', value: session.patient_id },
          { label: 'Patient Name', value: session.patient_name },
          { label: 'Examiner', value: session.doctor_name },
          { label: 'Exam Date', value: session.exam_date },
          { label: 'Attorney', value: session.attorney_name },
          { label: 'Case ID', value: session.case_id },
        ]}
      />

      <InfoCard
        title="Recording Details"
        icon="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
        items={[
          { label: 'State', value: session.state },
          { label: 'Recording Mode', value: session.mode },
          { label: 'Legal Basis', value: session.recording_allowed?.rule },
          { label: 'Video Permitted', value: session.recording_allowed?.video ? 'Yes' : 'No' },
          { label: 'Audio Permitted', value: session.recording_allowed?.audio ? 'Yes' : 'No' },
        ]}
      />
    </div>
  );
}

function AnalysisTab({ session }) {
  if (session.status !== 'completed') {
    return (
      <EmptyState
        icon="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
        title="Analysis Pending"
        description="Analysis results will appear here once the recording has been processed."
        gradient="from-blue-500 to-indigo-600"
      />
    );
  }

  return (
    <div className="space-y-6">
      <InfoCard
        title="Declared Tests"
        icon="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        items={[{ label: '', value: 'Test declarations detected from audio transcript will appear here.' }]}
      />
      <InfoCard
        title="Observed Actions"
        icon="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
        items={[{ label: '', value: 'Visual analysis of performed tests will appear here.' }]}
      />
      <InfoCard
        title="Discrepancies"
        icon="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        items={[{ label: '', value: 'Mismatches between declared and observed tests will appear here.' }]}
      />
    </div>
  );
}

function TimelineTab({ session }) {
  return (
    <EmptyState
      icon="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
      title="Timeline View"
      description="A chronological timeline of the examination will be generated after processing."
      gradient="from-purple-500 to-indigo-600"
    />
  );
}

function RecordingTab({ session }) {
  if (!session.video_uri) {
    return (
      <EmptyState
        icon="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
        title="No Recording"
        description="Upload a recording to begin analysis."
        gradient="from-slate-500 to-slate-600"
      />
    );
  }

  return (
    <InfoCard
      title="Recording Information"
      icon="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
      items={[
        { label: 'Video URI', value: session.video_uri, mono: true },
        { label: 'Upload Date', value: session.updated_at ? new Date(session.updated_at * 1000).toLocaleString() : 'N/A' },
      ]}
    />
  );
}

function InfoCard({ title, icon, items }) {
  return (
    <div className="bg-white rounded-2xl shadow-lg border border-slate-200 p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl">
          <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={icon} />
          </svg>
        </div>
        <h3 className="text-lg font-bold text-slate-900">{title}</h3>
      </div>
      <dl className="space-y-4">
        {items.map((item, index) => (
          <div key={index}>
            {item.label && <dt className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">{item.label}</dt>}
            <dd className={`text-sm text-slate-900 ${item.mono ? 'font-mono text-xs bg-slate-50 p-2 rounded-lg' : ''}`}>
              {item.value || '—'}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function EmptyState({ icon, title, description, gradient }) {
  return (
    <div className="bg-white rounded-2xl shadow-lg border border-slate-200 p-16 text-center">
      <div className={`w-20 h-20 bg-gradient-to-br ${gradient} rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-lg`}>
        <svg className="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={icon} />
        </svg>
      </div>
      <h3 className="text-lg font-bold text-slate-900 mb-2">{title}</h3>
      <p className="text-sm text-slate-600 max-w-md mx-auto">{description}</p>
    </div>
  );
}
