import type { SyntheticEvent } from 'react';
import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AlertTriangle,
  BarChart3,
  Bot,
  CheckCircle2,
  ClipboardList,
  Database,
  LogOut,
  PlayCircle,
  Upload,
  X,
} from 'lucide-react';
import { label, t } from './i18n';
import './styles.css';

const API = import.meta.env.VITE_API_BASE_URL ?? '';

type User = { id: string; email: string; display_name: string; role: string };
type Summary = { total_sessions: number; total_cases: number; open_cases: number; closed_cases: number; closure_rate: number; high_risk_cases: number; experience_count: number };
type BreakdownItem = { key: string; count: number };
type Breakdown = { by_status: BreakdownItem[]; by_severity: BreakdownItem[]; by_problem_type: BreakdownItem[]; by_agent_type: BreakdownItem[] };
type Session = { id: string; agent_type: string; repository?: string; branch?: string; summary?: string; langfuse_url?: string; created_at: string };
type Case = {
  id: string;
  title: string;
  status: string;
  severity: string;
  problem_type: string;
  ai_analysis_status: string;
  owner_id?: string;
  session_id?: string;
  created_at: string;
  closure_reason?: string;
  scene_description?: string;
  expected_result?: string;
  actual_result?: string;
  reproducible?: boolean | null;
  responsible_owner?: string;
  closure_practice?: string;
  feedback_acceptance_conclusion?: string;
};
type CaseDetail = Case & { session?: Session; analyses: Analysis[]; events: EventItem[]; human_conclusion?: string; handling_action?: string };
type Analysis = { id: string; summary?: string; failure_point?: string; ownership_suggestion?: string; severity_suggestion?: string; next_steps: string[]; experience_suggestion?: string; confidence?: number; error_message?: string; created_at: string };
type EventItem = { id: string; event_type: string; comment?: string; from_status?: string; to_status?: string; created_at: string };
type JsonValue = null | boolean | number | string | JsonValue[] | JsonObject;
type JsonObject = { [key in string]: JsonValue };
type ChatBlockKind = 'user' | 'assistant' | 'thinking' | 'tool' | 'function' | 'mcp' | 'skill' | 'shell' | 'file' | 'error' | 'diff' | 'observation' | 'metadata';
type ChatBlock = { kind: ChatBlockKind; title: string; body: string; meta?: string };

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('hq_token');
  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const res = await fetch(`${API}/api/v1${path}`, {
    ...options,
    headers,
  });
  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }
  return (await res.json()) as T;
}

async function requestForm<T>(path: string, formData: FormData): Promise<T> {
  const token = localStorage.getItem('hq_token');
  const headers = new Headers();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const res = await fetch(`${API}/api/v1${path}`, {
    method: 'POST',
    headers,
    body: formData,
  });
  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }
  return (await res.json()) as T;
}

class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly responseText: string,
  ) {
    super(responseText);
  }
}

function loginErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) {
      return t.loginInvalid;
    }
    if (err.status === 422) {
      return t.loginBadRequest;
    }
    return t.loginFailed;
  }
  return t.loginNetworkFailed;
}

function isObject(value: JsonValue | undefined): value is JsonObject {
  return value !== undefined && value !== null && typeof value === 'object' && !Array.isArray(value);
}

function asArray(value: JsonValue | undefined): JsonValue[] {
  return Array.isArray(value) ? value : [];
}

function text(value: JsonValue | undefined): string | null {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value === null || value === undefined) return null;
  return JSON.stringify(value, null, 2);
}

function field(obj: JsonObject | null, key: string): JsonValue | undefined {
  return obj ? obj[key] : undefined;
}

function pretty(value: JsonValue | undefined): string {
  const plain = text(value);
  return plain ?? '-';
}

function safeLabel(value: JsonValue | undefined, fallback: string): string {
  if (typeof value === 'string' && value.trim()) return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback;
}

