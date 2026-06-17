import { AlertTriangle, Bot, CheckCircle2, ClipboardList, Database } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Stat } from '../../components/Stat';
import { label, t } from '../../config/i18n';
import { request } from '../../core/api/client';
import type { Breakdown, Summary } from '../../types/domain';

export function Dashboard() {
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
