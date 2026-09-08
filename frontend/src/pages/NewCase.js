import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import Button from '../components/Button';
import StepIndicator from '../components/case/StepIndicator';
import DropZone, { VideoIcon, PdfIcon } from '../components/case/DropZone';
import FileCard, { FileProgressRow, ProgressBar } from '../components/case/FileCard';
import PdfImportZone from '../components/case/PdfImportZone';
import { toWizardMetadata } from '../lib/pdfCaseParser';
import { importCaseFromPdf } from '../services/pdfImportService';
import {
  STEPS,
  VIDEO_ACCEPT,
  PDF_ACCEPT,
  MAX_VIDEO_BYTES,
  REPORT_TYPES,
  todayISO,
  formatBytes,
  isVideoFile,
  isPdfFile,
  makeFileId,
  reportLabel,
} from '../lib/caseConstants';
import {
  createCase,
  deleteMockCase,
  isMockMode,
  requestUploadUrl,
  startProcessing,
  updateMockCase,
  uploadFileWithProgress,
} from '../services/casesService';

const REPORT_TYPE_COLORS = {
  indigo: 'text-indigo-600',
  purple: 'text-purple-600',
  violet: 'text-violet-600',
  slate: 'text-slate-600',
};

const stepVariants = {
  initial: { opacity: 0, x: 16 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -16 },
};