function pushIfText(blocks: ChatBlock[], kind: ChatBlockKind, title: string, value: JsonValue | undefined, meta?: string) {
  const body = text(value);
  if (body?.trim()) {
    blocks.push({ kind, title, body, meta });
  }
}

function messageKind(role: string): ChatBlockKind {
  const normalized = role.toLowerCase();
  if (normalized.includes('user')) return 'user';
  if (normalized.includes('assistant') || normalized.includes('agent')) return 'assistant';
  if (normalized.includes('thinking') || normalized.includes('reasoning')) return 'thinking';
  if (normalized.includes('shell') || normalized.includes('bash') || normalized.includes('command')) return 'shell';
  if (normalized.includes('file') || normalized.includes('edit') || normalized.includes('write')) return 'file';
  if (normalized.includes('diff')) return 'diff';
  if (normalized.includes('tool')) return 'tool';
  if (normalized.includes('function')) return 'function';
  if (normalized.includes('mcp')) return 'mcp';
  if (normalized.includes('skill')) return 'skill';
  if (normalized.includes('error')) return 'error';
  return 'observation';
}

function classifyCall(name: string, fallback: ChatBlockKind = 'tool'): ChatBlockKind {
  const lowered = name.toLowerCase();
  if (lowered.includes('mcp')) return 'mcp';
  if (lowered.includes('skill')) return 'skill';
  if (lowered.includes('function')) return 'function';
  return fallback;
}

function observationKind(observation: JsonObject): ChatBlockKind {
  const type = safeLabel(field(observation, 'type'), '').toLowerCase();
  const name = safeLabel(field(observation, 'name'), '').toLowerCase();
  const level = safeLabel(field(observation, 'level'), '').toLowerCase();
  if (name.includes('thinking') || name.includes('reasoning') || type.includes('thinking')) return 'thinking';
  if (type.includes('generation')) return 'assistant';
  if (type.includes('mcp') || name.includes('mcp')) return 'mcp';
  if (type.includes('skill') || name.includes('skill')) return 'skill';
  if (type.includes('function') || name.includes('function')) return 'function';
  if (type.includes('tool')) return 'tool';
  if (level.includes('error') || level.includes('warning')) return 'error';
  return 'observation';
}

