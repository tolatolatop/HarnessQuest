export const CASE_SEVERITIES = ['low', 'medium', 'high', 'critical'] as const;
export const CASE_PROBLEM_TYPES = [
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

export const CUSTOM_PROBLEM_TYPE = '__custom_problem_type__';
export const PRESET_PROBLEM_TYPE_SET = new Set<string>(CASE_PROBLEM_TYPES);
