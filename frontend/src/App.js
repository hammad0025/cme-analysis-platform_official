import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { AssistantProvider } from './hooks/useAssistantContext';
import CaseAssistant from './components/assistant/CaseAssistant';
import ProtectedRoute from './components/ProtectedRoute';
import AppShell from './components/AppShell';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import SessionDetail from './pages/SessionDetail';
import NewCase from './pages/NewCase';
import SampleCase from './pages/SampleCase';
import CaseProcessing from './pages/CaseProcessing';

function AuthenticatedLayout() {
  return (
    <ProtectedRoute>
      <AppShell />
    </ProtectedRoute>
  );
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <AssistantProvider>
          <CaseAssistant />
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<AuthenticatedLayout />}>
              <Route index element={<Dashboard />} />
              <Route path="cases/new" element={<NewCase />} />
              <Route path="cases/sample" element={<SampleCase />} />
              <Route path="cases/:caseId" element={<CaseProcessing />} />
              <Route path="sessions/:sessionId" element={<SessionDetail />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AssistantProvider>
      </Router>
    </AuthProvider>
  );
}

export default App;