function extractChatBlocks(raw: JsonValue | null): ChatBlock[] {
  if (!isObject(raw)) return [];
  const blocks: ChatBlock[] = [];
  const metadataValue = field(raw, 'metadata');
  const metadata = isObject(metadataValue) ? metadataValue : null;
  const conversation = [...asArray(field(raw, 'conversation')), ...asArray(field(raw, 'messages')), ...asArray(field(metadata, 'conversation')), ...asArray(field(metadata, 'messages'))];
  const hasConversation = conversation.length > 0;
  for (const message of conversation) {
    if (!isObject(message)) continue;
    const role = safeLabel(field(message, 'role') ?? field(message, 'type'), t.observation);
    const title = safeLabel(field(message, 'title'), label(role));
    pushIfText(blocks, messageKind(role), title, field(message, 'content') ?? field(message, 'message') ?? field(message, 'text') ?? message, safeLabel(field(message, 'timestamp'), role));
  }
  if (blocks.length === 0) {
    pushIfText(blocks, 'user', t.userMessage, field(raw, 'user_input'));
    pushIfText(blocks, 'assistant', t.assistantMessage, field(raw, 'assistant_output'));
    pushIfText(blocks, 'thinking', t.thinkingMessage, field(raw, 'thinking') ?? field(raw, 'reasoning'));
  }

  if (!hasConversation) {
    for (const call of asArray(field(raw, 'tool_calls'))) {
      if (!isObject(call)) continue;
      const name = safeLabel(field(call, 'name'), t.toolCall);
      blocks.push({
        kind: classifyCall(name),
        title: name,
        body: `Input:\n${pretty(field(call, 'input'))}\n\nOutput:\n${pretty(field(call, 'output'))}`,
        meta: t.toolCall,
      });
    }

    for (const command of asArray(field(raw, 'shell_commands'))) {
      if (!isObject(command)) continue;
      blocks.push({
        kind: 'shell',
        title: safeLabel(field(command, 'command'), t.shellCommand),
        body: `Exit: ${pretty(field(command, 'exit_code'))}\n\n${pretty(field(command, 'output'))}`,
        meta: t.shellCommand,
      });
    }

    for (const edit of asArray(field(raw, 'file_edits'))) {
      if (!isObject(edit)) continue;
      blocks.push({
        kind: 'file',
        title: safeLabel(field(edit, 'path'), t.fileEdit),
        body: pretty(field(edit, 'change') ?? edit),
        meta: t.fileEdit,
      });
    }

    for (const error of asArray(field(raw, 'errors'))) {
      blocks.push({ kind: 'error', title: t.errorRecord, body: pretty(error) });
    }

    pushIfText(blocks, 'diff', t.gitDiff, field(raw, 'git_diff'));
  }

  const langfuseShapeValue = field(metadata, 'langfuse_shape');
  const langfuseShape = isObject(langfuseShapeValue) ? langfuseShapeValue : null;
  const traceValue = field(langfuseShape, 'trace');
  const trace = isObject(traceValue) ? traceValue : null;
  if (trace) {
    blocks.push({
      kind: 'metadata',
      title: safeLabel(field(trace, 'name'), t.traceMetadata),
      body: pretty(trace),
      meta: t.traceMetadata,
    });
  }

  for (const observation of asArray(field(langfuseShape, 'observations'))) {
    if (!isObject(observation)) continue;
    const kind = observationKind(observation);
    const title = safeLabel(field(observation, 'name'), safeLabel(field(observation, 'type'), t.observation));
    const statusMessage = text(field(observation, 'statusMessage'));
    const body = [
      statusMessage ? `Status:\n${statusMessage}` : null,
      `Input:\n${pretty(field(observation, 'input'))}`,
      `Output:\n${pretty(field(observation, 'output'))}`,
    ].filter(Boolean).join('\n\n');
    blocks.push({ kind, title, body, meta: safeLabel(field(observation, 'type'), t.observation) });
  }

  if (!hasConversation) {
    for (const key of ['function_calls', 'mcp_calls', 'skill_calls']) {
      for (const item of asArray(field(raw, key) ?? field(metadata, key))) {
        blocks.push({
          kind: key.startsWith('mcp') ? 'mcp' : key.startsWith('skill') ? 'skill' : 'function',
          title: label(key),
          body: pretty(item),
        });
      }
    }
  }

  return blocks;
}

function toneClass(value: string | undefined): string {
  return (value ?? 'unknown').replace(/[^a-z0-9_-]/gi, '-').toLowerCase();
}

function Badge({ value, type = 'neutral' }: { value: string | undefined; type?: 'status' | 'severity' | 'neutral' }) {
  return <span className={`badge ${type} ${toneClass(value)}`}>{label(value)}</span>;
}

function pageSubtitle(tab: string): string {
  if (tab === 'dashboard') return t.dashboardSubtitle;
  if (tab === 'cases') return t.casesSubtitle;
  return t.sessionsSubtitle;
}

function pageTitle(tab: string): string {
  if (tab === 'dashboard') return t.dashboard;
  if (tab === 'cases') return t.cases;
  return t.sessions;
}

function isCollapsedByDefault(kind: ChatBlockKind): boolean {
  return ['tool', 'function', 'mcp', 'skill', 'shell', 'file', 'diff', 'metadata', 'observation'].includes(kind);
}

