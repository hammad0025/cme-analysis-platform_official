import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactPlayer from 'react-player';
import api from '../services/cmeApi';

const CMESessionDetail = () => {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [showConsentModal, setShowConsentModal] = useState(false);
  
  useEffect(() => {
    fetchSessionDetails();
  }, [sessionId]);
  
  const fetchSessionDetails = async () => {
    try {
      setLoading(true);
      const response = await api.get(`/cme/sessions/${sessionId}`);
      setSession(response.data);
    } catch (error) {
      console.error('Error fetching session:', error);
    } finally {
      setLoading(false);
    }
  };
  
  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    
    try {
      // Get presigned URL
      const response = await api.post('/cme/upload', {
        session_id: sessionId,
        filename: file.name,
        content_type: file.type,
        file_size: file.size
      });
      
      const { upload_url } = response.data;
      
      // Upload file to S3
      await fetch(upload_url, {
        method: 'PUT',
        body: file,
        headers: {
          'Content-Type': file.type
        },
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setUploadProgress(percentCompleted);
        }
      });
      
      // Start processing
      await api.post('/cme/process', { session_id: sessionId });
      
      fetchSessionDetails();
    } catch (error) {
      console.error('Upload error:', error);
      alert('Failed to upload recording');
    }
  };
  
  const generateReport = async () => {
    try {
      const response = await api.get(`/cme/sessions/${sessionId}/report`);
      if (response.data.download_url) {
        window.open(response.data.download_url, '_blank');
      }
    } catch (error) {
      console.error('Error generating report:', error);
      alert('Failed to generate report');
    }
  };
  
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-16 w-16 border-b-4 border-indigo-600"></div>
          <p className="mt-4 text-gray-600 text-lg">Loading session...</p>
        </div>
      </div>
    );
  }
  
  if (!session) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="text-6xl mb-4">❌</div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Session Not Found</h2>
          <button
            onClick={() => navigate('/cme')}
            className="mt-4 text-indigo-600 hover:text-indigo-800 font-semibold"
          >
            ← Back to Sessions
          </button>
        </div>
      </div>
    );
  }
  
  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <button
            onClick={() => navigate('/cme')}
            className="text-indigo-600 hover:text-indigo-800 font-medium mb-4"
          >
            ← Back to Sessions
          </button>
          
          <div className="bg-white rounded-lg shadow-md p-6">
            <div className="flex justify-between items-start">
              <div>
                <h1 className="text-3xl font-bold text-gray-900 mb-2">
                  {session.patient_name || 'CME Session'}
                </h1>
                <div className="flex items-center gap-3">
                  <StatusBadge status={session.status} />
                  <span className="text-sm bg-gray-100 text-gray-600 px-3 py-1 rounded">
                    {session.state}
                  </span>
                  <span className="text-sm bg-purple-100 text-purple-800 px-3 py-1 rounded">
                    {session.mode}
                  </span>
                </div>
              </div>
              
              <div className="flex gap-3">
                {session.status === 'completed' && (
                  <button
                    onClick={generateReport}
                    className="bg-gradient-to-r from-green-600 to-green-700 text-white px-6 py-3 rounded-lg font-semibold hover:from-green-700 hover:to-green-800 transition shadow-lg"
                  >
                    📄 Generate Report
                  </button>
                )}
                {session.status === 'created' && (
                  <label className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white px-6 py-3 rounded-lg font-semibold hover:from-indigo-700 hover:to-purple-700 transition shadow-lg cursor-pointer">
                    📤 Upload Recording
                    <input
                      type="file"
                      accept="video/*,audio/*"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                  </label>
                )}
              </div>
            </div>
          </div>
        </div>
        
        {/* Tabs */}
        <div className="bg-white rounded-lg shadow-md mb-6">
          <div className="border-b border-gray-200">
            <nav className="-mb-px flex space-x-8 px-6">
              {['overview', 'timeline', 'demeanor', 'recordings'].map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`py-4 px-1 border-b-2 font-medium text-sm transition ${
                    activeTab === tab
                      ? 'border-indigo-500 text-indigo-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </button>
              ))}
            </nav>
          </div>
          
          <div className="p-6">
            {activeTab === 'overview' && <OverviewTab session={session} />}
            {activeTab === 'timeline' && <TimelineTab session={session} />}
            {activeTab === 'demeanor' && <DemeanorTab session={session} />}
            {activeTab === 'recordings' && <RecordingsTab session={session} />}
          </div>
        </div>
        
        {/* Consent Modal */}
        {showConsentModal && (
          <ConsentModal
            session={session}
            onClose={() => setShowConsentModal(false)}
            onSubmit={() => {
              setShowConsentModal(false);
              fetchSessionDetails();
            }}
          />
        )}
      </div>
    </div>
  );
};

const StatusBadge = ({ status }) => {
  const colors = {
    'created': 'bg-blue-100 text-blue-800',
    'recording_uploaded': 'bg-yellow-100 text-yellow-800',
    'processing': 'bg-purple-100 text-purple-800 animate-pulse',
    'completed': 'bg-green-100 text-green-800',
    'error': 'bg-red-100 text-red-800'
  };
  
  return (
    <span className={`px-3 py-1 rounded-full text-xs font-semibold ${colors[status] || 'bg-gray-100 text-gray-800'}`}>
      {status.replace('_', ' ').toUpperCase()}
    </span>
  );
};

const OverviewTab = ({ session }) => (
  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
    <div>
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Session Information</h3>
      <dl className="space-y-3">
        <div>
          <dt className="text-sm font-medium text-gray-500">Patient ID</dt>
          <dd className="mt-1 text-sm text-gray-900">{session.patient_id}</dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-gray-500">Examiner</dt>
          <dd className="mt-1 text-sm text-gray-900">{session.doctor_name}</dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-gray-500">Exam Date</dt>
          <dd className="mt-1 text-sm text-gray-900">{session.exam_date}</dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-gray-500">Attorney</dt>
          <dd className="mt-1 text-sm text-gray-900">{session.attorney_name || 'N/A'}</dd>
        </div>
      </dl>
    </div>
    
    <div>
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Recording Details</h3>
      <dl className="space-y-3">
        <div>
          <dt className="text-sm font-medium text-gray-500">Recording Mode</dt>
          <dd className="mt-1 text-sm text-gray-900">{session.mode}</dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-gray-500">State</dt>
          <dd className="mt-1 text-sm text-gray-900">{session.state}</dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-gray-500">Legal Basis</dt>
          <dd className="mt-1 text-sm text-gray-900">{session.recording_allowed?.rule || 'N/A'}</dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-gray-500">Video Permitted</dt>
          <dd className="mt-1 text-sm text-gray-900">
            {session.recording_allowed?.video ? '✅ Yes' : '❌ No'}
          </dd>
        </div>
      </dl>
    </div>
  </div>
);

const TimelineTab = ({ session }) => (
  <div>
    <p className="text-gray-600 mb-4">Test declarations and observed actions will appear here after processing.</p>
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
      <p className="text-sm text-blue-800">
        ⏳ Processing status: {session.processing_stage || 'Not started'}
      </p>
    </div>
  </div>
);

const DemeanorTab = ({ session }) => (
  <div>
    <p className="text-gray-600 mb-4">Demeanor analysis results will appear here after processing.</p>
    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
      <p className="text-sm text-yellow-800">
        🎭 Demeanor analysis will detect negative tone, interruptions, and dismissive behavior.
      </p>
    </div>
  </div>
);

const RecordingsTab = ({ session }) => (
  <div>
    {session.video_uri ? (
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Recording</h3>
        <p className="text-sm text-gray-600">Video URI: {session.video_uri}</p>
      </div>
    ) : (
      <div className="text-center py-12">
        <div className="text-6xl mb-4">🎥</div>
        <p className="text-gray-600">No recording uploaded yet</p>
      </div>
    )}
  </div>
);

const ConsentModal = ({ session, onClose, onSubmit }) => {
  const [signature, setSignature] = useState('');
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await api.post('/cme/consent', {
        session_id: session.session_id,
        participant_role: 'attorney',
        signature: signature,
        consent_text: 'Digital consent provided'
      });
      onSubmit();
    } catch (error) {
      console.error('Consent error:', error);
      alert('Failed to submit consent');
    }
  };
  
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg max-w-2xl w-full p-6">
        <h2 className="text-2xl font-bold mb-4">Digital Consent</h2>
        <form onSubmit={handleSubmit}>
          <textarea
            className="w-full border border-gray-300 rounded-lg p-4 mb-4"
            rows="10"
            readOnly
            value={`Florida CME Recording Consent\n\nBy signing, you consent to recording this examination...`}
          />
          <input
            type="text"
            placeholder="Type your full name to sign"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg mb-4"
            value={signature}
            onChange={(e) => setSignature(e.target.value)}
            required
          />
          <div className="flex justify-end gap-3">
            <button type="button" onClick={onClose} className="px-6 py-2 border rounded-lg">
              Cancel
            </button>
            <button type="submit" className="px-6 py-2 bg-indigo-600 text-white rounded-lg">
              Submit Consent
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CMESessionDetail;


