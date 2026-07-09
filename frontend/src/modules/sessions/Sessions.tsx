import type { SyntheticEvent } from 'react';
import { useEffect, useState } from 'react';
import { ClipboardPlus, RotateCcw, Search, Upload, X } from 'lucide-react';
import { t } from '../../config/i18n';
import { ApiError, request, requestForm } from '../../core/api/client';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { relativeTime } from '../../core/utils/format';
import type { Session } from '../../types/domain';
import { CreateCaseModal } from '../cases/components/CreateCaseModal';
import { SessionChatModal } from './components/SessionChatModal';

type PaginatedResponse<T> = { items: T[]; total: number };

export function Sessions({ onCaseCreated }: { onCaseCreated?: (caseId: string) => void }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [caseSession, setCaseSession] = useState<Session | null>(null);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [uploadOpen, setUploadOpen] = useState(false);
  const pageSize = 30;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const load = () => {
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('page_size', String(pageSize));
    if (query.trim() && query.trim().length > 4) params.set('q', query.trim());
    const suffix = params.toString();
    return request<PaginatedResponse<Session>>(`/sessions${suffix ? `?${suffix}` : ''}`).then(data => { setSessions(data.items); setTotal(data.total); });
  };
  useEffect(() => {
    void load();
  }, []);
  useEffect(() => {
    void load();
  }, [query]);
  useEffect(() => {
    void load();
  }, [page]);
  useEffect(() => {
    setPage(1);
  }, [query]);

  async function uploaded(sessionId: string) {
    await load();
    setSelected(sessionId);
    setUploadOpen(false);
  }
  async function caseCreated(caseId: string) {
    setCaseSession(null);
    await load();
    onCaseCreated?.(caseId);
  }
  return (
    <section className="panel">
      <div className="panelHeader">
        <h2>{t.sessions}</h2>
        <button onClick={() => setUploadOpen(true)}><Upload size={16} /> {t.uploadSession}</button>
      </div>
      <div className="caseSearchBox">
        <label>{t.sessionSearch}</label>
        <div className="issueSearch">
          <Search size={18} />
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder={t.sessionSearchPlaceholder} />
          {query && <button className="iconButton" aria-label={t.reset} onClick={() => setQuery('')}><RotateCcw size={16} /></button>}
        </div>
      </div>
      <table className="sessionTable"><thead><tr><th>{t.agent}</th><th>{t.repository}</th><th>{t.branch}</th><th>{t.summary}</th><th>{t.createdAt}</th><th>{'会话 ID'}</th><th>{t.langfuse}</th><th>{t.actions}</th></tr></thead><tbody>{sessions.map(s => <tr key={s.id} onClick={() => setSelected(s.id)} className={selected === s.id ? 'selected' : ''}><td><span className="agentMark">{s.agent_type}</span></td><td>{s.repository ?? '-'}</td><td>{s.branch ?? '-'}</td><td>{s.summary ?? '-'}</td><td><span className="relativeTime">{relativeTime(s.created_at)}</span></td><td><code>{s.id ? s.id.slice(0, 8) + '-' : '-'}</code></td><td>{s.langfuse_url ? <a href={s.langfuse_url} target="_blank" onClick={e => e.stopPropagation()}>{t.open}</a> : '-'}</td><td><button className="secondaryButton" onClick={e => { e.stopPropagation(); setCaseSession(s); }}><ClipboardPlus size={16} /> {t.createCase}</button></td></tr>)}</tbody></table>
      {sessions.length === 0 && <p className="muted sessionEmptyState">{t.noMatchingSessions}</p>}
      {uploadOpen && <UploadSessionModal onClose={() => setUploadOpen(false)} onUploaded={uploaded} />}
      {caseSession && <CreateCaseModal initialSession={caseSession} knownProblemTypes={[]} onClose={() => setCaseSession(null)} onCreated={caseCreated} />}
      {selected && <SessionChatModal sessionId={selected} onClose={() => setSelected(null)} />}
      <div className="paginationBar">
        <span>{t.pageSummary.replace('{page}', String(page)).replace('{pages}', String(pageCount)).replace('{total}', String(total))}</span>
        <div>
          <button className="iconButton" aria-label={t.previousPage} disabled={page <= 1} onClick={() => setPage(current => Math.max(1, current - 1))}><ChevronLeft size={16} /></button>
          <button className="iconButton" aria-label={t.nextPage} disabled={page >= pageCount} onClick={() => setPage(current => Math.min(pageCount, current + 1))}><ChevronRight size={16} /></button>
        </div>
      </div>
    </section>
  );
}

function UploadSessionModal({ onClose, onUploaded }: { onClose: () => void; onUploaded: (sessionId: string) => Promise<void> }) {
  const [file, setFile] = useState<File | null>(null);
  const [projectName, setProjectName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  async function submit(e: SyntheticEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    if (!file) {
      setError(t.sessionRecordRequired);
      return;
    }
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.set('file', file);
      const suffix = projectName.trim() ? `?project_name=${encodeURIComponent(projectName.trim())}` : '';
      const session = await requestForm<Session>(`/sessions/upload/auto${suffix}`, formData);
      await onUploaded(session.id);
    } catch (exc) {
      setError(exc instanceof ApiError && exc.status === 409 ? t.sessionAlreadyExists : t.uploadSessionFailed);
    } finally {
      setSubmitting(false);
    }
  }
  return (
    <div className="modalOverlay" role="presentation" onMouseDown={onClose}>
      <form className="caseCreateModal" onSubmit={submit} onMouseDown={e => e.stopPropagation()}>
        <header className="modalHeader">
          <div className="modalHeaderMain">
            <div className="modalTitleRow"><span>{t.uploadSessionTitle}</span><strong>{t.autoDetectSession}</strong></div>
            <p>{t.uploadSessionHelp}</p>
          </div>
          <button className="iconButton" type="button" aria-label={t.closeModal} onClick={onClose}><X size={18} /></button>
        </header>
        <div className="caseCreateBody">
          <label>{t.projectNameOptional}<input value={projectName} onChange={e => setProjectName(e.target.value)} placeholder={t.projectNamePlaceholder} /></label>
          <label>{t.sessionRecordFile}<input type="file" accept=".json,.jsonl,application/json,application/jsonl,text/plain" required onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
          {error && <div className="error">{error}</div>}
        </div>
        <footer className="modalFooter">
          <button type="button" onClick={onClose}>{t.close}</button>
          <button disabled={submitting}>{submitting ? t.loading : t.uploadSessionOnly}</button>
        </footer>
      </form>
    </div>
  );
}
