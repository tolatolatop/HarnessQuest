import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { createServer } from 'vite';

// Use the project's existing TypeScript loader; no extra test framework is needed.
const server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false } });
let extractChatBlocks;
let extractSessionChatBlocks;
let isCollapsedByDefault;
let chatRecognition;
let formatLocalTimestamp;
try {
  ({ extractChatBlocks, extractSessionChatBlocks, isCollapsedByDefault } = await server.ssrLoadModule('/src/core/utils/chat.ts'));
  ({ chatRecognition } = await server.ssrLoadModule('/src/config/chatRecognition.ts'));
  ({ formatLocalTimestamp } = await server.ssrLoadModule('/src/core/utils/format.ts'));
} finally {
  await server.close();
}

function deepFreeze(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(deepFreeze);
    Object.freeze(value);
  }
  return value;
}

const kinds = raw => extractChatBlocks(raw).map(block => block.kind);

test('Claude mixed user envelope: only user text is placed on the right', () => {
  const raw = deepFreeze({ messages: [
    { type: 'user', message: { role: 'user', content: [
      { type: 'text', text: '请检查结果' },
      { type: 'tool_result', tool_use_id: 'call-1', content: 'done' },
    ] } },
    { type: 'assistant', message: { content: [
      { type: 'thinking', thinking: '检查中' },
      { type: 'tool_use', id: 'call-2', name: 'search_user', input: { query: 'hello' } },
      { type: 'text', text: '已完成' },
    ] } },
  ] });
  const before = JSON.stringify(raw);
  const blocks = extractChatBlocks(raw);
  assert.deepEqual(blocks.map(block => block.kind), ['user', 'tool', 'thinking', 'tool', 'assistant']);
  assert.equal(blocks[0].body, '请检查结果');
  assert.equal(JSON.parse(blocks[1].body).tool_use_id, 'call-1');
  assert.equal(blocks[2].body, '检查中');
  assert.equal(JSON.stringify(raw), before);
});

test('opencode nested info.role and parts', () => {
  assert.deepEqual(kinds({ messages: [
    { info: { role: 'user' }, parts: [{ type: 'text', text: '你好' }] },
    { info: { role: 'assistant' }, parts: [
      { type: 'reasoning', text: '思考' },
      { type: 'tool', tool: 'bash', state: { status: 'completed', output: 'ok' } },
      { type: 'text', text: '完成' },
    ] },
  ] }), ['user', 'thinking', 'tool', 'assistant']);
});

test('event envelope subtypes and exact role aliases', () => {
  assert.deepEqual(kinds({ messages: [
    { type: 'event_msg', payload: { type: 'user_message', message: '问题' } },
    { type: 'event_msg', payload: { type: 'agent_message', message: '回复' } },
    { role: ' Human ', content: '用户' },
    { role: 'AI', content: '助手' },
    { role: 'user_search_event', content: '未知事件，不应因为包含 user 而靠右' },
    { role: 'system', content: '系统事件' },
  ] }), ['user', 'assistant', 'user', 'assistant', 'observation', 'metadata']);
});

test('alternative conversation fields do not duplicate messages; repeated turns remain', () => {
  const conversation = [{ role: 'user', content: '继续' }, { role: 'user', content: '继续' }];
  assert.equal(extractChatBlocks({ conversation, messages: conversation, metadata: { conversation } }).length, 2);
  assert.deepEqual(kinds({ conversation: [], metadata: { messages: conversation } }), ['user', 'user']);
});

test('one config adapts new source paths, role fields, content fields and event rules', () => {
  const config = {
    ...chatRecognition,
    conversationPaths: ['record.turns', ...chatRecognition.conversationPaths],
    rolePaths: ['sender.kind', ...chatRecognition.rolePaths],
    contentPaths: ['body', ...chatRecognition.contentPaths],
    roleAliases: { ...chatRecognition.roleAliases, visitor: 'user', bot_v2: 'assistant' },
    rules: [{ paths: ['event.name'], values: ['execution_done'], kind: 'tool' }, ...chatRecognition.rules],
  };
  const raw = deepFreeze({ record: { turns: [
    { sender: { kind: 'visitor' }, body: '问题' },
    { sender: { kind: 'bot_v2' }, body: '回复' },
    { sender: { kind: 'visitor' }, event: { name: 'execution_done' }, body: '结果' },
  ] } });
  assert.deepEqual(extractChatBlocks(raw, config).map(block => block.kind), ['user', 'assistant', 'tool']);
  assert.deepEqual(extractChatBlocks(raw), []);
});

test('native repository sample retains user, assistant and event fallback', async () => {
  const raw = JSON.parse(await readFile(new URL('../../examples/sample-session.json', import.meta.url), 'utf8'));
  assert.deepEqual(kinds(raw), ['user', 'assistant', 'tool', 'shell', 'error', 'diff']);
});