function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('admin@harnessquest.local');
  const [password, setPassword] = useState('admin123456');
  const [error, setError] = useState('');
  const [oidcEnabled, setOidcEnabled] = useState(false);
  useEffect(() => {
    void fetch(`${API}/api/v1/auth/oidc/status`)
      .then(res => res.json() as Promise<{ enabled: boolean }>)
      .then(data => setOidcEnabled(data.enabled))
      .catch(() => setOidcEnabled(false));
  }, []);
  async function submit(e: SyntheticEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    try {
      const data = await request<{ access_token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
      localStorage.setItem('hq_token', data.access_token);
      onLogin();
    } catch (err) {
      setError(loginErrorMessage(err));
    }
  }
  return (
    <main className="login">
      <form className="loginPanel" onSubmit={submit}>
        <h1>HarnessQuest</h1>
        <p>{t.appSubtitle}</p>
        <label>{t.email}<input value={username} onChange={e => setUsername(e.target.value)} /></label>
        <label>{t.password}<input type="password" value={password} onChange={e => setPassword(e.target.value)} /></label>
        {error && <div className="error">{error}</div>}
        <button>{t.signIn}</button>
        {oidcEnabled && <a className="oauthButton" href={`${API}/api/v1/auth/oidc/login`}>{t.signInWithOAuth}</a>}
      </form>
    </main>
  );
}

function Stat({ label, value, icon }: { label: string; value: string | number; icon: React.ReactNode }) {
  return <div className="stat"><div className="statIcon">{icon}</div><div><span>{label}</span><strong>{value}</strong></div></div>;
}

function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [breakdown, setBreakdown] = useState<Breakdown | null>(null);
  useEffect(() => {
    void request<Summary>('/dashboard/summary').then(setSummary);
    void request<Breakdown>('/dashboard/case-breakdown').then(setBreakdown);
  }, []);
  if (!summary) return <section className="panel">{t.loadingDashboard}</section>;
  const groups = [
    [t.status, breakdown?.by_status ?? []],
    [t.problemType, breakdown?.by_problem_type ?? []],
    [t.severity, breakdown?.by_severity ?? []],
    [t.agentType, breakdown?.by_agent_type ?? []],
  ] as const;
  return (
    <div className="stack">
      <section className="missionStrip">
        <div>
          <span>{t.evidenceReady}</span>
          <strong>{summary.open_cases}</strong>
          <p>{t.openCases}</p>
        </div>
        <div>
          <span>{t.closureRate}</span>
          <strong>{Math.round(summary.closure_rate * 100)}%</strong>
          <p>{t.experience}: {summary.experience_count}</p>
        </div>
        <div>
          <span>{t.highRisk}</span>
          <strong>{summary.high_risk_cases}</strong>
          <p>{t.totalSessions}: {summary.total_sessions}</p>
        </div>
      </section>
      <div className="stats">
        <Stat label={t.totalSessions} value={summary.total_sessions} icon={<Bot size={20} />} />
        <Stat label={t.totalCases} value={summary.total_cases} icon={<ClipboardList size={20} />} />
        <Stat label={t.openCases} value={summary.open_cases} icon={<AlertTriangle size={20} />} />
        <Stat label={t.closureRate} value={`${Math.round(summary.closure_rate * 100)}%`} icon={<CheckCircle2 size={20} />} />
        <Stat label={t.highRisk} value={summary.high_risk_cases} icon={<AlertTriangle size={20} />} />
        <Stat label={t.experience} value={summary.experience_count} icon={<Database size={20} />} />
      </div>
      <div className="grid">
        {groups.map(([title, items]) => <section className="panel" key={title}><h2>{title}</h2>{items.length === 0 ? <p className="muted">{t.noData}</p> : items.map(item => <div className="bar" key={item.key}><span>{label(item.key)}</span><strong>{item.count}</strong></div>)}</section>)}
      </div>
    </div>
  );
}

function Sessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    void request<Session[]>('/sessions').then(setSessions);
  }, []);
  return (
    <section className="panel">
      <h2>{t.sessions}</h2>
      <table><thead><tr><th>{t.agent}</th><th>{t.repository}</th><th>{t.branch}</th><th>{t.summary}</th><th>{t.langfuse}</th></tr></thead><tbody>{sessions.map(s => <tr key={s.id} onClick={() => setSelected(s.id)} className={selected === s.id ? 'selected' : ''}><td><span className="agentMark">{s.agent_type}</span></td><td>{s.repository ?? '-'}</td><td>{s.branch ?? '-'}</td><td>{s.summary ?? '-'}</td><td>{s.langfuse_url ? <a href={s.langfuse_url} target="_blank" onClick={e => e.stopPropagation()}>{t.open}</a> : '-'}</td></tr>)}</tbody></table>
      {selected && <SessionChatModal sessionId={selected} onClose={() => setSelected(null)} />}
    </section>
  );
}

function SessionChatModal({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
  const [session, setSession] = useState<Session | null>(null);
  const [raw, setRaw] = useState<JsonValue | null>(null);
  const [showJson, setShowJson] = useState(false);
  useEffect(() => {
    setSession(null);
    setRaw(null);
    void request<Session>(`/sessions/${sessionId}`).then(setSession);
    void request<JsonValue>(`/sessions/${sessionId}/raw`).then(setRaw);
  }, [sessionId]);
  const blocks = extractChatBlocks(raw);
  return (
    <div className="modalOverlay" role="presentation" onMouseDown={onClose}>
      <section className="sessionModal" role="dialog" aria-modal="true" aria-label={t.fullConversation} onMouseDown={e => e.stopPropagation()}>
        <header className="modalHeader">
          <div className="modalHeaderMain">
            <div className="modalTitleRow">
              <span>{t.fullConversation}</span>
              <strong>{session ? session.agent_type : t.loading}</strong>
              {session?.repository && <em>{session.repository}</em>}
              {session?.branch && <em>{session.branch}</em>}
            </div>
            {session?.summary && <p>{session.summary}</p>}
          </div>
          <button className="iconButton" aria-label={t.closeModal} onClick={onClose}><X size={18} /></button>
        </header>
        <div className="chatTranscript">
          {!raw && <div className="chatBubble system">{t.loading}</div>}
          {blocks.map((block, index) => (
            <article className={`chatMessage ${block.kind}`} key={`${block.kind}-${index}`}>
              <details className="chatBubble" open={!isCollapsedByDefault(block.kind)}>
                <summary className="chatTitle">
                  <span className="chatKind"><strong>{block.title}</strong></span>
                  {block.meta && <span>{block.meta}</span>}
                </summary>
                <pre>{block.body}</pre>
              </details>
            </article>
          ))}
        </div>
        <footer className="modalFooter">
          <button onClick={() => setShowJson(!showJson)}>{showJson ? t.hideJson : t.showJson}</button>
        </footer>
        {showJson && <pre className="jsonViewer modalJson">{raw ? JSON.stringify(raw, null, 2) : t.loading}</pre>}
      </section>
    </div>
  );
}

function Cases() {
  const [cases, setCases] = useState<Case[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const load = () => request<Case[]>('/cases').then(setCases);
  useEffect(() => {
    void load();
  }, []);
  async function created(caseId: string) {
    await load();
    setSelected(caseId);
    setCreateOpen(false);
  }
  return (
    <div className="split">
      <section className="panel">
        <div className="panelHeader"><h2>{t.cases}</h2><button onClick={() => setCreateOpen(true)}><Upload size={16} /> {t.createCase}</button></div>
        <table><thead><tr><th>{t.title}</th><th>{t.status}</th><th>{t.severity}</th><th>{t.type}</th><th>{t.ai}</th></tr></thead><tbody>{cases.map(c => <tr key={c.id} onClick={() => setSelected(c.id)} className={selected === c.id ? 'selected' : ''}><td><strong className="caseTitle">{c.title}</strong></td><td><Badge value={c.status} type="status" /></td><td><Badge value={c.severity} type="severity" /></td><td>{label(c.problem_type)}</td><td><Badge value={c.ai_analysis_status} /></td></tr>)}</tbody></table>
        {createOpen && <CreateCaseModal onClose={() => setCreateOpen(false)} onCreated={created} />}
      </section>
      <CaseDetailPanel caseId={selected} onChanged={load} />
    </div>
  );
}

function CreateCaseModal({ onClose, onCreated }: { onClose: () => void; onCreated: (caseId: string) => Promise<void> }) {
  const [title, setTitle] = useState('');
  const [sceneDescription, setSceneDescription] = useState('');
  const [expectedResult, setExpectedResult] = useState('');
  const [actualResult, setActualResult] = useState('');
  const [reproducible, setReproducible] = useState('');
  const [responsibleOwner, setResponsibleOwner] = useState('');
  const [file, setFile] = useState<File | null>(null);
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
      const session = await requestForm<Session>('/sessions/upload/claude-jsonl', formData);
      const normalizedTitle = title.trim();
      const created = await request<Case>('/cases', {
        method: 'POST',
        body: JSON.stringify({
          title: normalizedTitle.length > 0 ? normalizedTitle : (session.summary ?? file.name),
          session_id: session.id,
          source: 'offline_log_import',
          severity: 'medium',
          problem_type: 'other',
          scene_description: sceneDescription || null,
          expected_result: expectedResult || null,
          actual_result: actualResult || null,
          reproducible: reproducible === '' ? null : reproducible === 'true',
          responsible_owner: responsibleOwner || null,
        }),
      });
      await onCreated(created.id);
    } catch {
      setError(t.createCaseFailed);
    } finally {
      setSubmitting(false);
    }
  }
  return (
    <div className="modalOverlay" role="presentation" onMouseDown={onClose}>
      <form className="caseCreateModal" onSubmit={submit} onMouseDown={e => e.stopPropagation()}>
        <header className="modalHeader">
          <div className="modalHeaderMain">
            <div className="modalTitleRow"><span>{t.createCaseTitle}</span><strong>{t.claudeCodeJsonl}</strong></div>
          </div>
          <button className="iconButton" type="button" aria-label={t.closeModal} onClick={onClose}><X size={18} /></button>
        </header>
        <div className="caseCreateBody">
          <label>{t.title}<input value={title} onChange={e => setTitle(e.target.value)} placeholder={t.caseTitlePlaceholder} /></label>
          <label>{t.sceneDescription}<textarea value={sceneDescription} onChange={e => setSceneDescription(e.target.value)} /></label>
          <label>{t.expectedResult}<textarea value={expectedResult} onChange={e => setExpectedResult(e.target.value)} /></label>
          <label>{t.actualResult}<textarea value={actualResult} onChange={e => setActualResult(e.target.value)} /></label>
          <label>{t.reproducible}<select value={reproducible} onChange={e => setReproducible(e.target.value)}><option value="">{t.reproducibleUnknown}</option><option value="true">{t.reproducibleYes}</option><option value="false">{t.reproducibleNo}</option></select></label>
          <label>{t.responsibleOwner}<input value={responsibleOwner} onChange={e => setResponsibleOwner(e.target.value)} /></label>
          <label>{t.sessionFormat}<select defaultValue="claude-jsonl"><option value="claude-jsonl">{t.claudeCodeJsonl}</option></select></label>
          <label>{t.sessionRecordFile}<input type="file" accept=".jsonl,application/jsonl,text/plain" required onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
          {error && <div className="error">{error}</div>}
        </div>
        <footer className="modalFooter">
          <button type="button" onClick={onClose}>{t.close}</button>
          <button disabled={submitting}>{submitting ? t.loading : t.uploadAndCreate}</button>
        </footer>
      </form>
    </div>
  );
}

