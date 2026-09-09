# 前端会话展示规则

本功能只把已读取的会话映射为浏览器内的展示块，决定用户消息靠右、AI 和事件靠左。不会写回原始 JSON、修改数据库、重新导入会话或产生业务记录。原始 JSON 查看功能保持原样。

## 快速适配

统一配置位于 `frontend/src/config/chatRecognition.ts`。先在会话弹窗点击“原始 JSON”，查看出错消息的字段，再按以下方式调整：

| 格式变化 | 修改项 | 示例 |
| --- | --- | --- |
| 新的用户/AI 角色名 | `roleAliases` | `visitor: 'user'`、`bot_v2: 'assistant'` |
| 角色移动到嵌套字段 | `rolePaths` | 在前面添加 `'sender.kind'` |
| 文本字段改名 | `contentPaths` | 在前面添加 `'body'` |
| 会话列表路径改变 | `conversationPaths` | 在前面添加 `'record.turns'` |
| 事件被误认为用户消息 | `rules` | 根据事件类型优先指定 `kind: 'tool'` |

例如，以下消息虽然有用户角色，但实际是工具执行结果：

```json
{"role":"user","event":{"name":"execution_done"},"content":"执行完成"}
```

在 `rules` 最前面添加：

```ts
{ paths: ['event.name'], values: ['execution_done'], kind: 'tool' },
```

消息即显示在左侧。规则按顺序首次匹配生效，角色别名为精确匹配（忽略大小写和首尾空格），避免 `user_search_event` 因包含 `user` 而误判。字段路径使用点号访问对象，不支持数组下标或通配符。

配置属于前端代码：开发时 Vite 热更新；部署后生效需要重新构建/发布前端，无需重新上传历史会话。当前没有后台规则编辑或持久化功能。

## 展示约定

- 消息内的内容块先识别，再回退到消息容器规则和角色。Claude 用户容器中的 `tool_result` 仍属于工具事件；同一容器的文本仍是用户消息。
- 支持 `message.role`、`info.role` 等嵌套角色、Claude 内容块、opencode parts 和事件子类型。工具内容保留结构化 JSON，便于核对调用 ID 和结果。
- `conversationPaths` 是替代来源，采用首个能生成展示块的数组，不拼接重复的 `conversation` / `messages`。如果某格式应优先使用保留的原始行，将对应路径前移。
- 无法识别的角色作为普通事件放在左侧。没有可展示会话数组时，沿用 `user_input`、`assistant_output` 和工具/错误摘要等已有展示。

复杂格式可扩展 `frontend/src/core/utils/chatRecognition.ts` 中的纯展示函数。配置也可作为 `extractChatBlocks(raw, config)` 的第二个参数传入，便于隔离验证。

## 验证

```bash
cd frontend
npm test
npm run typecheck
npm run lint
npm run build
```

`tests/chat.test.mjs` 覆盖混合用户/工具内容、嵌套角色、事件子类型、未知角色、重复来源、新格式规则和仓库现有样例。样例仅在测试内存中使用，并冻结输入以检查识别过程不修改原数据。每次适配建议加入一条脱敏的错误格式回归用例。
