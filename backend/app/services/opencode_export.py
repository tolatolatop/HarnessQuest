import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def convert_opencode_export_content(
    content: str,
    *,
    source_name: str,
    project_name: str | None = None,
    user_email: str | None = None,
) -> dict[str, Any]:
    payload = _read_json(content)
    session = _session(payload, source_name)
    messages = _messages(payload)
    session_id = _str_or_none(session.get("id")) or Path(source_name).stem
    directory = _str_or_none(session.get("directory"))
    title = _str_or_none(session.get("title")) or "opencode session"
    version = _str_or_none(session.get("version"))
    created_at = _time_value(session.get("time"), "created") or _first_message_time(messages)
    updated_at = _time_value(session.get("time"), "updated") or _last_message_time(messages)

    conversation: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    shell_commands: list[dict[str, Any]] = []
    file_edits: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []

    for item in messages:
        info = _message_info(item)
        parts = _message_parts(item)
        role = _str_or_none(info.get("role")) or "assistant"
        timestamp = _timestamp_from_ms(_time_value(info.get("time"), "created"))
        if not parts:
            text = _str_or_none(info.get("text") or info.get("content"))
            if text:
                conversation.append(_conversation_item(role, label_role(role), text, timestamp, item))
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            _handle_part(part, role, timestamp, item, conversation, tool_calls, shell_commands, file_edits, errors, observations)
        if isinstance(info.get("error"), dict):
            errors.append({"type": "message_error", "level": "ERROR", "message": _stringify(info["error"]), "message_id": info.get("id")})

    user_input = _first_content(conversation, "user")
    assistant_output = _last_content(conversation, "assistant")
    return {
        "external_session_id": session_id,
        "langfuse_session_id": session_id,
        "langfuse_trace_id": f"opencode_{session_id}",
        "agent_type": "opencode",
        "user_email": user_email,
        "project_name": project_name or _project_name(directory),
        "repository": directory,
        "started_at": _timestamp_from_ms(created_at),
        "ended_at": _timestamp_from_ms(updated_at),
        "source": "opencode_export_import",
        "summary": _summary(title, user_input, assistant_output, len(conversation), len(tool_calls)),
        "user_input": user_input,
        "assistant_output": assistant_output,
        "tool_calls": tool_calls,
        "shell_commands": shell_commands,
        "file_edits": file_edits,
        "errors": errors,
        "metadata": {
            "converter": "harnessquest.opencode_export.v1",
            "opencode": {
                "session_id": session_id,
                "directory": directory,
                "version": version,
                "title": title,
                "source_name": source_name,
                "message_count": len(messages),
                "raw": payload,
            },
            "conversation": conversation,
            "messages": conversation,
            "langfuse_shape": {
                "sessionId": session_id,
                "trace": {
                    "id": f"opencode_{session_id}",
                    "name": title,
                    "userId": user_email,
                    "tags": ["opencode", "json-export", "offline-log"],
                    "input": {"prompt": user_input},
                    "output": {"answer": assistant_output},
                    "metadata": {"directory": directory, "version": version, "source_name": source_name},
                },
                "observations": observations,
            },
        },
    }


def _read_json(content: str) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid opencode JSON export: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("opencode export must be a JSON object")
    return data


