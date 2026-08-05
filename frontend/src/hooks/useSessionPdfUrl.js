import { useEffect, useState } from 'react';
import api from '../services/cmeApi';
import { fetchSessionPdfUrl } from '../lib/sessionArtifacts';

export function useSessionPdfUrl(sessionId, artifactUrls) {
  const direct = artifactUrls?.standard_report_pdf || null;
  const [pdfUrl, setPdfUrl] = useState(direct);
  const [loading, setLoading] = useState(Boolean(sessionId) && !direct);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    if (direct) {
      setPdfUrl(direct);
      setLoading(false);
      setError('');
      return undefined;
    }

    if (!sessionId) {
      setPdfUrl(null);
      setLoading(false);
      return undefined;
    }

    setLoading(true);
    setError('');
    (async () => {
      try {
        const url = await fetchSessionPdfUrl(sessionId, artifactUrls, api);
        if (cancelled) return;
        setPdfUrl(url);
        if (!url) setError('PDF report not available yet.');
      } catch {
        if (!cancelled) setError('Could not load PDF report.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sessionId, direct]);

  return { pdfUrl, loading, error };
}
