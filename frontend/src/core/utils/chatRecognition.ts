import { chatRecognition } from '../../config/chatRecognition';
import type { ChatRecognitionConfig } from '../../config/chatRecognition';
import { label, t } from '../../config/i18n';
import type { ChatBlock, ChatBlockKind, JsonObject, JsonValue } from '../../types/domain';

export function isChatObject(value: JsonValue | undefined): value is JsonObject {
  return value !== undefined && value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function valueAtPath(value: JsonValue, path: string): JsonValue | undefined {
  let current: JsonValue | undefined = value;
  for (const key of path.split('.')) {
    if (!isChatObject(current)) return undefined;
    current = current[key];
  }
  return current;
}

function firstValue(value: JsonObject, paths: string[]): JsonValue | undefined {
  for (const path of paths) {
    const result = valueAtPath(value, path);
    if (result !== undefined && result !== null && result !== '') return result;
  }
  return undefined;
}

function stringValue(value: JsonValue | undefined): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function ruleKind(value: JsonObject, config: ChatRecognitionConfig): ChatBlockKind | undefined {
  return config.rules.find(rule => rule.paths.some(path => {
    const candidate = stringValue(valueAtPath(value, path))?.trim().toLowerCase();
    return candidate !== undefined && rule.values.some(alias => alias.toLowerCase() === candidate);
  }))?.kind;
}

function roleKind(value: JsonObject, config: ChatRecognitionConfig): ChatBlockKind | undefined {
  for (const path of config.rolePaths) {
    const role = stringValue(valueAtPath(value, path))?.trim().toLowerCase();
    if (role && Object.prototype.hasOwnProperty.call(config.roleAliases, role)) return config.roleAliases[role];
  }
  return undefined;
}

export function recognizeMessageKind(
  message: JsonObject,
  part?: JsonObject,
  config: ChatRecognitionConfig = chatRecognition,
): ChatBlockKind {
  // A tool result may be transported in a user envelope. Its own type takes priority.
  return (part && (ruleKind(part, config) ?? roleKind(part, config)))
    ?? ruleKind(message, config) ?? roleKind(message, config) ?? 'observation';
}

function messageBlocks(message: JsonObject, config: ChatRecognitionConfig): ChatBlock[] {
  const content = firstValue(message, config.contentPaths);
  const parts = Array.isArray(content) ? content : [content ?? message];
  const metaValue = firstValue(message, ['timestamp', 'info.time.created', 'time.created']);
  const meta = typeof metaValue === 'string' || typeof metaValue === 'number' ? String(metaValue) : undefined;
  return parts.flatMap(part => {
    if (part === null) return [];
    const object = isChatObject(part) ? part : undefined;
    const kind = recognizeMessageKind(message, object, config);
    // Keep structured event details intact, including tool IDs, inputs, outputs and status.
    const partType = object ? stringValue(object.type) : undefined;
    const isTextPart = partType && ['text', 'input_text', 'output_text', 'thinking', 'reasoning'].includes(partType);
    const bodyValue = object && isTextPart ? (object.text ?? object.thinking ?? object.content ?? object) : part;
    const body = typeof bodyValue === 'string' ? bodyValue : JSON.stringify(bodyValue, null, 2);
    if (!body.trim()) return [];
    const title = stringValue(object?.title) ?? stringValue(object?.name) ?? stringValue(object?.tool)
      ?? stringValue(message.title) ?? label(kind);
    return [{ kind, title: title || t.observation, body, meta }];
  });
}

export function extractConversationBlocks(
  raw: JsonValue | null,
  config: ChatRecognitionConfig = chatRecognition,
): ChatBlock[] {
  const sources = Array.isArray(raw) ? [raw] : config.conversationPaths.map(path => valueAtPath(raw, path));
  for (const source of sources) {
    if (!Array.isArray(source)) continue;
    const blocks = source.flatMap(message => isChatObject(message) ? messageBlocks(message, config) : []);
    if (blocks.length) return blocks;
  }
  return [];
}
