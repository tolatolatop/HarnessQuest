import type { ChatBlockKind } from '../types/domain';

/** Paths are relative to each message/content part; the first matching rule wins. */
export type ChatKindRule = {
  paths: string[];
  values: string[];
  kind: ChatBlockKind;
};

export type ChatRecognitionConfig = {
  conversationPaths: string[];
  rolePaths: string[];
  contentPaths: string[];
  rules: ChatKindRule[];
  roleAliases: Record<string, ChatBlockKind>;
};

/** Display-only adaptation point. No stored session records are rewritten. */
export const chatRecognition: ChatRecognitionConfig = {
  // These are alternative representations of a conversation, not additional messages.
  conversationPaths: [
    'conversation', 'messages', 'metadata.conversation', 'metadata.messages',
    'metadata.claude.raw_rows', 'metadata.opencode.raw.messages',
  ],
  rolePaths: ['message.role', 'info.role', 'role', 'author.role', 'speaker', 'type'],
  contentPaths: ['message.content', 'parts', 'content', 'text', 'payload.message', 'payload.text', 'message'],
  rules: [
    { paths: ['type', 'payload.type'], values: ['tool_use', 'tool_result', 'tool_call', 'tool', 'tool_call_output'], kind: 'tool' },
    { paths: ['type', 'payload.type'], values: ['function_call', 'function_call_output'], kind: 'function' },
    { paths: ['type', 'payload.type'], values: ['thinking', 'reasoning', 'analysis'], kind: 'thinking' },
    { paths: ['type', 'payload.type'], values: ['user_message', 'human_message'], kind: 'user' },
    { paths: ['type', 'payload.type'], values: ['agent_message', 'assistant_message', 'generation'], kind: 'assistant' },
    { paths: ['type', 'payload.type'], values: ['shell', 'bash', 'command'], kind: 'shell' },
    { paths: ['type', 'payload.type'], values: ['file', 'edit', 'write', 'patch', 'snapshot'], kind: 'file' },
    { paths: ['type', 'payload.type'], values: ['error'], kind: 'error' },
  ],
  roleAliases: {
    user: 'user', human: 'user', customer: 'user',
    assistant: 'assistant', ai: 'assistant', agent: 'assistant', model: 'assistant',
    thinking: 'thinking', reasoning: 'thinking',
    tool: 'tool', function: 'function', mcp: 'mcp', skill: 'skill',
    shell: 'shell', bash: 'shell', command: 'shell',
    file: 'file', edit: 'file', write: 'file', diff: 'diff',
    error: 'error', metadata: 'metadata', system: 'metadata', developer: 'metadata',
    observation: 'observation',
  },
};
