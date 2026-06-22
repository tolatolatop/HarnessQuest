export type User = { id: string; email: string; display_name: string; role: string };

export type Summary = {
  total_sessions: number;
  total_cases: number;
  open_cases: number;
  closed_cases: number;
  closure_rate: number;
  high_risk_cases: number;
  experience_count: number;
  avg_closure_hours: number;
  analysis_feedback_count: number;
  analysis_acceptance_rate: number;
};

export type BreakdownItem = { key: string; count: number };
export type Breakdown = {
  by_status: BreakdownItem[];
  by_severity: BreakdownItem[];
  by_problem_type: BreakdownItem[];
  by_agent_type: BreakdownItem[];
  by_repository: BreakdownItem[];
  by_owner: BreakdownItem[];
  by_tag: BreakdownItem[];
};

export type Session = {
  id: string;
  agent_type: string;
  repository?: string;
  branch?: string;
  summary?: string;
  langfuse_url?: string;
  project_id?: string;
  created_at: string;
};

export type Case = {
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

export type CaseDetail = Case & {
  session?: Session;
  analyses: Analysis[];
  events: EventItem[];
  human_conclusion?: string;
  handling_action?: string;
};

export type Analysis = {
  id: string;
  summary?: string;
  failure_point?: string;
  ownership_suggestion?: string;
  severity_suggestion?: string;
  next_steps: string[];
  experience_suggestion?: string;
  confidence?: number;
  human_feedback?: string;
  error_message?: string;
  created_at: string;
};

export type EventItem = {
  id: string;
  event_type: string;
  comment?: string;
  from_status?: string;
  to_status?: string;
  created_at: string;
};

export type JsonValue = null | boolean | number | string | JsonValue[] | JsonObject;
export type JsonObject = { [key in string]: JsonValue };

export type ChatBlockKind =
  | 'user'
  | 'assistant'
  | 'thinking'
  | 'tool'
  | 'function'
  | 'mcp'
  | 'skill'
  | 'shell'
  | 'file'
  | 'error'
  | 'diff'
  | 'observation'
  | 'metadata';

export type ChatBlock = { kind: ChatBlockKind; title: string; body: string; meta?: string };
