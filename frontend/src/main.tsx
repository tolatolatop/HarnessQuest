import type { SyntheticEvent } from 'react';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AlertTriangle,
  BarChart3,
  Bot,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  ClipboardList,
  Database,
  LogOut,
  PlayCircle,
  RotateCcw,
  Search,
  Upload,
  X,
} from 'lucide-react';
import { label, t } from './i18n';
import './styles.css';

const API = import.meta.env.VITE_API_BASE_URL ?? '';

type User = { id: string; email: string; display_name: string; role: string };
type Summary = { total_sessions: number; total_cases: number; open_cases: number; closed_cases: number; closure_rate: number; high_risk_cases: number; experience_count: number; avg_closure_hours: number; analysis_feedback_count: number; analysis_acceptance_rate: number };
type BreakdownItem = { key: string; count: number };
type Breakdown = { by_status: BreakdownItem[]; by_severity: BreakdownItem[]; by_problem_type: BreakdownItem[]; by_agent_type: BreakdownItem[]; by_repository: BreakdownItem[]; by_owner: BreakdownItem[]; by_tag: BreakdownItem[] };
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
  feedback_reporter?: string;
  responsible_owner?: string;
  tags?: string[] | null;
  closure_practice?: string;
  feedback_acceptance_conclusion?: string;
};
type CaseDetail = Case & { session?: Session; analyses: Analysis[]; events: EventItem[]; human_conclusion?: string; handling_action?: string };
type Analysis = { id: string; summary?: string; failure_point?: string; ownership_suggestion?: string; severity_suggestion?: string; next_steps: string[]; experience_suggestion?: string; confidence?: number; human_feedback?: string; error_message?: string; created_at: string };
type EventItem = { id: string; event_type: string; comment?: string; from_status?: string; to_status?: string; created_at: string };
type JsonValue = null | boolean | number | string | JsonValue[] | JsonObject;
type JsonObject = { [key in string]: JsonValue };
type ChatBlockKind = 'user' | 'assistant' | 'thinking' | 'tool' | 'function' | 'mcp' | 'skill' | 'shell' | 'file' | 'error' | 'diff' | 'observation' | 'metadata';
type ChatBlock = { kind: ChatBlockKind; title: string; body: string; meta?: string };
const CASE_SEVERITIES = ['low', 'medium', 'high', 'critical'] as const;
const CASE_PROBLEM_TYPES = [
  'incorrect_model_answer',
  'insufficient_context',
  'tool_call_failure',
  'command_execution_failure',
  'risky_code_change',
  'requirement_misunderstanding',
  'cost_or_latency_anomaly',
  'permission_or_security_issue',
  'user_workflow_issue',
  'other',
] as const;
const CUSTOM_PROBLEM_TYPE = '__custom_problem_type__';
const PRESET_PROBLEM_TYPE_SET = new Set<string>(CASE_PROBLEM_TYPES);

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

  if (!hasConversation) {
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

function parseTags(value: string): string[] {
  return Array.from(new Set(value.split(/[,\s，]+/).map(item => item.trim()).filter(Boolean)));
}

function problemTypeOptions(knownProblemTypes: string[] = []): string[] {
  return Array.from(new Set([...CASE_PROBLEM_TYPES, ...knownProblemTypes.filter(item => item && !PRESET_PROBLEM_TYPE_SET.has(item))]));
}

function selectedProblemTypeValue(value: string): string {
  return PRESET_PROBLEM_TYPE_SET.has(value) ? value : CUSTOM_PROBLEM_TYPE;
}

function formatDateTimeFilter(value: string, endOfDay = false): string | null {
  if (!value) return null;
  return new Date(`${value}T${endOfDay ? '23:59:59' : '00:00:00'}`).toISOString();
}

const STATUS_QUERY_LABELS: Record<string, string> = {
  '待分流': 'to_triage',
  '待分析': 'to_analyze',
  '处理中': 'in_progress',
  '待验证': 'to_verify',
  '已关闭': 'closed',
  'to_triage': 'to_triage',
  'to_analyze': 'to_analyze',
  'in_progress': 'in_progress',
  'to_verify': 'to_verify',
  'closed': 'closed',
};

type CaseQuery = { q: string; status: string; state: string; tags: string[]; createdFrom: string; createdTo: string };

function dateOnly(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function parseCreatedFilter(value: string): { createdFrom: string; createdTo: string } {
  const today = new Date();
  if (['今天', 'today'].includes(value)) {
    const day = dateOnly(today);
    return { createdFrom: day, createdTo: day };
  }
  if (['昨天', 'yesterday'].includes(value)) {
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    const day = dateOnly(yesterday);
    return { createdFrom: day, createdTo: day };
  }
  if (['最近7天', '7d', 'last7d'].includes(value)) {
    const start = new Date(today);
    start.setDate(today.getDate() - 6);
    return { createdFrom: dateOnly(start), createdTo: dateOnly(today) };
  }
  const range = value.split('..');
  if (range.length === 2) {
    return { createdFrom: range[0] ?? '', createdTo: range[1] ?? '' };
  }
  return { createdFrom: value, createdTo: value };
}

function parseCaseQuery(input: string): CaseQuery {
  const result: CaseQuery = { q: '', status: '', state: '', tags: [], createdFrom: '', createdTo: '' };
  const keywords: string[] = [];
  const tokens = input.match(/"[^"]+"|\S+/g) ?? [];
  for (const rawToken of tokens) {
    const token = rawToken.replace(/^"|"$/g, '');
    const separator = token.includes(':') ? ':' : token.includes('：') ? '：' : '';
    if (!separator) {
      keywords.push(token);
      continue;
    }
    const [rawKey, ...rest] = token.split(separator);
    const key = rawKey.toLowerCase();
    const value = rest.join(separator).trim();
    if (!value) continue;
    if (['is', '类型'].includes(key)) continue;
    if (['state', '状态'].includes(key)) {
      if (['open', '开启', '打开', '未关闭'].includes(value)) result.state = 'open';
      else if (['closed', '关闭', '已关闭'].includes(value)) result.state = 'closed';
      else result.status = STATUS_QUERY_LABELS[value] ?? value;
      continue;
    }
    if (['status'].includes(key)) {
      result.status = STATUS_QUERY_LABELS[value] ?? value;
      continue;
    }
    if (['tag', 'label', '标签'].includes(key)) {
      result.tags.push(...parseTags(value));
      continue;
    }
    if (['created', 'created-at', '创建', '创建时间'].includes(key)) {
      const range = parseCreatedFilter(value);
      result.createdFrom = range.createdFrom;
      result.createdTo = range.createdTo;
      continue;
    }
    keywords.push(token);
  }
  result.q = keywords.join(' ').trim();
  return result;
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

const TABS = ['dashboard', 'cases', 'sessions'] as const;
type Tab = (typeof TABS)[number];

type RouteState = { tab: Tab; caseId: string | null };

function parseHash(value: string | null | undefined): RouteState {
  const [rawTab, rawId] = (value ?? '').replace(/^#/, '').split('/');
  const tab = TABS.includes(rawTab as Tab) ? (rawTab as Tab) : 'dashboard';
  return { tab, caseId: tab === 'cases' && rawId ? decodeURIComponent(rawId) : null };
}

function currentRoute(): RouteState {
  return parseHash(window.location.hash);
}

function routeHash(tab: Tab, caseId: string | null = null): string {
  return tab === 'cases' && caseId ? `#cases/${encodeURIComponent(caseId)}` : `#${tab}`;
}

function isCollapsedByDefault(kind: ChatBlockKind): boolean {
  return ['tool', 'function', 'mcp', 'skill', 'shell', 'file', 'diff', 'metadata', 'observation'].includes(kind);
}

function matchesBlockQuery(block: ChatBlock, query: string): boolean {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return true;
  return [block.kind, block.title, block.meta, block.body].some(value => value?.toLowerCase().includes(normalizedQuery));
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
    [t.topRepository, breakdown?.by_repository ?? []],
    [t.topOwner, breakdown?.by_owner ?? []],
    [t.topTag, breakdown?.by_tag ?? []],
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
        <Stat label={t.avgClosureHours} value={summary.avg_closure_hours} icon={<CheckCircle2 size={20} />} />
        <Stat label={t.analysisFeedback} value={summary.analysis_feedback_count} icon={<ClipboardList size={20} />} />
        <Stat label={t.analysisAcceptance} value={`${Math.round(summary.analysis_acceptance_rate * 100)}%`} icon={<CheckCircle2 size={20} />} />
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
  const [blockQuery, setBlockQuery] = useState('');
  useEffect(() => {
    setSession(null);
    setRaw(null);
    setBlockQuery('');
    void request<Session>(`/sessions/${sessionId}`).then(setSession);
    void request<JsonValue>(`/sessions/${sessionId}/raw`).then(setRaw);
  }, [sessionId]);
  const blocks = extractChatBlocks(raw);
  const visibleBlocks = blocks.filter(block => matchesBlockQuery(block, blockQuery));
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
        <div className="chatFilterBar">
          <div className="chatFilterInput">
            <Search size={17} />
            <input value={blockQuery} onChange={e => setBlockQuery(e.target.value)} placeholder={t.searchConversationBlocks} />
            {blockQuery && <button className="iconButton" aria-label={t.reset} onClick={() => setBlockQuery('')}><RotateCcw size={15} /></button>}
          </div>
          <span>{t.blockSearchSummary.replace('{visible}', String(visibleBlocks.length)).replace('{total}', String(blocks.length))}</span>
        </div>
        <div className="chatTranscript">
          {!raw && <div className="chatBubble system">{t.loading}</div>}
          {raw && visibleBlocks.length === 0 && <div className="chatBubble system">{t.noMatchingBlocks}</div>}
          {visibleBlocks.map((block, index) => (
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

function Cases({ selectedCaseId, onSelectCase }: { selectedCaseId: string | null; onSelectCase: (caseId: string | null) => void }) {
  const [cases, setCases] = useState<Case[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [page, setPage] = useState(1);
  const filters = useMemo(() => parseCaseQuery(query), [query]);
  const pageSize = 8;
  const pageCount = Math.max(1, Math.ceil(cases.length / pageSize));
  const visibleCases = cases.slice((page - 1) * pageSize, page * pageSize);
  const load = useCallback(() => {
    const params = new URLSearchParams();
    if (filters.q.trim()) params.set('q', filters.q.trim());
    if (filters.status) params.set('status', filters.status);
    if (filters.state) params.set('state', filters.state);
    const createdFrom = formatDateTimeFilter(filters.createdFrom);
    const createdTo = formatDateTimeFilter(filters.createdTo, true);
    if (createdFrom) params.set('created_from', createdFrom);
    if (createdTo) params.set('created_to', createdTo);
    filters.tags.forEach(item => params.append('tag', item));
    const suffix = params.toString();
    return request<Case[]>(`/cases${suffix ? `?${suffix}` : ''}`).then(setCases);
  }, [filters.createdFrom, filters.createdTo, filters.q, filters.state, filters.status, filters.tags]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    setPage(1);
  }, [query]);
  useEffect(() => {
    setPage(current => Math.min(current, pageCount));
  }, [pageCount]);
  useEffect(() => {
    if (!selectedCaseId) return;
    const index = cases.findIndex(item => item.id === selectedCaseId);
    if (index >= 0) {
      setPage(Math.floor(index / pageSize) + 1);
    }
  }, [cases, selectedCaseId]);
  async function created(caseId: string) {
    await load();
    setPage(1);
    onSelectCase(caseId);
    setCreateOpen(false);
  }
  const knownTags = Array.from(new Set(cases.flatMap(item => item.tags ?? []))).slice(0, 6);
  const querySuggestions = [
    { label: '类型:工单', value: 'is:issue' },
    { label: '状态:开启', value: 'state:open' },
    { label: '状态:已关闭', value: 'state:closed' },
    { label: '状态:待分流', value: '状态:待分流' },
    { label: '状态:处理中', value: '状态:处理中' },
    { label: '状态:待验证', value: '状态:待验证' },
    { label: '创建:今天', value: '创建:今天' },
    { label: '创建:最近7天', value: '创建:最近7天' },
    ...knownTags.map(item => ({ label: `标签:${item}`, value: `标签:${item}` })),
  ];
  function appendQueryToken(value: string) {
    setQuery(current => `${current.trim()}${current.trim() ? ' ' : ''}${value} `);
    setSuggestionsOpen(true);
  }
  return (
    <div className="split">
      <section className="panel caseListPanel">
        <div className="panelHeader"><h2>{t.cases}</h2><button onClick={() => setCreateOpen(true)}><Upload size={16} /> {t.createCase}</button></div>
        <div className="caseSearchBox" onBlur={() => window.setTimeout(() => setSuggestionsOpen(false), 120)}>
          <label>{t.caseSearch}</label>
          <div className="issueSearch">
            <Search size={18} />
            <input value={query} onFocus={() => setSuggestionsOpen(true)} onChange={e => setQuery(e.target.value)} placeholder={t.caseSearchPlaceholder} />
            {query && <button className="iconButton" aria-label={t.reset} onClick={() => setQuery('')}><RotateCcw size={16} /></button>}
          </div>
          {suggestionsOpen && (
            <div className="querySuggestions">
              <div><strong>{t.searchSuggestions}</strong><span>{t.queryExample}: state:open 标签:工具失败 创建:最近7天 复现失败</span></div>
              <div className="suggestionGrid">
                {querySuggestions.map(item => <button key={item.value} onMouseDown={e => e.preventDefault()} onClick={() => appendQueryToken(item.value)}><span>{item.label}</span><code>{item.value}</code></button>)}
              </div>
            </div>
          )}
        </div>
        <table><thead><tr><th>{t.title}</th><th>{t.status}</th><th>{t.severity}</th><th>{t.type}</th><th>{t.tags}</th><th>{t.ai}</th></tr></thead><tbody>{visibleCases.map(c => <tr key={c.id} onClick={() => onSelectCase(c.id)} className={selectedCaseId === c.id ? 'selected' : ''}><td><strong className="caseTitle">{c.title}</strong></td><td><Badge value={c.status} type="status" /></td><td><Badge value={c.severity} type="severity" /></td><td>{label(c.problem_type)}</td><td><div className="tagList">{(c.tags ?? []).map(item => <span key={item}>{item}</span>)}</div></td><td><Badge value={c.ai_analysis_status} /></td></tr>)}</tbody></table>
        <div className="paginationBar">
          <span>{t.pageSummary.replace('{page}', String(page)).replace('{pages}', String(pageCount)).replace('{total}', String(cases.length))}</span>
          <div>
            <button className="iconButton" aria-label={t.previousPage} disabled={page <= 1} onClick={() => setPage(current => Math.max(1, current - 1))}><ChevronLeft size={16} /></button>
            <button className="iconButton" aria-label={t.nextPage} disabled={page >= pageCount} onClick={() => setPage(current => Math.min(pageCount, current + 1))}><ChevronRight size={16} /></button>
          </div>
        </div>
        {createOpen && <CreateCaseModal knownProblemTypes={cases.map(item => item.problem_type)} onClose={() => setCreateOpen(false)} onCreated={created} />}
      </section>
      <CaseDetailPanel caseId={selectedCaseId} knownProblemTypes={cases.map(item => item.problem_type)} onChanged={load} />
    </div>
  );
}

function CreateCaseModal({ knownProblemTypes, onClose, onCreated }: { knownProblemTypes: string[]; onClose: () => void; onCreated: (caseId: string) => Promise<void> }) {
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
      const session = await requestForm<Session>('/sessions/upload/auto', formData);
      const normalizedTitle = title.trim();
      const normalizedProblemType = problemType === CUSTOM_PROBLEM_TYPE ? customProblemType.trim() : problemType;
      const created = await request<Case>('/cases', {
        method: 'POST',
        body: JSON.stringify({
          title: normalizedTitle.length > 0 ? normalizedTitle : (session.summary ?? file.name),
          session_id: session.id,
          source: 'offline_log_import',
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
            <div className="modalTitleRow"><span>{t.createCaseTitle}</span><strong>{t.autoDetectSession}</strong></div>
          </div>
          <button className="iconButton" type="button" aria-label={t.closeModal} onClick={onClose}><X size={18} /></button>
        </header>
        <div className="caseCreateBody">
          <label>{t.title}<input value={title} onChange={e => setTitle(e.target.value)} placeholder={t.caseTitlePlaceholder} /></label>
          <label>{t.sceneDescription}<textarea value={sceneDescription} onChange={e => setSceneDescription(e.target.value)} /></label>
          <label>{t.expectedResult}<textarea value={expectedResult} onChange={e => setExpectedResult(e.target.value)} /></label>
          <label>{t.actualResult}<textarea value={actualResult} onChange={e => setActualResult(e.target.value)} /></label>
          <label>{t.severity}<select value={severity} onChange={e => setSeverity(e.target.value)}>{CASE_SEVERITIES.map(item => <option key={item} value={item}>{label(item)}</option>)}</select></label>
          <label>{t.problemType}<select value={problemType} onChange={e => setProblemType(e.target.value)}>{problemTypeOptions(knownProblemTypes).map(item => <option key={item} value={item}>{label(item)}</option>)}<option value={CUSTOM_PROBLEM_TYPE}>{t.customProblemType}</option></select></label>
          {problemType === CUSTOM_PROBLEM_TYPE && <label>{t.customProblemType}<input value={customProblemType} onChange={e => setCustomProblemType(e.target.value)} placeholder={t.customProblemTypePlaceholder} maxLength={128} /></label>}
          <label>{t.reproducible}<select value={reproducible} onChange={e => setReproducible(e.target.value)}><option value="">{t.reproducibleUnknown}</option><option value="true">{t.reproducibleYes}</option><option value="false">{t.reproducibleNo}</option></select></label>
          <label>{t.feedbackReporter}<input value={feedbackReporter} onChange={e => setFeedbackReporter(e.target.value)} /></label>
          <label>{t.responsibleOwner}<input value={responsibleOwner} onChange={e => setResponsibleOwner(e.target.value)} /></label>
          <label>{t.tags}<input value={tags} onChange={e => setTags(e.target.value)} placeholder={t.tagsPlaceholder} /></label>
          <label>{t.sessionRecordFile}<input type="file" accept=".json,.jsonl,application/json,application/jsonl,text/plain" required onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
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

function CaseDetailPanel({ caseId, knownProblemTypes, onChanged }: { caseId: string | null; knownProblemTypes: string[]; onChanged: () => void }) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [analysisMessage, setAnalysisMessage] = useState('');
  const [experienceMessage, setExperienceMessage] = useState('');
  const [experienceForm, setExperienceForm] = useState({ title: '', content: '', tags: '' });
  const [caseForm, setCaseForm] = useState({
    scene_description: '',
    expected_result: '',
    actual_result: '',
    severity: 'medium',
    problem_type: 'other',
    reproducible: '',
    feedback_reporter: '',
    responsible_owner: '',
    tags: '',
    closure_practice: '',
    feedback_acceptance_conclusion: '',
  });
  const [caseInfoMessage, setCaseInfoMessage] = useState('');
  const load = () => (caseId ? request<CaseDetail>(`/cases/${caseId}`).then(setDetail) : Promise.resolve());
  useEffect(() => {
    setDetail(null);
    setChatSessionId(null);
    setCaseInfoMessage('');
    setAnalysisMessage('');
    setExperienceMessage('');
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
      severity: detail.severity,
      problem_type: detail.problem_type,
      reproducible: detail.reproducible === null || detail.reproducible === undefined ? '' : String(detail.reproducible),
      feedback_reporter: detail.feedback_reporter ?? '',
      responsible_owner: detail.responsible_owner ?? '',
      tags: (detail.tags ?? []).join(', '),
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
  async function saveAnalysisFeedback(analysisId: string, humanFeedback: string) {
    await request(`/cases/${caseId}/analyses/${analysisId}/feedback`, { method: 'POST', body: JSON.stringify({ human_feedback: humanFeedback }) });
    setAnalysisMessage(t.analysisFeedbackSaved);
    await load();
  }
  async function extractExperience(analysis?: Analysis) {
    if (!detail) return;
    const currentDetail = detail;
    const titleText = experienceForm.title.trim();
    const contentText = experienceForm.content.trim();
    const title = titleText.length > 0 ? titleText : currentDetail.title;
    const fallbackContent = analysis?.experience_suggestion ?? analysis?.summary ?? currentDetail.closure_practice ?? currentDetail.actual_result ?? currentDetail.title;
    const content = contentText.length > 0 ? contentText : fallbackContent;
    await request(`/cases/${caseId}/experience`, {
      method: 'POST',
      body: JSON.stringify({ title, content, type: 'failure_mode', tags: parseTags(experienceForm.tags || caseForm.tags) }),
    });
    setExperienceForm({ title: '', content: '', tags: '' });
    setExperienceMessage(t.experienceSaved);
    await load();
    onChanged();
  }
  function updateCaseForm(key: keyof typeof caseForm, value: string) {
    setCaseForm(current => ({ ...current, [key]: value }));
  }
  async function saveCaseInfo() {
    setCaseInfoMessage('');
    try {
      const normalizedProblemType = caseForm.problem_type.trim() || 'other';
      await request(`/cases/${caseId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          scene_description: caseForm.scene_description || null,
          expected_result: caseForm.expected_result || null,
          actual_result: caseForm.actual_result || null,
          severity: caseForm.severity,
          problem_type: normalizedProblemType,
          reproducible: caseForm.reproducible === '' ? null : caseForm.reproducible === 'true',
          feedback_reporter: caseForm.feedback_reporter || null,
          responsible_owner: caseForm.responsible_owner || null,
          tags: parseTags(caseForm.tags),
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
        <label>{t.severity}<select value={caseForm.severity} onChange={e => updateCaseForm('severity', e.target.value)}>{CASE_SEVERITIES.map(item => <option key={item} value={item}>{label(item)}</option>)}</select></label>
        <label>{t.problemType}<select value={selectedProblemTypeValue(caseForm.problem_type)} onChange={e => updateCaseForm('problem_type', e.target.value === CUSTOM_PROBLEM_TYPE ? '' : e.target.value)}>{problemTypeOptions([...knownProblemTypes, detail.problem_type]).map(item => <option key={item} value={item}>{label(item)}</option>)}<option value={CUSTOM_PROBLEM_TYPE}>{t.customProblemType}</option></select></label>
        {selectedProblemTypeValue(caseForm.problem_type) === CUSTOM_PROBLEM_TYPE && <label>{t.customProblemType}<input value={caseForm.problem_type} onChange={e => updateCaseForm('problem_type', e.target.value)} placeholder={t.customProblemTypePlaceholder} maxLength={128} /></label>}
        <label>{t.reproducible}<select value={caseForm.reproducible} onChange={e => updateCaseForm('reproducible', e.target.value)}><option value="">{t.reproducibleUnknown}</option><option value="true">{t.reproducibleYes}</option><option value="false">{t.reproducibleNo}</option></select></label>
        <label>{t.feedbackReporter}<input value={caseForm.feedback_reporter} onChange={e => updateCaseForm('feedback_reporter', e.target.value)} /></label>
        <label>{t.responsibleOwner}<input value={caseForm.responsible_owner} onChange={e => updateCaseForm('responsible_owner', e.target.value)} /></label>
        <label>{t.tags}<input value={caseForm.tags} onChange={e => updateCaseForm('tags', e.target.value)} placeholder={t.tagsPlaceholder} /></label>
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
      {analysisMessage && <p className="muted">{analysisMessage}</p>}
      {detail.analyses.length === 0 ? <p className="muted">{t.noAnalysis}</p> : detail.analyses.map(a => <div className="analysis" key={a.id}><strong>{label(a.ownership_suggestion ?? t.unknown)}</strong><p>{a.summary}</p>{a.failure_point && <p><b>{t.failure}:</b> {a.failure_point}</p>}{a.experience_suggestion && <p><b>{t.experience}:</b> {a.experience_suggestion}</p>}{a.human_feedback && <p><b>{t.analysisFeedback}:</b> {a.human_feedback}</p>}{a.error_message && <p className="error">{a.error_message}</p>}<div className="analysisActions"><button onClick={() => saveAnalysisFeedback(a.id, 'accepted')}>{t.acceptAnalysis}</button><button onClick={() => saveAnalysisFeedback(a.id, 'needs_correction')}>{t.correctAnalysis}</button><button onClick={() => extractExperience(a)}>{t.extractExperience}</button></div></div>)}
      <h3>{t.extractExperience}</h3>
      <div className="experienceForm">
        <label>{t.experienceTitle}<input value={experienceForm.title} onChange={e => setExperienceForm(current => ({ ...current, title: e.target.value }))} placeholder={detail.title} /></label>
        <label>{t.experienceContent}<textarea value={experienceForm.content} onChange={e => setExperienceForm(current => ({ ...current, content: e.target.value }))} placeholder={detail.analyses[0]?.experience_suggestion ?? detail.closure_practice ?? ''} /></label>
        <label>{t.tags}<input value={experienceForm.tags} onChange={e => setExperienceForm(current => ({ ...current, tags: e.target.value }))} placeholder={caseForm.tags || t.tagsPlaceholder} /></label>
        <div className="actions"><button onClick={() => extractExperience(detail.analyses[0])}>{t.extractExperience}</button>{experienceMessage && <span className="muted">{experienceMessage}</span>}</div>
      </div>
      <h3>{t.timeline}</h3>
      <div className="comment"><input value={comment} onChange={e => setComment(e.target.value)} placeholder={t.addComment} /><button onClick={addComment}>{t.add}</button></div>
      {detail.events.map(e => <div className="event" key={e.id}><b>{label(e.event_type)}</b> {e.from_status && <span>{label(e.from_status)} {'->'} {label(e.to_status)}</span>}<p>{e.comment}</p></div>)}
    </section>
  );
}

function App() {
  const [token, setToken] = useState(localStorage.getItem('hq_token'));
  const [route, setRoute] = useState<RouteState>(currentRoute);
  const [user, setUser] = useState<User | null>(null);
  const tab = route.tab;
  useEffect(() => {
    if (token) {
      void request<User>('/auth/me').then(setUser).catch(() => { localStorage.removeItem('hq_token'); setToken(null); });
    }
  }, [token]);
  useEffect(() => {
    const onHashChange = () => setRoute(currentRoute());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);
  function navigate(nextTab: Tab, caseId: string | null = null) {
    const nextHash = routeHash(nextTab, caseId);
    if (window.location.hash === nextHash) {
      setRoute({ tab: nextTab, caseId: nextTab === 'cases' ? caseId : null });
      return;
    }
    window.location.hash = nextHash;
  }
  if (!token) return <Login onLogin={() => setToken(localStorage.getItem('hq_token'))} />;
  const content = tab === 'dashboard' ? <Dashboard /> : tab === 'sessions' ? <Sessions /> : <Cases selectedCaseId={route.caseId} onSelectCase={caseId => navigate('cases', caseId)} />;
  return (
    <main className="app">
      <aside>
        <div className="brandBlock">
          <h1>HarnessQuest</h1>
          <span>{t.workspaceKicker}</span>
        </div>
        <button className={tab === 'dashboard' ? 'active' : ''} onClick={() => navigate('dashboard')}><BarChart3 size={18} /> {t.dashboard}</button>
        <button className={tab === 'cases' ? 'active' : ''} onClick={() => navigate('cases')}><ClipboardList size={18} /> {t.cases}</button>
        <button className={tab === 'sessions' ? 'active' : ''} onClick={() => navigate('sessions')}><Bot size={18} /> {t.sessions}</button>
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
