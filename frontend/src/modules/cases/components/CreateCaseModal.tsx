import { RichTextEditor } from '../../../components/RichTextEditor';
import type { SyntheticEvent } from 'react';
import { useState } from 'react';
import { X } from 'lucide-react';
import { label, t } from '../../../config/i18n';
import { ApiError, request, requestForm } from '../../../core/api/client';
import { parseTags } from '../../../core/utils/format';
import type { Case, Session } from '../../../types/domain';
import { CASE_SEVERITIES, CUSTOM_PROBLEM_TYPE } from '../constants';
import { problemTypeOptions } from '../utils';
import { ResponsibleOwnerSelect } from './ResponsibleOwnerSelect';

type CreateCaseModalProps = {
  knownProblemTypes: string[];
  initialSession?: Session;
  onClose: () => void;
  onCreated: (caseId: string) => Promise<void>;
};

export function CreateCaseModal({ knownProblemTypes, initialSession, onClose, onCreated }: CreateCaseModalProps) {
  const [title, setTitle] = useState('');
  const [sceneDescription, setSceneDescription] = useState('');
  const [expectedResult, setExpectedResult] = useState('');
  const [actualResult, setActualResult] = useState('');
  const [reproducible, setReproducible] = useState('');
  const [feedbackReporter, setFeedbackReporter] = useState('');
  const [responsibleOwner, setResponsibleOwner] = useState('');
  const [severity, setSeverity] = useState('medium');
  const [problemType, setProblemType] = useState('other');
  const [customProblemType, setCustomProblemType] = useState('');
  const [tags, setTags] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const usesExistingSession = Boolean(initialSession);

  async function submit(e: SyntheticEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    const normalizedTitle = title.trim();
    if (!normalizedTitle && !initialSession) {
      setError(t.caseTitleRequired);
      return;
    }
    const caseTitle = normalizedTitle || (initialSession ? sessionTitleFallback(initialSession, file) : '');
    setSubmitting(true);
    try {
      let session = initialSession;
      if (!session && file) {
        const formData = new FormData();
        formData.set('file', file);
        session = await requestForm<Session>('/sessions/upload/auto', formData);
      }
      const normalizedProblemType = problemType === CUSTOM_PROBLEM_TYPE ? customProblemType.trim() : problemType;
      const created = await request<Case>('/cases', {
        method: 'POST',
        body: JSON.stringify({
          title: caseTitle,
          session_id: session?.id ?? null,
          source: session ? 'offline_log_import' : 'manual',
          severity,
          problem_type: normalizedProblemType || 'other',
          scene_description: sceneDescription || null,
          expected_result: expectedResult || null,
          actual_result: actualResult || null,
          reproducible: reproducible === '' ? null : reproducible === 'true',
          feedback_reporter: feedbackReporter || null,
          responsible_owner: responsibleOwner || null,
          tags: parseTags(tags),
        }),
      });
      await onCreated(created.id);
    } catch (exc) {
      setError(exc instanceof ApiError && exc.status === 409 ? t.sessionAlreadyExists : t.createCaseFailed);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modalOverlay" role="presentation" onMouseDown={onClose}>
      <form className="caseCreateModal" onSubmit={submit} onMouseDown={e => e.stopPropagation()}>
        <header className="modalHeader">
          <div className="modalHeaderMain">
            <div className="modalTitleRow"><span>{t.createCaseTitle}</span><strong>{usesExistingSession ? t.useSelectedSession : t.sessionOptional}</strong></div>
            {initialSession && <p>{t.selectedSessionEvidence}: {sessionTitleFallback(initialSession)}</p>}
            {!initialSession && <p>{t.caseSessionOptionalHelp}</p>}
          </div>
          <button className="iconButton" type="button" aria-label={t.closeModal} onClick={onClose}><X size={18} /></button>
        </header>
        <div className="caseCreateBody">
          <label>{t.title}<input value={title} onChange={e => setTitle(e.target.value)} placeholder={t.caseTitlePlaceholder} required={!usesExistingSession} /></label>
          <label>{t.sceneDescription}<RichTextEditor value={sceneDescription} onChange={setSceneDescription} placeholder={t.sceneDescription} /></label>
          <label>{t.expectedResult}<textarea value={expectedResult} onChange={e => setExpectedResult(e.target.value)} /></label>
          <label>{t.actualResult}<textarea value={actualResult} onChange={e => setActualResult(e.target.value)} /></label>
          <label>{t.severity}<select value={severity} onChange={e => setSeverity(e.target.value)}>{CASE_SEVERITIES.map(item => <option key={item} value={item}>{label(item)}</option>)}</select></label>
          <label>{t.problemType}<select value={problemType} onChange={e => setProblemType(e.target.value)}>{problemTypeOptions(knownProblemTypes).map(item => <option key={item} value={item}>{label(item)}</option>)}<option value={CUSTOM_PROBLEM_TYPE}>{t.customProblemType}</option></select></label>
          {problemType === CUSTOM_PROBLEM_TYPE && <label>{t.customProblemType}<input value={customProblemType} onChange={e => setCustomProblemType(e.target.value)} placeholder={t.customProblemTypePlaceholder} maxLength={128} /></label>}
          <label>{t.reproducible}<select value={reproducible} onChange={e => setReproducible(e.target.value)}><option value="">{t.reproducibleUnknown}</option><option value="true">{t.reproducibleYes}</option><option value="false">{t.reproducibleNo}</option></select></label>
          <label>{t.feedbackReporter}<input value={feedbackReporter} onChange={e => setFeedbackReporter(e.target.value)} /></label>
          <label>{t.responsibleOwner}<ResponsibleOwnerSelect value={responsibleOwner} onChange={setResponsibleOwner} /></label>
          <label>{t.tags}<input value={tags} onChange={e => setTags(e.target.value)} placeholder={t.tagsPlaceholder} /></label>
          {!usesExistingSession && <label>{t.sessionRecordFile}（{t.optional}）<input type="file" accept=".json,.jsonl,application/json,application/jsonl,text/plain" onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>}
          {error && <div className="error">{error}</div>}
        </div>
        <footer className="modalFooter">
          <button type="button" onClick={onClose}>{t.close}</button>
          <button disabled={submitting}>{submitting ? t.loading : (file ? t.uploadAndCreate : t.createCase)}</button>
        </footer>
      </form>
    </div>
  );
}

function sessionTitleFallback(session: Session, file?: File | null) {
  if (session.summary) return session.summary;
  const location = [session.repository, session.branch].filter(Boolean).join(' / ');
  if (location) return `${session.agent_type} - ${location}`;
  return file?.name ?? `${session.agent_type} ${session.created_at}`;
}
