import json
from pathlib import Path
from typing import Any


def convert_claude_jsonl_content(
    content: str,
    *,
    source_name: str,
    project_name: str | None = None,
    user_email: str | None = None,
) -> dict[str, Any]:
    rows = _read_jsonl(content)
    session_id = _first_str(rows, "sessionId") or Path(source_name).stem
    cwd = _first_str(rows, "cwd")
    git_branch = _last_str(rows, "gitBranch")
    version = _last_str(rows, "version")
    started_at = _first_str(rows, "timestamp")
    ended_at = _last_str(rows, "timestamp")
    last_prompt = _last_prompt(rows)

    tool_uses: dict[str, dict[str, Any]] = {}
    conversation: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    shell_commands: list[dict[str, Any]] = []
    file_edits: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []

    for row in rows:
        row_type = row.get("type")
        timestamp = _str_or_none(row.get("timestamp"))
        uuid = _str_or_none(row.get("uuid") or row.get("messageId"))
        message = row.get("message")
        if row_type == "user" and isinstance(message, dict):
            _handle_user_row(row, message, timestamp, conversation, tool_uses, tool_calls, shell_commands, file_edits, errors, observations)
        elif row_type == "assistant" and isinstance(message, dict):
            _handle_assistant_row(row, message, timestamp, conversation, tool_uses, observations)
        elif row_type in {"system", "attachment", "file-history-snapshot", "mode", "permission-mode", "last-prompt"}:
            observations.append(
                {
                    "id": uuid or f"obs_{len(observations) + 1}",
                    "type": "span",
                    "name": str(row_type),
                    "level": "DEFAULT",
                    "input": {key: value for key, value in row.items() if key not in {"message", "toolUseResult", "attachment", "snapshot"}},
                    "output": {},
                }
            )

    user_input = _first_content(conversation, "user")
    assistant_output = _last_content(conversation, "assistant")
    summary = _summary(last_prompt, user_input, assistant_output, len(conversation), len(tool_calls))
    return {
        "external_session_id": session_id,
        "langfuse_session_id": session_id,
        "langfuse_trace_id": f"claude_{session_id}",
        "agent_type": "claude_code",
        "user_email": user_email,
        "project_name": project_name or (Path(cwd).name if cwd else None),
        "repository": cwd,
        "branch": git_branch,
        "started_at": started_at,
        "ended_at": ended_at,
        "source": "claude_jsonl_import",
        "summary": summary,
        "user_input": user_input,
        "assistant_output": assistant_output,
        "tool_calls": tool_calls,
        "shell_commands": shell_commands,
        "file_edits": file_edits,
        "errors": errors,
        "metadata": {
            "converter": "harnessquest.claude_jsonl.v1",
            "claude": {
                "session_id": session_id,
                "cwd": cwd,
                "version": version,
                "last_prompt": last_prompt,
                "source_name": source_name,
                "row_count": len(rows),
                "raw_rows": rows,
            },
            "conversation": conversation,
            "messages": conversation,
            "langfuse_shape": {
                "sessionId": session_id,
                "trace": {
                    "id": f"claude_{session_id}",
                    "name": last_prompt or "claude-code-session",
                    "userId": user_email,
                    "tags": ["claude-code", "jsonl-import", "offline-log"],
                    "input": {"prompt": user_input},
                    "output": {"answer": assistant_output},
                    "metadata": {"cwd": cwd, "gitBranch": git_branch, "version": version, "source_name": source_name},
                },
                "observations": observations,
            },
        },
    }