export default function NewCase() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);

  const [metadata, setMetadata] = useState({
    plaintiff_name: '',
    examiner_name: '',
    exam_date: '',
    date_of_injury: '',
    date_of_birth: '',
  });
  const [metadataErrors, setMetadataErrors] = useState({});
  const [highlightedFields, setHighlightedFields] = useState([]);
  const [pdfImportLoading, setPdfImportLoading] = useState(false);
  const [pdfImportError, setPdfImportError] = useState('');
  const [pdfImportPreview, setPdfImportPreview] = useState(null);
  const [importSuccess, setImportSuccess] = useState('');

  const [videos, setVideos] = useState([]);
  const [videoError, setVideoError] = useState('');
  const videoInputRef = useRef(null);

  const [reports, setReports] = useState([]);
  const [reportError, setReportError] = useState('');
  const reportInputRef = useRef(null);

  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState({});
  const [submitError, setSubmitError] = useState('');
  const [submitPhase, setSubmitPhase] = useState('');
  const cancelRefs = useRef([]);
  const inFlightCaseId = useRef(null);

  const mock = isMockMode();

  const validateMetadata = useCallback(() => {
    const errs = {};
    const today = todayISO();
    if (!metadata.plaintiff_name.trim()) errs.plaintiff_name = 'Plaintiff name is required.';
    if (!metadata.examiner_name.trim()) errs.examiner_name = 'Examiner name is required.';
    if (!metadata.exam_date) errs.exam_date = 'Exam date is required.';
    else if (metadata.exam_date > today) errs.exam_date = 'Exam date cannot be in the future.';
    if (!metadata.date_of_injury) errs.date_of_injury = 'Date of injury is required.';
    else if (metadata.date_of_injury > today) errs.date_of_injury = 'Date of injury cannot be in the future.';
    if (!metadata.date_of_birth) errs.date_of_birth = 'Date of birth is required.';
    else if (metadata.date_of_birth > today) errs.date_of_birth = 'Date of birth cannot be in the future.';
    if (metadata.date_of_birth && metadata.exam_date && metadata.date_of_birth > metadata.exam_date) {
      errs.date_of_birth = 'Date of birth must precede the exam date.';
    }
    if (metadata.date_of_injury && metadata.exam_date && metadata.date_of_injury > metadata.exam_date) {
      errs.date_of_injury = 'Injury date must precede the exam date.';
    }
    return errs;
  }, [metadata]);

  const metadataValid = useMemo(() => Object.keys(validateMetadata()).length === 0, [validateMetadata]);

  const handleMetadataField = (field) => (e) => {
    setMetadata((prev) => ({ ...prev, [field]: e.target.value }));
    setMetadataErrors((prev) => ({ ...prev, [field]: undefined }));
    setHighlightedFields((prev) => prev.filter((f) => f !== field));
  };

  const attachImportedReport = useCallback((file, reportType = 'cme_report') => {
    setReports((prev) => {
      const duplicate = prev.some(
        (r) => r.file.name === file.name && r.file.size === file.size && r.file.lastModified === file.lastModified
      );
      if (duplicate) return prev;
      return [
        ...prev,
        {
          id: makeFileId(file),
          file,
          type: reportType,
          fromImport: true,
        },
      ];
    });
  }, []);

  const handlePdfImport = async (file) => {
    if (!isPdfFile(file)) {
      setPdfImportError('Please upload a PDF report.');
      return;
    }

    setPdfImportError('');
    setImportSuccess('');
    setPdfImportLoading(true);
    setPdfImportPreview(null);

    try {
      const result = await importCaseFromPdf(file);
      const wizardMeta = toWizardMetadata(result.fields);
      const filled = Object.entries(wizardMeta)
        .filter(([, v]) => v)
        .map(([k]) => k);

      setMetadata((prev) => {
        const next = { ...prev };
        for (const [key, val] of Object.entries(wizardMeta)) {
          if (val) next[key] = val;
        }
        return next;
      });
      setMetadataErrors({});
      setHighlightedFields(filled);
      setPdfImportPreview({
        fields: result.fields,
        fields_found: result.fields_found,
        confidence: result.confidence,
        sourceFilename: result.sourceFilename,
        pagesRead: result.pagesRead,
      });

      attachImportedReport(file, result.report_type_hint || 'cme_report');

      if (result.confidence === 'none') {
        setPdfImportError(
          'We attached your PDF but could not confidently read case details. Please fill in the fields below.'
        );
      } else {
        setImportSuccess(
          filled.length
            ? `Auto-filled ${filled.length} field${filled.length !== 1 ? 's' : ''} from your report. Review and edit before continuing.`
            : 'PDF attached to reports. Enter case details manually below.'
        );
      }

      window.setTimeout(() => setHighlightedFields([]), 2800);
      window.setTimeout(() => setImportSuccess(''), 6000);
    } catch (err) {
      setPdfImportError(err?.message || 'Could not read this PDF. Try another file or enter details manually.');
    } finally {
      setPdfImportLoading(false);
    }
  };

  const renumberVideos = (list) =>
    list.map((v, i) => ({ ...v, slot: i + 1, label: v.label || `Video ${i + 1}` }));

  const goToStep = (target) => {
    if (target < step) {
      setStep(target);
      return;
    }
    if (step === 1) {
      const errs = validateMetadata();
      if (Object.keys(errs).length) {
        setMetadataErrors(errs);
        return;
      }
    }
    if (step === 2 && videos.length === 0) {
      setVideoError('Please attach an examination recording before continuing.');
      return;
    }
    if (step === 3) setReportError('');
    setStep(target);
  };

  const onVideosChosen = (files) => {
    setVideoError('');
    const list = Array.from(files || []);
    if (!list.length) return;

    const rejects = [];
    const accepts = [];
    list.forEach((f) => {
      if (!isVideoFile(f)) rejects.push(f);
      else if (f.size > MAX_VIDEO_BYTES) rejects.push(f);
      else accepts.push(f);
    });

    if (rejects.length) {
      setVideoError(
        rejects.length === 1 && rejects[0].size > MAX_VIDEO_BYTES
          ? `${rejects[0].name} exceeds the 5 GB limit (${formatBytes(rejects[0].size)}).`
          : `Skipped invalid files: ${rejects.map((r) => r.name).join(', ')}. Use MP4, MOV, M4V, WEBM, or supported audio under 5 GB.`
      );
    }

    if (accepts.length > 1) {
      setVideoError((prev) => (
        prev
          ? `${prev} Only one recording is supported per live case right now; using ${accepts[0].name}.`
          : `Only one recording is supported per live case right now; using ${accepts[0].name}.`
      ));
    }

    if (accepts.length) {
      const file = accepts[0];
      setVideos(renumberVideos([{
        id: makeFileId(file),
        file,
        slot: 1,
        label: '',
      }]));
    }
  };

  const removeVideo = (id) => setVideos((prev) => renumberVideos(prev.filter((v) => v.id !== id)));

  const setVideoLabel = (id, label) =>
    setVideos((prev) => prev.map((v) => (v.id === id ? { ...v, label } : v)));

  const onReportsChosen = (files) => {
    setReportError('');
    const list = Array.from(files || []);
    if (!list.length) return;
    const rejects = list.filter((f) => !isPdfFile(f));
    const accepts = list.filter((f) => isPdfFile(f));
    if (rejects.length) {
      setReportError(`Only PDF reports are accepted. Skipped: ${rejects.map((r) => r.name).join(', ')}.`);
    }
    setReports((prev) => [
      ...prev,
      ...accepts.map((file) => ({
        id: makeFileId(file),
        file,
        type: prev.length === 0 ? 'cme_report' : 'other',
      })),
    ]);
  };

  const removeReport = (id) => setReports((prev) => prev.filter((r) => r.id !== id));
  const setReportType = (id, type) =>
    setReports((prev) => prev.map((r) => (r.id === id ? { ...r, type } : r)));

  const canSubmit = metadataValid && videos.length > 0 && !submitting;

  const overallPercent = useMemo(() => {
    const values = Object.values(progress);
    if (!values.length) return 0;
    return values.reduce((acc, v) => acc + (Number.isFinite(v) ? v : 0), 0) / values.length;
  }, [progress]);

  const cancelAll = useCallback(() => {
    cancelRefs.current.forEach((c) => {
      try { c && c(); } catch (_) { /* ignore */ }
    });
    cancelRefs.current = [];
    if (inFlightCaseId.current && mock) {
      try { deleteMockCase(inFlightCaseId.current); } catch (_) { /* ignore */ }
    }
    inFlightCaseId.current = null;
  }, [mock]);

  useEffect(() => () => cancelAll(), [cancelAll]);

  const onSubmit = async () => {
    if (!canSubmit) return;
    setSubmitError('');
    setSubmitPhase('Preparing case record...');
    setSubmitting(true);
    setProgress({});
    cancelRefs.current = [];

    let createdCase = null;

    try {
      createdCase = await createCase(metadata);
      inFlightCaseId.current = createdCase.case_id;

      const fileTasks = [
        ...videos.map((v, i) => ({
          key: `video_${i}`,
          file: v.file,
          kind: 'video',
          tag: 'recording',
          recordingSlot: v.slot,
          displayLabel: v.label || `Video ${v.slot}`,
        })),
        ...reports.map((r, i) => ({
          key: `report_${i}`,
          file: r.file,
          kind: 'report',
          tag: r.type,
          displayLabel: reportLabel(r.type),
        })),
      ];

      const uploadedRefs = [];
      for (const task of fileTasks) {
        setSubmitPhase(`Uploading ${task.displayLabel || task.file.name}...`);
        const ref = await uploadWithRetry(createdCase.case_id, task, setProgress, cancelRefs);
        uploadedRefs.push({ ...task, ...ref });
      }

      const videoRefs = uploadedRefs
        .filter((r) => r.kind === 'video')
        .map((r) => ({
          filename: r.file.name,
          size: r.file.size,
          file_key: r.file_key,
          recording_slot: r.recording_slot || r.recordingSlot,
          label: r.displayLabel,
        }));

      const reportRefs = uploadedRefs
        .filter((r) => r.kind === 'report')
        .map((r) => ({
          filename: r.file.name,
          size: r.file.size,
          file_key: r.file_key,
          tag: r.tag,
        }));

      if (mock) {
        updateMockCase(createdCase.case_id, {
          video: videoRefs[0] || null,
          videos: videoRefs,
          reports: reportRefs,
          status: 'processing',
        });
      }

      setSubmitPhase('Starting analysis pipeline...');
      await startProcessing({
        caseId: createdCase.case_id,
        videos: videoRefs,
        reports: reportRefs,
      });

      setSubmitPhase('Opening case dashboard...');
      inFlightCaseId.current = null;
      navigate(`/cases/${createdCase.case_id}`);
    } catch (err) {
      const isCancel = /cancelled/i.test(err && err.message);
      if (isCancel) {
        if (mock && createdCase) {
          try { deleteMockCase(createdCase.case_id); } catch (_) { /* ignore */ }
        }
        setSubmitError('Upload cancelled. The case was discarded.');
      } else {
        setSubmitError(err?.message || 'Upload failed. Please try again.');
      }
      setSubmitPhase('');
      inFlightCaseId.current = null;
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
        <header className="mb-10">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-3xl font-bold text-slate-900 tracking-tight">New case</h1>
              <p className="text-sm text-slate-600 mt-2 max-w-xl leading-relaxed">
                Upload examination videos and supporting reports. Our pipeline extracts conduct, claims, and contradictions — with timestamped evidence for trial.
              </p>
            </div>
            {mock && (
              <span className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-full px-3 py-1.5 shadow-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
                Mock mode
              </span>
            )}
          </div>
        </header>

        <StepIndicator steps={STEPS} currentStep={step} onJump={goToStep} />

        <div className="mt-8 rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-200/50 overflow-hidden">
          <div className="h-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-indigo-500 bg-[length:200%_100%] animate-gradient-x" />
          <div className="p-6 sm:p-10">
            <AnimatePresence mode="wait">
              <motion.div
                key={step}
                variants={stepVariants}
                initial="initial"
                animate="animate"
                exit="exit"
                transition={{ duration: 0.2 }}
              >
                {step === 1 && (
                  <StepDetails
                    metadata={metadata}
                    errors={metadataErrors}
                    onChange={handleMetadataField}
                    highlightedFields={highlightedFields}
                    pdfImportLoading={pdfImportLoading}
                    pdfImportError={pdfImportError}
                    pdfImportPreview={pdfImportPreview}
                    importSuccess={importSuccess}
                    onPdfImport={handlePdfImport}
                    onDismissPdfPreview={() => setPdfImportPreview(null)}
                    disabled={submitting}
                  />
                )}
                {step === 2 && (
                  <StepVideos
                    videos={videos}
                    error={videoError}
                    onAdd={onVideosChosen}
                    onRemove={removeVideo}
                    onSetLabel={setVideoLabel}
                    inputRef={videoInputRef}
                    disabled={submitting}
                  />
                )}
                {step === 3 && (
                  <StepReports
                    reports={reports}
                    error={reportError}
                    onAdd={onReportsChosen}
                    onRemove={removeReport}
                    onSetType={setReportType}
                    inputRef={reportInputRef}
                    disabled={submitting}
                  />
                )}
                {step === 4 && (
                  <StepReview
                    metadata={metadata}
                    videos={videos}
                    reports={reports}
                    submitting={submitting}
                    progress={progress}
                    overallPercent={overallPercent}
                    submitError={submitError}
                    submitPhase={submitPhase}
                    mock={mock}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>

        <div className="mt-8 flex items-center justify-between gap-3">
          <Button
            variant="ghost"
            size="md"
            onClick={() => {
              if (submitting) {
                cancelAll();
                setSubmitting(false);
                setSubmitPhase('');
                setSubmitError('Upload cancelled. The case was discarded.');
                return;
              }
              if (step === 1) navigate('/');
              else goToStep(step - 1);
            }}
          >
            {submitting ? 'Cancel upload' : step === 1 ? 'Cancel' : 'Back'}
          </Button>
          <div className="flex items-center gap-3">
            {step < 4 && (
              <Button variant="primary" size="md" onClick={() => goToStep(step + 1)}>
                Continue
              </Button>
            )}
            {step === 4 && (
              <Button variant="primary" size="lg" disabled={!canSubmit} onClick={onSubmit}>
                {submitting ? (
                  <>
                    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Working…
                  </>
                ) : (
                  'Submit case'
                )}
              </Button>
            )}
          </div>
        </div>
    </div>
  );
}

async function uploadWithRetry(caseId, task, setProgress, cancelRefs) {
  const attempt = async () => {
    const presigned = await requestUploadUrl({
      caseId,
      file: task.file,
      kind: task.kind,
      tag: task.tag,
      recordingSlot: task.recordingSlot,
    });
    const { promise, cancel } = uploadFileWithProgress({
      url: presigned.upload_url,
      file: task.file,
      mock: presigned.mock,
      contentType: presigned.content_type,
      onProgress: ({ percent }) => setProgress((prev) => ({ ...prev, [task.key]: percent })),
    });
    cancelRefs.current.push(cancel);
    try {
      await promise;
    } finally {
      cancelRefs.current = cancelRefs.current.filter((fn) => fn !== cancel);
    }
    return { file_key: presigned.file_key, recording_slot: presigned.recording_slot };
  };

  try {
    return await attempt();
  } catch (err) {
    if (/cancelled/i.test(err?.message)) throw err;
    setProgress((prev) => ({ ...prev, [task.key]: 0 }));
    try {
      return await attempt();
    } catch (retryErr) {
      if (/cancelled/i.test(retryErr?.message)) throw retryErr;
      const reason = retryErr?.message || err?.message || 'Upload failed after retry.';
      throw new Error(`${task.file.name}: ${reason}`);
    }
  }
}

function StepDetails({
  metadata,
  errors,
  onChange,
  highlightedFields = [],
  pdfImportLoading,
  pdfImportError,
  pdfImportPreview,
  importSuccess,
  onPdfImport,
  onDismissPdfPreview,
  disabled,
}) {
  const highlight = (field) => highlightedFields.includes(field);

  return (
    <div>
      <SectionHeader
        title="Case details"
        subtitle="Import a CME report PDF to auto-fill, or enter details manually. All fields are required."
      />

      <PdfImportZone
        loading={pdfImportLoading}
        error={pdfImportError}
        preview={pdfImportPreview}
        onImport={onPdfImport}
        onDismissPreview={onDismissPdfPreview}
        disabled={disabled}
      />

      {importSuccess && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 flex items-center gap-2 text-sm font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3"
        >
          <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
          {importSuccess}
        </motion.div>
      )}

      <div className="relative">
        <div className="absolute inset-x-0 top-0 flex items-center gap-3 pointer-events-none -mt-1 mb-4">
          <div className="flex-1 h-px bg-slate-200" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Or enter manually</span>
          <div className="flex-1 h-px bg-slate-200" />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 pt-6">
        <Field span={2} label="Plaintiff name" required error={errors.plaintiff_name} highlighted={highlight('plaintiff_name')}>
          <input
            type="text"
            value={metadata.plaintiff_name}
            onChange={onChange('plaintiff_name')}
            placeholder="e.g. Wendy Scammon"
            autoComplete="off"
            className={inputCls(errors.plaintiff_name, highlight('plaintiff_name'))}
          />
        </Field>
        <Field label="Examiner name" required error={errors.examiner_name} highlighted={highlight('examiner_name')}>
          <input
            type="text"
            value={metadata.examiner_name}
            onChange={onChange('examiner_name')}
            placeholder="e.g. Dr. Brett Osborn, DO"
            autoComplete="off"
            className={inputCls(errors.examiner_name, highlight('examiner_name'))}
          />
        </Field>
        <Field label="Exam date" required error={errors.exam_date} highlighted={highlight('exam_date')}>
          <input
            type="date"
            value={metadata.exam_date}
            max={todayISO()}
            onChange={onChange('exam_date')}
            className={inputCls(errors.exam_date, highlight('exam_date'))}
          />
        </Field>
        <Field label="Date of injury" required error={errors.date_of_injury} highlighted={highlight('date_of_injury')}>
          <input
            type="date"
            value={metadata.date_of_injury}
            max={todayISO()}
            onChange={onChange('date_of_injury')}
            className={inputCls(errors.date_of_injury, highlight('date_of_injury'))}
          />
        </Field>
        <Field label="Date of birth" required error={errors.date_of_birth} highlighted={highlight('date_of_birth')}>
          <input
            type="date"
            value={metadata.date_of_birth}
            max={todayISO()}
            onChange={onChange('date_of_birth')}
            className={inputCls(errors.date_of_birth, highlight('date_of_birth'))}
          />
        </Field>
      </div>
    </div>
  );
}

function StepVideos({ videos, error, onAdd, onRemove, onSetLabel, inputRef, disabled }) {
  return (
    <div>
      <SectionHeader
        title="Examination videos"
        subtitle="Upload one CME recording for this production workflow. If the exam is split across files, combine the segments into one file first."
      />
      <DropZone
        accept={VIDEO_ACCEPT}
        multiple={false}
        onFiles={onAdd}
        inputRef={inputRef}
        icon={VideoIcon}
        title="Drag and drop examination videos"
        subtitle="MP4, MOV, M4V, WEBM, or audio (MP3, M4A, WAV, FLAC) · up to 5 GB each"
        accent="indigo"
        disabled={disabled}
      />

      {videos.length > 0 && (
        <div className="mt-6 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {videos.length} video{videos.length !== 1 ? 's' : ''} attached
            </span>
            <Button variant="ghost" size="sm" onClick={() => inputRef.current?.click()} disabled={disabled}>
              Replace
            </Button>
          </div>
          {videos.map((v, i) => (
            <FileCard
              key={v.id}
              kind="video"
              name={v.file.name}
              size={v.file.size}
              badge={`Video ${v.slot}`}
              index={i}
              onRemove={() => onRemove(v.id)}
              onReplace={() => inputRef.current?.click()}
            >
              <input
                type="text"
                value={v.label}
                onChange={(e) => onSetLabel(v.id, e.target.value)}
                placeholder={`Label (optional) — e.g. "Morning session"`}
                className="w-full h-9 px-3 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-slate-50"
                disabled={disabled}
              />
            </FileCard>
          ))}
        </div>
      )}

      {error && <Alert variant="error">{error}</Alert>}
    </div>
  );
}

function StepReports({ reports, error, onAdd, onRemove, onSetType, inputRef, disabled }) {
  return (
    <div>
      <SectionHeader
        title="Reports & documents"
        subtitle="Optional PDFs can improve claim matching, but video-only cases can still be submitted. Tag each document for proper routing."
      />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {REPORT_TYPES.map((t) => (
          <div key={t.value} className="rounded-xl border border-slate-100 bg-slate-50/80 p-3 text-center">
            <div className={`text-[10px] font-bold uppercase tracking-wide ${REPORT_TYPE_COLORS[t.color]}`}>{t.short}</div>
            <div className="text-[10px] text-slate-500 mt-1 leading-snug">{t.label}</div>
          </div>
        ))}
      </div>

      <DropZone
        accept={PDF_ACCEPT}
        multiple
        onFiles={onAdd}
        inputRef={inputRef}
        icon={PdfIcon}
        title="Drag and drop optional PDF reports"
        subtitle="Defense expert report, IME, medical history, and supporting documents"
        accent="purple"
        disabled={disabled}
      />

      {reports.length > 0 && (
        <div className="mt-6 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {reports.length} document{reports.length !== 1 ? 's' : ''} attached
            </span>
            <Button variant="ghost" size="sm" onClick={() => inputRef.current?.click()} disabled={disabled}>
              Add more
            </Button>
          </div>
          {reports.map((r, i) => (
            <FileCard
              key={r.id}
              kind="report"
              name={r.file.name}
              size={r.file.size}
              badgeType={r.type}
              index={i}
              onRemove={() => onRemove(r.id)}
            >
              <select
                value={r.type}
                onChange={(e) => onSetType(r.id, e.target.value)}
                disabled={disabled}
                className="w-full h-9 text-xs font-medium border border-slate-200 rounded-lg px-2 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {REPORT_TYPES.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </FileCard>
          ))}
        </div>
      )}

      {error && <Alert variant="error">{error}</Alert>}
    </div>
  );
}

function StepReview({ metadata, videos, reports, submitting, progress, overallPercent, submitError, submitPhase, mock }) {
  return (
    <div>
      <SectionHeader
        title="Review & submit"
        subtitle={
          mock
            ? 'Mock mode simulates uploads locally. Processing state is stored in your browser only.'
            : 'Files upload directly to secure storage via presigned URLs. Processing begins when the last file completes.'
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <ReviewPanel title="Case details">
          <ReviewRow label="Plaintiff" value={metadata.plaintiff_name} />
          <ReviewRow label="Examiner" value={metadata.examiner_name} />
          <ReviewRow label="Exam date" value={metadata.exam_date} />
          <ReviewRow label="Date of injury" value={metadata.date_of_injury} />
          <ReviewRow label="Date of birth" value={metadata.date_of_birth} />
        </ReviewPanel>

        <ReviewPanel title="Materials summary">
          <ReviewRow
            label="Videos"
            value={
              videos.length === 0 ? (
                <span className="text-slate-400">None</span>
              ) : (
                <ul className="space-y-1.5">
                  {videos.map((v) => (
                    <li key={v.id} className="text-sm flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 flex-shrink-0" />
                      <span className="text-slate-800 truncate">{v.label || `Video ${v.slot}`}</span>
                      <span className="text-xs text-slate-400">{formatBytes(v.file.size)}</span>
                    </li>
                  ))}
                </ul>
              )
            }
          />
          <ReviewRow
            label="Reports"
            value={
              reports.length === 0 ? (
                <span className="text-slate-400">None attached; video-only processing will run</span>
              ) : (
                <ul className="space-y-1.5">
                  {reports.map((r) => (
                    <li key={r.id} className="text-sm flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-purple-500 flex-shrink-0" />
                      <span className="text-slate-800 truncate">{r.file.name}</span>
                      <span className="text-xs text-slate-400">{reportLabel(r.type)}</span>
                    </li>
                  ))}
                </ul>
              )
            }
          />
        </ReviewPanel>
      </div>

      {submitting && (
        <div className="rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-purple-50 p-6 mb-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-indigo-900">{submitPhase || 'Uploading materials...'}</span>
            <span className="text-sm font-mono font-semibold text-indigo-700">{Math.round(overallPercent)}%</span>
          </div>
          <ProgressBar percent={overallPercent} />
          <ul className="mt-5 space-y-3">
            {videos.map((v, i) => (
              <FileProgressRow
                key={v.id}
                label={`${v.label || `Video ${v.slot}`} · ${v.file.name}`}
                percent={progress[`video_${i}`]}
              />
            ))}
            {reports.map((r, i) => (
              <FileProgressRow
                key={r.id}
                label={`${reportLabel(r.type)} · ${r.file.name}`}
                percent={progress[`report_${i}`]}
              />
            ))}
          </ul>
        </div>
      )}

      {submitError && <Alert variant="error">{submitError}</Alert>}
    </div>
  );
}

function SectionHeader({ title, subtitle }) {
  return (
    <div className="mb-8">
      <h2 className="text-xl font-bold text-slate-900">{title}</h2>
      <p className="text-sm text-slate-600 mt-1.5 leading-relaxed">{subtitle}</p>
    </div>
  );
}

function Field({ label, required, error, span, highlighted, children }) {
  return (
    <motion.div
      className={span === 2 ? 'sm:col-span-2' : ''}
      animate={highlighted ? { scale: [1, 1.01, 1] } : { scale: 1 }}
      transition={{ duration: 0.35 }}
    >
      <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">
        {label}
        {required && <span className="text-rose-500 ml-1">*</span>}
        {highlighted && (
          <span className="ml-2 text-[10px] font-bold normal-case tracking-normal text-indigo-600">Auto-filled</span>
        )}
      </label>
      {children}
      {error && <p className="mt-1.5 text-xs font-medium text-rose-600">{error}</p>}
    </motion.div>
  );
}

function inputCls(hasError, highlighted) {
  return `w-full h-11 px-4 text-sm bg-white border rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all duration-500 ${
    hasError
      ? 'border-rose-300 ring-1 ring-rose-100'
      : highlighted
        ? 'border-indigo-400 ring-2 ring-indigo-200 bg-indigo-50/40 shadow-sm shadow-indigo-100'
        : 'border-slate-200 hover:border-slate-300'
  }`;
}

function ReviewPanel({ title, children }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-5">
      <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-4">{title}</h3>
      <dl className="space-y-3">{children}</dl>
    </div>
  );
}

function ReviewRow({ label, value }) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="text-sm text-slate-800 mt-0.5">{value || <span className="text-slate-400">—</span>}</dd>
    </div>
  );
}

function Alert({ variant, children }) {
  const cls =
    variant === 'error'
      ? 'bg-rose-50 border-rose-200 text-rose-700'
      : 'bg-amber-50 border-amber-200 text-amber-800';
  return (
    <div className={`mt-4 p-4 text-sm border rounded-xl ${cls}`}>{children}</div>
  );
}
