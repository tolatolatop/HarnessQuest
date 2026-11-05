import { RotateCcw, Search, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { t } from '../../../config/i18n';
import { request } from '../../../core/api/client';
import { formatLocalTimestamp } from '../../../core/utils/format';
import { extractSessionChatBlocks, isCollapsedByDefault, matchesBlockQuery } from '../../../core/utils/chat';
import type { JsonValue, Session } from '../../../types/domain';

const INITIAL_VISIBLE_BLOCKS = 60;

export function SessionChatModal({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
  const [session, setSession] = useState<Session | null>(null);
  const [raw, setRaw] = useState<JsonValue | null>(null);
  const [showJson, setShowJson] = useState(false);
  const [blockQuery, setBlockQuery] = useState('');
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE_BLOCKS);
  useEffect(() => {
    setVisibleCount(INITIAL_VISIBLE_BLOCKS);
  }, [blockQuery]);
  useEffect(() => {
    setSession(null);
    setRaw(null);
    setBlockQuery('');
    setVisibleCount(INITIAL_VISIBLE_BLOCKS);
    void request<Session>(`/sessions/${sessionId}`).then(setSession);
    void request<JsonValue>(`/sessions/${sessionId}/raw`).then(setRaw);
  }, [sessionId]);
  const blocks = extractSessionChatBlocks(session?.metadata_json, raw);
  const transcriptReady = blocks.length > 0 || raw !== null;
  const filteredBlocks = blocks.filter(block => matchesBlockQuery(block, blockQuery));
  const visibleBlocks = filteredBlocks.slice(0, visibleCount);
  const remainingBlocks = filteredBlocks.length - visibleBlocks.length;
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
          <span>{t.blockSearchSummary.replace('{visible}', String(filteredBlocks.length)).replace('{total}', String(blocks.length))}</span>
        </div>
        <div className="chatTranscript">
          {!transcriptReady && <div className="chatBubble system">{t.loading}</div>}
          {transcriptReady && visibleBlocks.length === 0 && <div className="chatBubble system">{t.noMatchingBlocks}</div>}
          {visibleBlocks.map((block, index) => (
            <article className={`chatMessage ${block.kind}`} key={`${block.kind}-${index}`}>
              <details className="chatBubble" open={!isCollapsedByDefault(block.kind)}>
                <summary className="chatTitle">
                  <span className="chatKind"><strong>{block.title}</strong></span>
                  <span className="chatBadges">
                    {block.status && <em className={`chatStatus ${block.statusTone ?? 'muted'}`}>{block.status}</em>}
                    {block.meta && <span className="chatMeta">{formatLocalTimestamp(block.meta)}</span>}
                  </span>
                </summary>
                <pre>{block.body}</pre>
              </details>
            </article>
          ))}
          {remainingBlocks > 0 && (
            <div className="chatMore">
              <button
                className="secondaryButton"
                onClick={() => setVisibleCount(count => count + INITIAL_VISIBLE_BLOCKS)}
              >
                {t.loadMoreBlocks.replace('{count}', String(remainingBlocks))}
              </button>
            </div>
          )}
        </div>
        <footer className="modalFooter">
          <button onClick={() => setShowJson(!showJson)}>{showJson ? t.hideJson : t.showJson}</button>
        </footer>
        {showJson && <pre className="jsonViewer modalJson">{raw ? JSON.stringify(raw, null, 2) : t.loading}</pre>}
      </section>
    </div>
  );
}