def _read_jsonl(content: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Claude JSONL at line {line_number}: {exc}") from exc
        if isinstance(row, dict):
            rows.append(row)
    if not rows:
        raise ValueError("Claude JSONL file is empty")
    return rows


def _handle_user_row(
    row: dict[str, Any],
    message: dict[str, Any],
    timestamp: str | None,
    conversation: list[dict[str, Any]],
    tool_uses: dict[str, dict[str, Any]],
    tool_calls: list[dict[str, Any]],
    shell_commands: list[dict[str, Any]],
    file_edits: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> None:
    content = message.get("content")
    if isinstance(content, str):
        conversation.append(_conversation_item("user", "用户", content, timestamp, row))
        return
    if not isinstance(content, list):
        return
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "tool_result":
            continue
        tool_use_id = _str_or_none(item.get("tool_use_id"))
        tool = tool_uses.get(tool_use_id or "", {})
        tool_name = str(tool.get("name") or "tool_result")
        output = _stringify(item.get("content"))
        call = {"name": tool_name, "input": tool.get("input", {}), "output": output, "is_error": bool(item.get("is_error")), "timestamp": timestamp, "tool_use_id": tool_use_id}
        tool_calls.append(call)
        observations.append({"id": row.get("uuid") or f"obs_{len(observations) + 1}", "type": "tool", "name": tool_name, "level": "ERROR" if call["is_error"] else "DEFAULT", "input": call["input"], "output": output})
        _classify_tool_result(tool_name, call, row.get("toolUseResult"), output, shell_commands, file_edits, errors)
        conversation.append(_tool_conversation_item(tool_name, call, output, timestamp, row))


def _handle_assistant_row(row: dict[str, Any], message: dict[str, Any], timestamp: str | None, conversation: list[dict[str, Any]], tool_uses: dict[str, dict[str, Any]], observations: list[dict[str, Any]]) -> None:
    content = message.get("content")
    if isinstance(content, str):
        conversation.append(_conversation_item("assistant", "助手", content, timestamp, row))
        return
    if not isinstance(content, list):
        return
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            conversation.append(_conversation_item("assistant", "助手", _stringify(item.get("text")), timestamp, row))
        elif item.get("type") == "thinking":
            conversation.append(_conversation_item("thinking", "Thinking", _stringify(item.get("thinking")), timestamp, row))
        elif item.get("type") == "tool_use":
            tool_id = _str_or_none(item.get("id"))
            tool_uses[tool_id or ""] = {"name": item.get("name"), "input": item.get("input", {}), "timestamp": timestamp}
            observations.append({"id": row.get("uuid") or tool_id or f"obs_{len(observations) + 1}", "type": "tool", "name": item.get("name") or "tool_use", "level": "DEFAULT", "input": item.get("input", {}), "output": {"tool_use_id": tool_id}})


def _classify_tool_result(tool_name: str, call: dict[str, Any], result: Any, output: str, shell_commands: list[dict[str, Any]], file_edits: list[dict[str, Any]], errors: list[dict[str, Any]]) -> None:
    if call.get("is_error"):
        errors.append({"type": "tool_error", "level": "ERROR", "message": output, "tool": tool_name})
    if tool_name == "Bash":
        input_value = call.get("input")
        command = input_value.get("command") if isinstance(input_value, dict) else None
        shell_commands.append({"command": command or "", "exit_code": 1 if call.get("is_error") else 0, "output": output})
    elif tool_name in {"Edit", "Write", "MultiEdit"}:
        result_obj = result if isinstance(result, dict) else {}
        file_edits.append({"path": result_obj.get("filePath") or _input_path(call.get("input")), "change": result_obj.get("structuredPatch") or output})


def _tool_conversation_item(tool_name: str, call: dict[str, Any], output: str, timestamp: str | None, row: dict[str, Any]) -> dict[str, Any]:
    input_value = call.get("input")
    role = "tool"
    title = tool_name
    if tool_name == "Bash":
        role = "shell"
        if isinstance(input_value, dict):
            title = _str_or_none(input_value.get("description")) or _str_or_none(input_value.get("command")) or tool_name
    elif tool_name in {"Edit", "Write", "MultiEdit"}:
        role = "file"
        title = _input_path(input_value) or tool_name
    elif tool_name == "Read":
        title = _input_path(input_value) or tool_name
    return _conversation_item(role, title, f"Input:\n{_stringify(input_value)}\n\nOutput:\n{output}", timestamp, row)


def _conversation_item(role: str, title: str, content: str, timestamp: str | None, row: dict[str, Any]) -> dict[str, Any]:
    return {"role": role, "timestamp": timestamp, "title": title, "content": content, "uuid": row.get("uuid")}


def _summary(last_prompt: str | None, user_input: str | None, assistant_output: str | None, turns: int, tools: int) -> str:
    prompt = last_prompt or user_input or "Claude Code session"
    answer = assistant_output or "No final assistant text captured"
    return f"Claude Code JSONL 导入：{prompt}。共解析 {turns} 条对话主线、{tools} 次工具结果。最终回复：{answer[:160]}"


def _first_content(conversation: list[dict[str, Any]], role: str) -> str | None:
    return next((_str_or_none(item.get("content")) for item in conversation if item.get("role") == role), None)


def _last_content(conversation: list[dict[str, Any]], role: str) -> str | None:
    return next((_str_or_none(item.get("content")) for item in reversed(conversation) if item.get("role") == role), None)


def _first_str(rows: list[dict[str, Any]], key: str) -> str | None:
    return next((_str_or_none(row.get(key)) for row in rows if _str_or_none(row.get(key))), None)


def _last_str(rows: list[dict[str, Any]], key: str) -> str | None:
    return next((_str_or_none(row.get(key)) for row in reversed(rows) if _str_or_none(row.get(key))), None)


def _last_prompt(rows: list[dict[str, Any]]) -> str | None:
    return next((_str_or_none(row.get("lastPrompt")) for row in reversed(rows) if _str_or_none(row.get("lastPrompt"))), None)


def _input_path(input_value: Any) -> str | None:
    if isinstance(input_value, dict):
        for key in ("file_path", "filePath", "path"):
            value = _str_or_none(input_value.get(key))
            if value:
                return value
    return None


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)
