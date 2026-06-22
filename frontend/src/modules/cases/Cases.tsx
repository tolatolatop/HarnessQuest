import { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, PlayCircle, RotateCcw, Search, Upload } from 'lucide-react';
import { Badge } from '../../components/Badge';
import { label, t } from '../../config/i18n';
import { request } from '../../core/api/client';
import { parseTags, relativeTime } from '../../core/utils/format';
import type { Analysis, Case, CaseDetail } from '../../types/domain';
import { SessionChatModal } from '../sessions/components/SessionChatModal';
import { CreateCaseModal } from './components/CreateCaseModal';
import { CASE_SEVERITIES, CUSTOM_PROBLEM_TYPE } from './constants';
import { caseQuerySuggestions, formatDateTimeFilter, parseCaseQuery, problemTypeOptions, searchExample, selectedProblemTypeValue } from './utils';

export function Cases({ selectedCaseId, onSelectCase }: { selectedCaseId: string | null; onSelectCase: (caseId: string | null) => void }) {
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
  const querySuggestions = caseQuerySuggestions(knownTags);
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
              <div><strong>{t.searchSuggestions}</strong><span>{searchExample()}</span></div>
              <div className="suggestionGrid">
                {querySuggestions.map(item => <button key={item.value} onMouseDown={e => e.preventDefault()} onClick={() => appendQueryToken(item.value)}><span>{item.label}</span><code>{item.value}</code></button>)}
              </div>
            </div>
          )}
        </div>
        <table><thead><tr><th>{t.title}</th><th>{t.createdAt}</th><th>{t.status}</th><th>{t.severity}</th><th>{t.type}</th><th>{t.tags}</th><th>{t.ai}</th></tr></thead><tbody>{visibleCases.map(c => <tr key={c.id} onClick={() => onSelectCase(c.id)} className={selectedCaseId === c.id ? 'selected' : ''}><td><strong className="caseTitle">{c.title}</strong></td><td><span className="relativeTime">{relativeTime(c.created_at)}</span></td><td><Badge value={c.status} type="status" /></td><td><Badge value={c.severity} type="severity" /></td><td>{label(c.problem_type)}</td><td><div className="tagList">{(c.tags ?? []).map(item => <span key={item}>{item}</span>)}</div></td><td><Badge value={c.ai_analysis_status} /></td></tr>)}</tbody></table>
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