def _session(payload: dict[str, Any], source_name: str) -> dict[str, Any]:
    for key in ("session", "info"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    value = payload.get("sessions")
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {"id": Path(source_name).stem, "title": Path(source_name).stem}


def _messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("messages", "message", "conversation"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _message_info(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("info")
    return value if isinstance(value, dict) else item


def _message_parts(item: dict[str, Any]) -> list[Any]:
    value = item.get("parts")
    if isinstance(value, list):
        return value
    value = item.get("content")
    return value if isinstance(value, list) else []


def _handle_part(
    part: dict[str, Any],
    role: str,
    timestamp: str | None,
    raw: dict[str, Any],
    conversation: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
    shell_commands: list[dict[str, Any]],
    file_edits: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> None:
    part_type = _str_or_none(part.get("type")) or "unknown"
    if part_type == "text":
        conversation.append(_conversation_item(role, label_role(role), _stringify(part.get("text")), timestamp, raw))
        return
    if part_type == "reasoning":
        conversation.append(_conversation_item("thinking", "Thinking", _stringify(part.get("text")), timestamp, raw))
        return
    if part_type == "file":
        title = _str_or_none(part.get("filename")) or _part_source_path(part) or "file"
        conversation.append(_conversation_item("file", title, _stringify(part), timestamp, raw))
        file_edits.append({"path": title, "change": _stringify(part.get("source") or part)})
        return
    if part_type == "tool":
        _handle_tool_part(part, timestamp, raw, conversation, tool_calls, shell_commands, file_edits, errors, observations)
        return
    if part_type in {"patch", "snapshot"}:
        conversation.append(_conversation_item("file", part_type, _stringify(part), timestamp, raw))
        if part_type == "patch":
            file_edits.append({"path": ", ".join(str(item) for item in part.get("files", [])), "change": _stringify(part)})
        return
    if part_type in {"step-start", "step-finish", "agent", "retry", "compaction", "subtask"}:
        conversation.append(_conversation_item("metadata", part_type, _stringify(part), timestamp, raw))


def _handle_tool_part(
    part: dict[str, Any],
    timestamp: str | None,
    raw: dict[str, Any],
    conversation: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
    shell_commands: list[dict[str, Any]],
    file_edits: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> None:
    state_raw = part.get("state")
    state: dict[str, Any] = state_raw if isinstance(state_raw, dict) else {}
    tool_name = _str_or_none(part.get("tool")) or "tool"
    status = _str_or_none(state.get("status")) or "unknown"
    input_value = state.get("input", {})
    output = _str_or_none(state.get("output")) or _str_or_none(state.get("error")) or _stringify(state)
    title = _str_or_none(state.get("title")) or tool_name
    call = {
        "name": tool_name,
        "input": input_value,
        "output": output,
        "status": status,
        "is_error": status == "error",
        "timestamp": timestamp,
        "tool_call_id": part.get("callID"),
    }
    tool_calls.append(call)
    observations.append({"id": part.get("id") or f"obs_{len(observations) + 1}", "type": "tool", "name": tool_name, "level": "ERROR" if call["is_error"] else "DEFAULT", "input": input_value, "output": output})
    if call["is_error"]:
        errors.append({"type": "tool_error", "level": "ERROR", "message": output, "tool": tool_name})
    role = _tool_role(tool_name, input_value, title)
    conversation.append(_conversation_item(role, title, f"Input:\n{_stringify(input_value)}\n\nOutput:\n{output}", timestamp, raw))
    if role == "shell":
        shell_commands.append({"command": _command_text(input_value), "exit_code": 1 if call["is_error"] else 0, "output": output})
    if role == "file":
        file_edits.append({"path": _input_path(input_value) or title, "change": output})


def _tool_role(tool_name: str, input_value: Any, title: str) -> str:
    normalized = tool_name.lower()
    if normalized in {"bash", "shell", "terminal"} or "bash" in normalized or "shell" in normalized:
        return "shell"
    if normalized in {"edit", "write", "patch"} or any(word in normalized for word in ("edit", "write", "patch")):
        return "file"
    if _input_path(input_value) or title.lower().endswith((".py", ".ts", ".tsx", ".js", ".json", ".md")):
        return "file"
    return "tool"


def label_role(role: str) -> str:
    if role == "user":
        return "用户"
    if role == "assistant":
        return "助手"
    return role


def _summary(title: str, user_input: str | None, assistant_output: str | None, turns: int, tools: int) -> str:
    prompt = user_input or title
    answer = assistant_output or "No final assistant text captured"
    return f"opencode JSON 导入：{prompt}。共解析 {turns} 条对话块、{tools} 次工具调用。最终回复：{answer[:160]}"


def _conversation_item(role: str, title: str, content: str, timestamp: str | None, row: dict[str, Any]) -> dict[str, Any]:
    return {"role": role, "timestamp": timestamp, "title": title, "content": content, "uuid": _message_info(row).get("id")}


def _timestamp_from_ms(value: int | float | None) -> str | None:
    if value is None:
        return None
    if value > 10_000_000_000:
        value = value / 1000
    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def _time_value(value: Any, key: str) -> int | float | None:
    if isinstance(value, dict) and isinstance(value.get(key), int | float):
        return value[key]
    return None


def _first_message_time(messages: list[dict[str, Any]]) -> int | float | None:
    for item in messages:
        value = _time_value(_message_info(item).get("time"), "created")
        if value:
            return value
    return None


def _last_message_time(messages: list[dict[str, Any]]) -> int | float | None:
    for item in reversed(messages):
        value = _time_value(_message_info(item).get("time"), "completed") or _time_value(_message_info(item).get("time"), "created")
        if value:
            return value
    return None


def _first_content(conversation: list[dict[str, Any]], role: str) -> str | None:
    return next((_str_or_none(item.get("content")) for item in conversation if item.get("role") == role), None)


def _last_content(conversation: list[dict[str, Any]], role: str) -> str | None:
    return next((_str_or_none(item.get("content")) for item in reversed(conversation) if item.get("role") == role), None)


def _project_name(directory: str | None) -> str | None:
    return Path(directory).name if directory else None


def _part_source_path(part: dict[str, Any]) -> str | None:
    source = part.get("source")
    if isinstance(source, dict):
        return _str_or_none(source.get("path"))
    return None


def _input_path(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("filePath", "path", "filename"):
            result = _str_or_none(value.get(key))
            if result:
                return result
    return None


def _command_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("command", "cmd"):
            result = _str_or_none(value.get(key))
            if result:
                return result
    return _stringify(value)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def _str_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, int | float):
        return str(value)
    return None
