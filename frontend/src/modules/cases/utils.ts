import { t } from '../../config/i18n';
import { parseTags } from '../../core/utils/format';
import { CASE_PROBLEM_TYPES, CUSTOM_PROBLEM_TYPE, PRESET_PROBLEM_TYPE_SET } from './constants';

export type CaseQuery = { q: string; status: string; state: string; tags: string[]; createdFrom: string; createdTo: string };

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

export function problemTypeOptions(knownProblemTypes: string[] = []): string[] {
  return Array.from(new Set([...CASE_PROBLEM_TYPES, ...knownProblemTypes.filter(item => item && !PRESET_PROBLEM_TYPE_SET.has(item))]));
}

export function selectedProblemTypeValue(value: string): string {
  return PRESET_PROBLEM_TYPE_SET.has(value) ? value : CUSTOM_PROBLEM_TYPE;
}

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

export function parseCaseQuery(input: string): CaseQuery {
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

export function formatDateTimeFilter(value: string, endOfDay = false): string | null {
  if (!value) return null;
  return new Date(`${value}T${endOfDay ? '23:59:59' : '00:00:00'}`).toISOString();
}

export function caseQuerySuggestions(tags: string[]) {
  return [
    { label: '类型:工单', value: 'is:issue' },
    { label: '状态:开启', value: 'state:open' },
    { label: '状态:已关闭', value: 'state:closed' },
    { label: '状态:待分流', value: '状态:待分流' },
    { label: '状态:处理中', value: '状态:处理中' },
    { label: '状态:待验证', value: '状态:待验证' },
    { label: '创建:今天', value: '创建:今天' },
    { label: '创建:最近7天', value: '创建:最近7天' },
    ...tags.map(item => ({ label: `标签:${item}`, value: `标签:${item}` })),
  ];
}

export function searchExample(): string {
  return `${t.queryExample}: state:open 标签:工具失败 创建:最近7天 复现失败`;
}