function CaseDetailPanel({ caseId, onChanged }: { caseId: string | null; onChanged: () => void }) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [caseForm, setCaseForm] = useState({
    scene_description: '',
    expected_result: '',
    actual_result: '',
    reproducible: '',
    responsible_owner: '',
    closure_practice: '',
    feedback_acceptance_conclusion: '',
  });
  const [caseInfoMessage, setCaseInfoMessage] = useState('');
  const load = () => (caseId ? request<CaseDetail>(`/cases/${caseId}`).then(setDetail) : Promise.resolve());
  useEffect(() => {
    setDetail(null);
    setChatSessionId(null);
    setCaseInfoMessage('');
    if (caseId) {
      void request<CaseDetail>(`/cases/${caseId}`).then(setDetail);
    }
  }, [caseId]);
  useEffect(() => {
    if (!detail) return;
    setCaseForm({
      scene_description: detail.scene_description ?? '',
      expected_result: detail.expected_result ?? '',
      actual_result: detail.actual_result ?? '',
      reproducible: detail.reproducible === null || detail.reproducible === undefined ? '' : String(detail.reproducible),
      responsible_owner: detail.responsible_owner ?? '',
      closure_practice: detail.closure_practice ?? '',
      feedback_acceptance_conclusion: detail.feedback_acceptance_conclusion ?? '',
    });
  }, [detail]);
  if (!caseId) return <section className="panel detail"><p className="muted">{t.selectCase}</p></section>;
  if (!detail) return <section className="panel detail">{t.loading}</section>;
  async function patch(status: string) {
    await request(`/cases/${caseId}`, { method: 'PATCH', body: JSON.stringify({ status }) });
    await load(); onChanged();
  }
  async function analyze() {
    await request(`/cases/${caseId}/analyze`, { method: 'POST', body: '{}' });
    await load(); onChanged();
  }
  async function addComment() {
    await request(`/cases/${caseId}/events`, { method: 'POST', body: JSON.stringify({ comment }) });
    setComment(''); await load();
  }
  function updateCaseForm(key: keyof typeof caseForm, value: string) {
    setCaseForm(current => ({ ...current, [key]: value }));
  }
  async function saveCaseInfo() {
    setCaseInfoMessage('');
    try {
      await request(`/cases/${caseId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          scene_description: caseForm.scene_description || null,
          expected_result: caseForm.expected_result || null,
          actual_result: caseForm.actual_result || null,
          reproducible: caseForm.reproducible === '' ? null : caseForm.reproducible === 'true',
          responsible_owner: caseForm.responsible_owner || null,
          closure_practice: caseForm.closure_practice || null,
          feedback_acceptance_conclusion: caseForm.feedback_acceptance_conclusion || null,
        }),
      });
      setCaseInfoMessage(t.caseInfoSaved);
      await load();
      onChanged();
    } catch {
      setCaseInfoMessage(t.caseInfoSaveFailed);
    }
  }
  return (
    <section className="panel detail">
      <h2>{detail.title}</h2>
      <div className="chips"><Badge value={detail.status} type="status" /><Badge value={detail.severity} type="severity" /><Badge value={detail.problem_type} /></div>
      {detail.session?.langfuse_url && <a href={detail.session.langfuse_url} target="_blank">{t.openLangfuseTrace}</a>}
      {detail.session_id && <button onClick={() => setChatSessionId(detail.session_id ?? null)}>{t.showRawSession}</button>}
      {chatSessionId && <SessionChatModal sessionId={chatSessionId} onClose={() => setChatSessionId(null)} />}
      <h3>{t.sceneDescription}</h3>
      <div className="caseInfoGrid">
        <label>{t.sceneDescription}<textarea value={caseForm.scene_description} onChange={e => updateCaseForm('scene_description', e.target.value)} /></label>
        <label>{t.expectedResult}<textarea value={caseForm.expected_result} onChange={e => updateCaseForm('expected_result', e.target.value)} /></label>
        <label>{t.actualResult}<textarea value={caseForm.actual_result} onChange={e => updateCaseForm('actual_result', e.target.value)} /></label>
        <label>{t.reproducible}<select value={caseForm.reproducible} onChange={e => updateCaseForm('reproducible', e.target.value)}><option value="">{t.reproducibleUnknown}</option><option value="true">{t.reproducibleYes}</option><option value="false">{t.reproducibleNo}</option></select></label>
        <label>{t.responsibleOwner}<input value={caseForm.responsible_owner} onChange={e => updateCaseForm('responsible_owner', e.target.value)} /></label>
        <label>{t.closurePractice}<textarea value={caseForm.closure_practice} onChange={e => updateCaseForm('closure_practice', e.target.value)} /></label>
        <label>{t.feedbackAcceptanceConclusion}<textarea value={caseForm.feedback_acceptance_conclusion} onChange={e => updateCaseForm('feedback_acceptance_conclusion', e.target.value)} /></label>
      </div>
      <div className="actions"><button onClick={saveCaseInfo}>{t.saveCaseInfo}</button>{caseInfoMessage && <span className="muted">{caseInfoMessage}</span>}</div>
      <div className="actions">
        <button onClick={analyze}><PlayCircle size={16} /> {t.analyze}</button>
        <button onClick={() => patch('to_analyze')}>{t.toAnalyze}</button>
        <button onClick={() => patch('in_progress')}>{t.inProgress}</button>
        <button onClick={() => patch('to_verify')}>{t.toVerify}</button>
        <button onClick={() => patch('closed')}>{t.close}</button>
      </div>
      <h3>{t.aiAnalysis}</h3>
      {detail.analyses.length === 0 ? <p className="muted">{t.noAnalysis}</p> : detail.analyses.map(a => <div className="analysis" key={a.id}><strong>{label(a.ownership_suggestion ?? t.unknown)}</strong><p>{a.summary}</p>{a.failure_point && <p><b>{t.failure}:</b> {a.failure_point}</p>}{a.error_message && <p className="error">{a.error_message}</p>}</div>)}
      <h3>{t.timeline}</h3>
      <div className="comment"><input value={comment} onChange={e => setComment(e.target.value)} placeholder={t.addComment} /><button onClick={addComment}>{t.add}</button></div>
      {detail.events.map(e => <div className="event" key={e.id}><b>{label(e.event_type)}</b> {e.from_status && <span>{label(e.from_status)} {'->'} {label(e.to_status)}</span>}<p>{e.comment}</p></div>)}
    </section>
  );
}

function App() {
  const [token, setToken] = useState(localStorage.getItem('hq_token'));
  const [tab, setTab] = useState('dashboard');
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    if (token) {
      void request<User>('/auth/me').then(setUser).catch(() => { localStorage.removeItem('hq_token'); setToken(null); });
    }
  }, [token]);
  if (!token) return <Login onLogin={() => setToken(localStorage.getItem('hq_token'))} />;
  const content = tab === 'dashboard' ? <Dashboard /> : tab === 'sessions' ? <Sessions /> : <Cases />;
  return (
    <main className="app">
      <aside>
        <div className="brandBlock">
          <h1>HarnessQuest</h1>
          <span>{t.workspaceKicker}</span>
        </div>
        <button className={tab === 'dashboard' ? 'active' : ''} onClick={() => setTab('dashboard')}><BarChart3 size={18} /> {t.dashboard}</button>
        <button className={tab === 'cases' ? 'active' : ''} onClick={() => setTab('cases')}><ClipboardList size={18} /> {t.cases}</button>
        <button className={tab === 'sessions' ? 'active' : ''} onClick={() => setTab('sessions')}><Bot size={18} /> {t.sessions}</button>
        <div className="spacer" />
        <p><span>{t.activeOperator}</span>{user?.display_name}</p>
        <button onClick={() => { localStorage.removeItem('hq_token'); setToken(null); }}><LogOut size={18} /> {t.logout}</button>
      </aside>
      <section className="content">
        <header className="workspaceHeader">
          <div>
            <p>{t.workspaceKicker}</p>
            <h2>{pageTitle(tab)}</h2>
          </div>
          <span>{pageSubtitle(tab)}</span>
        </header>
        {content}
      </section>
    </main>
  );
}

const root = document.getElementById('root');
if (!root) {
  throw new Error('Root element not found');
}
createRoot(root).render(<App />);