test('raw row arrays and unusable sources fall back without throwing', () => {
  assert.deepEqual(kinds([{ role: 'user', content: 'hello' }]), ['user']);
  assert.deepEqual(kinds({ metadata: { claude: { raw_rows: [{ type: 'assistant', message: { content: 'hello' } }] } } }), ['assistant']);
  assert.deepEqual(kinds({ conversation: [null, 'bad'], user_input: 'hello' }), ['user']);
  assert.deepEqual(kinds(null), []);
});

test('DeepSeek session details use the parsed transcript while keeping the original artifact', async () => {
  const log = await readFile(new URL('../../examples/deepseek-harness-session.v4.jsonl', import.meta.url), 'utf8');
  const rows = log.trim().split('\n').map(line => JSON.parse(line));
  const raw = deepFreeze({ format: 'deepseek_harness_jsonl', header: rows[0], rows });
  const metadata = deepFreeze({ conversation: [
    { role: 'user', content: 'Check the project test command.' },
    { role: 'thinking', content: 'Read the project configuration.' },
    { role: 'shell', title: 'cat pyproject.toml', content: 'Input:\ncat pyproject.toml\n\nOutput:\n[tool.pytest.ini_options]' },
    { role: 'assistant', content: 'Use uv run pytest to run the tests.' },
  ] });
  const before = JSON.stringify({ metadata, raw });

  const blocks = extractSessionChatBlocks(metadata, raw);

  assert.deepEqual(blocks.map(block => block.kind), ['user', 'thinking', 'shell', 'assistant']);
  assert.equal(blocks[0].body, 'Check the project test command.');
  assert.equal(blocks.at(-1).body, 'Use uv run pytest to run the tests.');
  assert.deepEqual(extractSessionChatBlocks(metadata, null), blocks);
  assert.equal(JSON.stringify({ metadata, raw }), before);
});

test('session transcript falls back to legacy raw artifacts when metadata has no parsed conversation', () => {
  const raw = { metadata: { conversation: [{ role: 'user', content: 'legacy prompt' }] } };
  for (const metadata of [undefined, {}, { conversation: [] }, { errors: ['tool failed'] }]) {
    assert.equal(extractSessionChatBlocks(metadata, raw)[0].body, 'legacy prompt');
  }
  assert.deepEqual(extractSessionChatBlocks(undefined, null), []);
  assert.deepEqual(extractSessionChatBlocks({ conversation: [] }, { format: 'deepseek_harness_jsonl', rows: [] }), []);
  assert.equal(extractSessionChatBlocks({ user_input: 'summary prompt' }, null)[0].body, 'summary prompt');
});

test('local timestamps render to the second without a timezone suffix', () => {
  const expected = (() => {
    const date = new Date('2026-11-05T03:51:19.012340+00:00');
    const pad = part => String(part).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  })();
  assert.equal(formatLocalTimestamp('2026-11-05T03:51:19.012340+00:00'), expected);
  assert.match(formatLocalTimestamp('2026-11-05T03:51:19.012340+00:00'), /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
  // Non-timestamp metadata (e.g. a fallback label) is passed through unchanged.
  assert.equal(formatLocalTimestamp('工具调用'), '工具调用');
});

test('thinking blocks collapse by default while dialogue stays open', () => {
  assert.equal(isCollapsedByDefault('thinking'), true);
  assert.equal(isCollapsedByDefault('shell'), true);
  assert.equal(isCollapsedByDefault('user'), false);
  assert.equal(isCollapsedByDefault('assistant'), false);
});

test('shell conversation items expose exit status badges', () => {
  const metadata = deepFreeze({ conversation: [
    { role: 'shell', title: 'pytest -q', content: 'Input:\n{}\n\nOutput:\n2 failed', exit_code: 2, status: 'completed' },
    { role: 'shell', title: 'sleep 100', content: 'Input:\n{}\n\nOutput:\nstill running', exit_code: null, status: 'running', background_job: 'bash-9' },
    { role: 'shell', title: 'tail -f', content: 'Input:\n{}\n\nOutput:\nkilled', exit_code: 143, status: 'killed' },
    { role: 'shell', title: 'pending call', content: 'Input:\n{}\n\nOutput:\nPending (no result recorded)', status: 'pending' },
  ] });

  const blocks = extractSessionChatBlocks(metadata, null);

  assert.deepEqual(blocks.map(block => block.statusTone), ['bad', 'warn', 'bad', 'muted']);
  assert.match(blocks[0].status, /退出码 2/);
  assert.match(blocks[1].status, /后台运行 · bash-9/);
  assert.match(blocks[2].status, /信号终止 · 退出码 143/);
  assert.equal(blocks[3].status, '待返回');
});
