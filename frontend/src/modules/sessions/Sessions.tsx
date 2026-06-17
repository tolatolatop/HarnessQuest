import { useEffect, useState } from 'react';
import { t } from '../../config/i18n';
import { request } from '../../core/api/client';
import type { Session } from '../../types/domain';
import { SessionChatModal } from './components/SessionChatModal';

export function Sessions() {
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
