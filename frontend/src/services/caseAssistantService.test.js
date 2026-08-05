jest.mock('./cmeApi', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

import {
  detectContextType,
  extractRouteParams,
  answerQuestion,
  getSuggestedQuestions,
  CONTEXT_TYPES,
} from './caseAssistantService';

describe('caseAssistantService', () => {
  test('detectContextType maps routes correctly', () => {
    expect(detectContextType('/')).toBe(CONTEXT_TYPES.DASHBOARD);
    expect(detectContextType('/cases/new')).toBe(CONTEXT_TYPES.NEW_CASE);
    expect(detectContextType('/cases/sample')).toBe(CONTEXT_TYPES.SAMPLE);
    expect(detectContextType('/cases/mock_abc123')).toBe(CONTEXT_TYPES.PROCESSING);
    expect(detectContextType('/sessions/sess-1')).toBe(CONTEXT_TYPES.SESSION);
    expect(detectContextType('/login')).toBe(CONTEXT_TYPES.GENERAL);
  });

  test('extractRouteParams parses ids', () => {
    expect(extractRouteParams('/cases/mock_abc')).toEqual({ caseId: 'mock_abc', sessionId: null });
    expect(extractRouteParams('/sessions/s1')).toEqual({ caseId: null, sessionId: 's1' });
    expect(extractRouteParams('/')).toEqual({ caseId: null, sessionId: null });
  });

  test('getSuggestedQuestions returns context-specific prompts', () => {
    const sample = getSuggestedQuestions(CONTEXT_TYPES.SAMPLE);
    expect(sample.some((q) => q.toLowerCase().includes('orthopedic'))).toBe(true);
    const dash = getSuggestedQuestions(CONTEXT_TYPES.DASHBOARD);
    expect(dash.some((q) => q.toLowerCase().includes('create'))).toBe(true);
  });

  test('answerQuestion handles dashboard create-case intent', async () => {
    const { answer, intent } = await answerQuestion('How do I create a new case?', {
      contextType: CONTEXT_TYPES.DASHBOARD,
    });
    expect(intent).toBe('dashboard');
    expect(answer.toLowerCase()).toContain('new case');
  });

  test('answerQuestion handles sample examiner intent', async () => {
    const { answer } = await answerQuestion('Who was the examiner?', {
      contextType: CONTEXT_TYPES.SAMPLE,
      manifest: { examiner_name: 'Dr. Test MD', plaintiff_name: 'Jane Doe', exam_date: '2020-01-01' },
    });
    expect(answer).toContain('Dr. Test MD');
    expect(answer).toContain('Jane Doe');
  });

  test('answerQuestion handles sample technique issues', async () => {
    const { answer } = await answerQuestion('What technique issues were found?', {
      contextType: CONTEXT_TYPES.SAMPLE,
      comprehensive: {
        technique_issues: [{ issue: 'no_goniometer', severity: 'high', timestamp_sec: 10 }],
        equipment_missing: ['goniometer'],
      },
    });
    expect(answer.toLowerCase()).toContain('goniometer');
  });

  test('answerQuestion handles processing status', async () => {
    const { answer } = await answerQuestion("What's the processing status?", {
      contextType: CONTEXT_TYPES.PROCESSING,
      caseData: {
        case_id: 'c1',
        plaintiff_name: 'Alice',
        examiner_name: 'Dr. Bob',
        status: 'processing',
        processing_started_at: new Date().toISOString(),
      },
    });
    expect(answer).toContain('Alice');
    expect(answer.toLowerCase()).toContain('processing');
  });

  test('answerQuestion falls back gracefully', async () => {
    const { answer, intent } = await answerQuestion('xyzzy nonsense question', {
      contextType: CONTEXT_TYPES.DASHBOARD,
    });
    expect(intent).toBe('fallback');
    expect(answer.toLowerCase()).toContain('not sure');
  });

  test('answerQuestion handles sample cost intent', async () => {
    const { answer } = await answerQuestion('What was the analysis cost?', {
      contextType: CONTEXT_TYPES.SAMPLE,
      manifest: { cost_usd: 47.4491, frame_count: 2617 },
    });
    expect(answer).toContain('$47.45');
    expect(answer.toLowerCase()).toContain('no re-analysis');
  });

  test('answerQuestion handles sample orthopedic tests intent', async () => {
    const { answer } = await answerQuestion('What orthopedic tests were observed?', {
      contextType: CONTEXT_TYPES.SAMPLE,
      testLedger: {
        total_events: 354,
        events: [
          {
            test_name: 'Gait assessment',
            category: 'orthopedic_neurologic',
            observed_on_video: true,
            start_sec: 100,
            technique_verdict: 'modified',
            three_way_status: 'observed_not_reported',
          },
        ],
      },
    });
    expect(answer.toLowerCase()).toContain('report vs video');
    expect(answer.toLowerCase()).toContain('timestamp');
  });

  test('answerQuestion handles session Report vs video tab intent', async () => {
    const { answer } = await answerQuestion('Show orthopedic tests', {
      contextType: CONTEXT_TYPES.SESSION,
      session: { status: 'completed', patient_name: 'Wendy Scammon' },
    });
    expect(answer).toContain('Report vs video');
  });
});
