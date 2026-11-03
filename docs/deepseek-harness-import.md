# DeepSeek Harness session 导入

支持 DeepSeek Harness（dsh）v2、v3、v4 的离线 session 日志：UTF-8 JSONL，以及默认的 `.jsonl.zstd` 压缩文件。Zstandard 文件可包含多个连续帧，按内容识别，无须重命名。输入和解压后的内容分别限制为 64 MiB。

格式依据为官方 [session 事件定义](https://github.com/deepseek-ai/deepseek-harness/blob/8bd073392eef6f54e921a093b95076248eb08cbb/packages/core/session/src/types.ts) 和 [JSONL 存储说明](https://github.com/deepseek-ai/deepseek-harness/blob/8bd073392eef6f54e921a093b95076248eb08cbb/packages/session/session-persistence-jsonl/README.md)。v2/v3 的 `tool-result` 包装会展开为与 v4 相同的工具结果结构。

## 使用

完成 SDK 登录后，通过自动识别或专用命令上传：

```bash
harnessquest auto-upload examples/deepseek-harness-session.v4.jsonl
harnessquest deepseek-upload session.v4.jsonl.zstd
harnessquest deepseek-upload session.v4.jsonl.zstd --json
harnessquest deepseek-upload session.v4.jsonl --case-title '检查工具失败'
```

`--json` 输出 `{"session": {...}, "case": null}`；指定 `--case-title` 时 `case` 为创建的工单对象。网页的会话上传与创建工单入口也接受 `.jsonl` 和 `.zstd` 文件。

Python SDK 可调用 `HarnessQuestClient.upload_deepseek_jsonl(path)` 或已有的 `upload_auto(path)`。文件以原始字节发送，由后端完成解压及解析。

## HTTP API

上传文件使用 multipart 的 `file` 字段；可通过 query 参数 `project_name` 指定项目，默认取 session 头中 `cwd` 的目录名。

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| POST | `/api/v1/sessions/upload/auto` | 自动识别格式并新建会话 |
| PUT | `/api/v1/sessions/upload/auto` | 自动识别并更新已有会话 |
| POST | `/api/v1/sessions/upload/deepseek-jsonl` | 解析 DeepSeek 日志并新建会话 |
| PUT | `/api/v1/sessions/upload/deepseek-jsonl` | 用最新日志更新已有会话 |

沿用现有身份认证和会话去重规则。POST 导入相同 session ID 返回 409，更新请使用 PUT。无效格式、不可读字节、解压错误、超限内容与不支持的版本返回 400。

## 解析结果

转换器产出既有 `SessionImport` 结构，`agent_type` 为 `deepseek_harness`，`source` 为 `deepseek_harness_jsonl_import`。API 返回既有 `SessionRead` 结构，以下解析详情保存在 `metadata_json` 中：

| 字段 | 含义 |
| --- | --- |
| `user_input` / `assistant_output` | 首条真实用户输入、最后一条含文本的助手消息；同一消息的文本块以换行连接 |
| `conversation` | 用户、助手、推理、上下文和工具的可读记录（不再额外写一份 `messages` 别名） |
| `tool_calls` | 按调用顺序保留名称、参数、输出、关联 ID、状态、turn 和 step |
| `shell_commands` | 已返回结果的命令执行记录，含 `exit_code`、`status`（`completed` / `error` / `running` / `timed_out` / `killed` / `stopped`）与输出 |
| `file_edits` | 文件工具返回的变更记录 |
| `errors` | 工具错误与以 error 结束的 turn |
| `deepseek_harness` | 格式版本、模型配置、标题、事件与行计数；完整原始行不在此处 |
| `langfuse_shape` | 与现有导入流程兼容的 trace 和工具 observations |

头部的 `createdAt` 和事件的 `time` 均按 Unix 毫秒转换为 UTC。`source.kind` 为 `user` 的消息用于用户输入搜索；注入的运行时上下文和工具输出不会被当作用户输入。缺少 source 的历史用户消息按用户输入处理。

没有结果的工具调用保留为 `status: "pending"`、`output: null`；仅有结果的记录仍保留输出。未知事件和非文本内容保存在原始行中。

Shell 结果保留 dsh 的终止标记语义：非 0 退出码取 `[exit code: N]`；`[timed out after ...]` 记为 124 / `timed_out`，`[killed by signal: SIGTERM]` 记为 128+信号值 / `killed`；被挂起到后台任务的调用（`[still running ...; moved to background job bash-9]`）记为 `exit_code: null`、`status: "running"` 并附 `background_job`。因此 `exit_code` 可能为 `null`，消费方需要同时看 `status`。

## 存储与资源

完整原始日志（`{"format", "header", "rows"}`）写入会话的 raw artifact（对象存储，`raw_artifact_uri`），`metadata_json` 只保留解析后的视图。这样列表接口不会因为导入大日志而返回整份日志；之前的实现把原始行也放进 `metadata_json`，一次 55 MB 的解压日志会生成约 106 MB 的响应体与约 0.9 GB 的峰值内存。

导入仍是整文件解析：64 MiB 的解压上限约对应 0.9~1 GB 峰值内存，属于单进程内存压力点。输入与解压后各 64 MiB 的限制对自动识别入口的所有格式生效（Claude Code / opencode / HarnessQuest JSON 同样受限）。

Langfuse trace 只接收裁剪后的元数据：`conversation`、`messages`、`raw_rows`、`tool_calls`、`shell_commands`、`file_edits` 以及 `langfuse_shape.observations` 不再发送，替换为 `counts` 计数与 `trimmed_keys` 说明；完整内容仍保留在 HarnessQuest 的元数据与 raw artifact 中。

该导入器提供审计时间线，不执行 dsh 的消息 surface 替换、压缩后重放或运行恢复。

v0/v1 使用历史打包行，须先由 dsh 迁移到 v2/v3/v4 后再导入；未来版本也会明确拒绝，避免静默丢失内容。

## 验证

```bash
uv venv --python 3.12
uv pip install -r backend/requirements.txt -e sdk/python
PYTHONPATH=backend:sdk/python uv run --no-project --python .venv/bin/python python -m pytest backend/tests sdk/python/tests -q
```

测试覆盖消息和工具关联、历史工具包装、错误记录、空会话、未完成调用、毫秒时间、连续压缩帧、大小边界、自动识别及更新、用户输入搜索、SDK 字节上传和 CLI JSON 输出。PostgreSQL 专用搜索测试仍需设置 `HQ_SEARCH_TEST_DATABASE_URL`。
