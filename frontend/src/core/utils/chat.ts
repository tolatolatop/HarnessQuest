import { label, t } from '../../config/i18n';
import type { ChatBlock, ChatBlockKind, JsonObject, JsonValue } from '../../types/domain';

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

export function extractChatBlocks(raw: JsonValue | null): ChatBlock[] {
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

export function isCollapsedByDefault(kind: ChatBlockKind): boolean {
  return ['tool', 'function', 'mcp', 'skill', 'shell', 'file', 'diff', 'metadata', 'observation'].includes(kind);
}

export function matchesBlockQuery(block: ChatBlock, query: string): boolean {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return true;
  return [block.kind, block.title, block.meta, block.body].some(value => value?.toLowerCase().includes(normalizedQuery));
}
