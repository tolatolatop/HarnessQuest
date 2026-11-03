"""DeepSeek Harness (dsh) session-log import.

A DeepSeek Harness session is one append-only log: a ``{"type": "session", ...}``
header line followed by event rows carrying ``{type, seq, time, data}``
envelopes. Uncompressed logs (``compression: 'none'``) are plain UTF-8 JSONL;
the default artifact is a concatenation of Zstandard frames, one frame per
durable append batch. Both encodings are accepted here.

Event payloads follow the harness ``SessionEventMap``: ``user/message``,
``assistant/message``, ``tool/call``, ``tool/result``, ``turn/start`` /
``turn/end``, ``session/title`` and request metadata. User messages carry a
``source.kind`` — ``user`` for a real prompt, other kinds for injected context
(runtime snapshot, relayed agent message, notices) that must not become the
session's user input.

Shell results keep dsh's terminal markers instead of flattening them to 0/1:
``exit_code`` is absent for commands that timed out, were killed, stopped, or
were promoted to a background job, and ``status`` says which. The complete log
travels in ``raw`` (stored as the session's raw artifact) rather than inside
``metadata``, which is returned by the list API.
"""

import io
import json
import re
import signal
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import zstandard

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
# Exact tool names only: substring matching would file `todo_write` under file edits.
SHELL_TOOLS = frozenset({"bash", "shell", "sh", "terminal", "pwsh", "powershell"})
FILE_TOOLS = frozenset({"write", "edit", "apply_patch", "str_replace_editor", "notebook_edit"})
EXIT_CODE_PATTERN = re.compile(r"\[exit code: (-?\d+)\]")
# The shell tools append at most one terminal-status marker after the output.
SIGNAL_PATTERN = re.compile(r"\[killed by signal: ([A-Za-z0-9_]+)\]")
TIMEOUT_PATTERN = re.compile(r"\[timed out after \d+ms\]")
STOPPED_PATTERN = re.compile(r"\[stopped: [^\]]*\]")
BACKGROUND_PATTERN = re.compile(r"\[still running after \d+ms; moved to background job ([^\]]+)\]")
SUPPORTED_VERSIONS = frozenset({2, 3, 4})
MAX_LOG_BYTES = 64 * 1024 * 1024


def decode_harness_log(content: bytes) -> str:
    """Decode a raw DSH session artifact into its JSONL text form."""
    if len(content) > MAX_LOG_BYTES:
        raise ValueError("Session log exceeds the 64 MiB import limit")
    if content.startswith(ZSTD_MAGIC):
        return _decompress_zstd(content)
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("DeepSeek Harness session log is not UTF-8 JSONL or Zstandard") from exc


def _decompress_zstd(content: bytes) -> str:
    reader = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(content), read_across_frames=True)
    try:
        text = reader.read(MAX_LOG_BYTES + 1)
    except zstandard.ZstdError as exc:
        raise ValueError(f"Invalid Zstandard DeepSeek Harness session log: {exc}") from exc
    finally:
        reader.close()
    if len(text) > MAX_LOG_BYTES:
        raise ValueError("Decompressed session log exceeds the 64 MiB import limit")
    try:
        return text.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Decompressed DeepSeek Harness session log is not UTF-8") from exc


def looks_like_harness_log(content: str) -> bool:
    """Return True when the text starts with a DeepSeek Harness session header.

    A DSH log is one JSONL file whose first record is the ``type: "session"``
    header with an integer ``version``/``createdAt`` and a string ``id``.
    """
    for line in content.splitlines():
        if not line.strip():
            continue
        try:
            header = json.loads(line)
        except json.JSONDecodeError:
            return False
        if not isinstance(header, dict):
            return False
        return (
            header.get("type") == "session"
            and type(header.get("version")) is int
            and type(header.get("createdAt")) is int
            and isinstance(header.get("id"), str)
            and bool(header["id"].strip())
        )
    return False


def convert_deepseek_harness_content(
    content: str,
    *,
    source_name: str,
    project_name: str | None = None,
    user_email: str | None = None,
) -> dict[str, Any]:
    rows = _read_jsonl(content)
    header = _header(rows)
    events = [row for row in rows[1:] if isinstance(row.get("data"), dict)]
    session_id = header["id"]
    cwd = _str_or_none(header.get("cwd"))
    title = _last_title(events) or "DeepSeek Harness session"
    config = _last_request_config(events)
    started_at = _timestamp_from_ms(header.get("createdAt"))
    ended_at = _last_event_time(events) or started_at

    state = _ParseState()
    for row in events:
        _apply_event(state, row)

    user_input = _first_content(state.conversation, "user")
    assistant_output = _last_content(state.conversation, "assistant")
    return {
        "external_session_id": session_id,
        "langfuse_session_id": session_id,
        "langfuse_trace_id": f"deepseek_{session_id}",
        "agent_type": "deepseek_harness",
        "user_email": user_email,
        "project_name": project_name or (Path(cwd).name if cwd else None),
        "repository": cwd,
        "started_at": started_at,
        "ended_at": ended_at,
        "source": "deepseek_harness_jsonl_import",
        "summary": _summary(title, user_input, assistant_output, len(state.conversation), len(state.tool_calls)),
        "user_input": user_input,
        "assistant_output": assistant_output,
        "tool_calls": state.tool_calls,
        "shell_commands": state.shell_commands,
        "file_edits": state.file_edits,
        "errors": state.errors,
        # The raw artifact keeps the complete log; metadata keeps parsed views only, so
        # storage, list responses and Langfuse never carry the log twice.
        "raw": {"format": "deepseek_harness_jsonl", "header": header, "rows": rows},
        "metadata": {
            "converter": "harnessquest.deepseek_harness.v1",
            "deepseek_harness": {
                "session_id": session_id,
                "format_version": header.get("version"),
                "cwd": cwd,
                "title": title,
                "agent_preset": _str_or_none(header.get("agentPreset")),
                "parent_session": _str_or_none(header.get("parentSession")),
                "origin": _str_or_none(header.get("origin")),
                "provider": _str_or_none(config.get("provider")),
                "model": _str_or_none(config.get("model")),
                "source_name": source_name,
                "event_count": len(events),
                "row_count": len(rows),
                "turns": state.turns,
            },
            "conversation": state.conversation,
            "langfuse_shape": {
                "sessionId": session_id,
                "trace": {
                    "id": f"deepseek_{session_id}",
                    "name": title,
                    "userId": user_email,
                    "tags": ["deepseek-harness", "jsonl-import", "offline-log"],
                    "input": {"prompt": user_input},
                    "output": {"answer": assistant_output},
                    "metadata": {"cwd": cwd, "model": config.get("model"), "source_name": source_name},
                },
                "observations": state.observations,
            },
        },
    }


@dataclass
class _ParseState:
    conversation: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    shell_commands: list[dict[str, Any]] = field(default_factory=list)
    file_edits: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    turns: list[dict[str, Any]] = field(default_factory=list)
    pending_calls: dict[str, dict[str, Any]] = field(default_factory=dict)


def _apply_event(state: _ParseState, row: dict[str, Any]) -> None:
    event_type = _str_or_none(row.get("type")) or ""
    data = row.get("data")
    if not isinstance(data, dict):
        return
    timestamp = _timestamp_from_ms(row.get("time"))
    if event_type == "user/message":
        _handle_user_message(state, data, timestamp, row)
    elif event_type == "assistant/message":
        _handle_assistant_message(state, data, timestamp, row)
    elif event_type == "tool/call":
        _handle_tool_call(state, data, timestamp, row)
    elif event_type == "tool/result":
        _handle_tool_result(state, data, timestamp, row)
    elif event_type == "turn/end":
        _handle_turn_end(state, data)


def _handle_user_message(state: _ParseState, data: dict[str, Any], timestamp: str | None, row: dict[str, Any]) -> None:
    text = _blocks_text(data.get("content"))
    if not text.strip():
        return
    source = data.get("source")
    kind = _str_or_none(source.get("kind")) if isinstance(source, dict) else None
    if kind in {None, "user"}:
        state.conversation.append(_conversation_item("user", "用户", text, timestamp, row))
        return
    # Injected context (runtime snapshot, relay, notice) is shown but never user input.
    state.conversation.append(_conversation_item("context", f"上下文 ({kind})", text, timestamp, row))


def _handle_assistant_message(
    state: _ParseState, data: dict[str, Any], timestamp: str | None, row: dict[str, Any]
) -> None:
    message = data.get("message")
    if not isinstance(message, dict):
        return
    blocks = message.get("content")
    if not isinstance(blocks, list):
        return
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "reasoning":
            state.conversation.append(
                _conversation_item("thinking", "Thinking", _stringify(block.get("text")), timestamp, row)
            )
    text = _blocks_text(blocks)
    if text.strip():
        state.conversation.append(_conversation_item("assistant", "助手", text, timestamp, row))


def _handle_tool_call(state: _ParseState, data: dict[str, Any], timestamp: str | None, row: dict[str, Any]) -> None:
    call_id = _str_or_none(data.get("callId")) or f"call_{row.get('seq')}"
    call: dict[str, Any] = {
        "name": _str_or_none(data.get("name")) or "tool",
        "input": _parse_arguments(data.get("arguments")),
        "output": None,
        "status": "pending",
        "is_error": False,
        "timestamp": timestamp,
        "tool_call_id": call_id,
        "turn": data.get("turn"),
        "step": data.get("step"),
    }
    state.tool_calls.append(call)
    role = _tool_role(call["name"])
    conversation = _tool_conversation_item(call["name"], role, call, timestamp, row)
    state.conversation.append(conversation)
    state.pending_calls[call_id] = {"call": call, "conversation": conversation}


def _handle_tool_result(state: _ParseState, data: dict[str, Any], timestamp: str | None, row: dict[str, Any]) -> None:
    message = _tool_result_message(data)
    call_id = _str_or_none(message.get("toolCallId")) or _str_or_none(data.get("callId"))
    pending = state.pending_calls.pop(call_id or "", {})
    call = pending.get("call")
    if call is None:
        call = {
            "name": "tool",
            "input": {},
            "tool_call_id": call_id,
            "turn": data.get("turn"),
            "step": data.get("step"),
        }
        state.tool_calls.append(call)
    name = call["name"]
    input_value = call["input"]
    output = _blocks_text(message.get("content"))
    is_error = message.get("isError") is True
    timestamp = timestamp or call.get("timestamp")
    call.update(
        {
            "output": output,
            "status": "error" if is_error else "completed",
            "is_error": is_error,
            "timestamp": timestamp,
        }
    )
    state.observations.append(
        {
            "id": call_id or f"obs_{len(state.observations) + 1}",
            "type": "tool",
            "name": name,
            "level": "ERROR" if is_error else "DEFAULT",
            "input": input_value,
            "output": output,
        }
    )
    _record_error(state, data, name, output, call_id, is_error)
    role = _tool_role(name)
    item = _tool_conversation_item(name, role, call, timestamp, row)
    if pending:
        pending["conversation"].update(item)
    else:
        state.conversation.append(item)
    if role == "shell":
        exit_code, status, background_job = _shell_result(output, is_error)
        command: dict[str, Any] = {
            "command": _command_text(input_value),
            "exit_code": exit_code,
            "status": status,
            "output": output,
        }
        if background_job:
            command["background_job"] = background_job
        state.shell_commands.append(command)
    if role == "file":
        state.file_edits.extend(_file_edits(data.get("meta"), input_value, output))


def _tool_result_message(data: dict[str, Any]) -> dict[str, Any]:
    """Unwrap v2/v3 user-role tool results; v4 uses a native tool message."""
    message = data.get("message")
    if not isinstance(message, dict):
        return {}
    content = message.get("content")
    if message.get("role") == "user" and isinstance(content, list):
        wrappers = [item for item in content if isinstance(item, dict) and item.get("type") == "tool-result"]
        if len(wrappers) == 1:
            return wrappers[0]
    return message


def _record_error(
    state: _ParseState,
    data: dict[str, Any],
    name: str,
    output: str,
    call_id: str | None,
    is_error: bool,
) -> None:
    error = data.get("error")
    error = error if isinstance(error, dict) else {}
    if not error and not is_error:
        return
    state.errors.append(
        {
            "type": "tool_error",
            "level": "ERROR",
            "message": _str_or_none(error.get("reason")) or output,
            "tool": name,
            "code": _str_or_none(error.get("code")),
            "name": _str_or_none(error.get("name")),
            "tool_call_id": call_id,
        }
    )


def _handle_turn_end(state: _ParseState, data: dict[str, Any]) -> None:
    reason = data.get("reason")
    reason = reason if isinstance(reason, dict) else {}
    kind = _str_or_none(reason.get("kind")) or "unknown"
    state.turns.append({"turn": data.get("turn"), "reason": kind})
    if kind != "error":
        return
    failure = reason.get("error")
    failure = failure if isinstance(failure, dict) else {}
    state.errors.append(
        {
            "type": "turn_error",
            "level": "ERROR",
            "message": _str_or_none(failure.get("message")) or _stringify(failure) or "Turn failed",
            "code": _str_or_none(failure.get("code")),
            "name": _str_or_none(failure.get("name")),
            "turn": data.get("turn"),
        }
    )


def _tool_role(name: str) -> str:
    normalized = name.strip().lower()
    if normalized in SHELL_TOOLS:
        return "shell"
    if normalized in FILE_TOOLS:
        return "file"
    return "tool"


def _tool_conversation_item(
    name: str,
    role: str,
    call: dict[str, Any],
    timestamp: str | None,
    row: dict[str, Any],
) -> dict[str, Any]:
    title = name
    if role == "shell":
        title = _shell_title(call.get("input")) or name
    elif role == "file":
        title = _input_path(call.get("input")) or name
    output = call.get("output") if call.get("status") != "pending" else "Pending (no result recorded)"
    content = f"Input:\n{_stringify(call.get('input'))}\n\nOutput:\n{output}"
    return _conversation_item(role, title, content, timestamp, row)


def _shell_title(input_value: Any) -> str | None:
    if isinstance(input_value, dict):
        return _str_or_none(input_value.get("description")) or _str_or_none(input_value.get("command"))
    return None


def _file_edits(meta: Any, input_value: Any, output: str) -> list[dict[str, Any]]:
    meta = meta if isinstance(meta, dict) else {}
    diffs = meta.get("diffs")
    if isinstance(diffs, list) and diffs:
        return [
            {"path": _str_or_none(diff.get("path")) or "unknown", "change": _stringify(diff)}
            for diff in diffs
            if isinstance(diff, dict)
        ]
    path = _str_or_none(meta.get("path")) or _input_path(input_value)
    if not path:
        return []
    return [{"path": path, "change": output}]


def _read_jsonl(content: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid DeepSeek Harness JSONL at line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"DeepSeek Harness JSONL line {line_number} is not a JSON object")
        rows.append(row)
    if not rows:
        raise ValueError("DeepSeek Harness session log is empty")
    return rows


def _header(rows: list[dict[str, Any]]) -> dict[str, Any]:
    header = rows[0]
    if header.get("type") != "session":
        raise ValueError("DeepSeek Harness session log does not start with a session header")
    if type(header.get("version")) is not int:
        raise ValueError("DeepSeek Harness session header has no integer version")
    if header["version"] not in SUPPORTED_VERSIONS:
        raise ValueError(
            "Unsupported DeepSeek Harness version; use a v2, v3 or v4 session log (migrate v0/v1 with dsh)"
        )
    if not isinstance(header.get("id"), str) or not header["id"].strip():
        raise ValueError("DeepSeek Harness session header has no id")
    if type(header.get("createdAt")) is not int:
        raise ValueError("DeepSeek Harness session header has no createdAt")
    return header


def _last_title(events: list[dict[str, Any]]) -> str | None:
    for row in reversed(events):
        if row.get("type") != "session/title":
            continue
        data = row.get("data")
        title = _str_or_none(data.get("title")) if isinstance(data, dict) else None
        if title:
            return title
    return None


def _last_request_config(events: list[dict[str, Any]]) -> dict[str, Any]:
    for row in reversed(events):
        if row.get("type") != "request/header":
            continue
        data = row.get("data")
        header = data.get("header") if isinstance(data, dict) else None
        config = header.get("config") if isinstance(header, dict) else None
        if isinstance(config, dict):
            return config
    return {}


def _last_event_time(events: list[dict[str, Any]]) -> str | None:
    for row in reversed(events):
        timestamp = _timestamp_from_ms(row.get("time"))
        if timestamp:
            return timestamp
    return None


def _blocks_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    texts = [
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    ]
    return "\n".join(texts)


def _parse_arguments(value: Any) -> Any:
    if isinstance(value, dict | list):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}
    return parsed


def _shell_result(output: str, is_error: bool) -> tuple[int | None, str, str | None]:
    """Recover the exit status dsh renders into the tool result.

    ``dsh-tool-bash`` appends at most one terminal marker: a timeout, a kill
    signal, a human stop, or a non-zero exit code. Promoted commands instead end
    with a background-job marker, and those have no exit status yet.
    """
    if TIMEOUT_PATTERN.search(output):
        return 124, "timed_out", None
    signal_name = SIGNAL_PATTERN.findall(output)
    if signal_name:
        return _signal_exit_code(signal_name[-1]), "killed", None
    if STOPPED_PATTERN.search(output):
        return None, "stopped", None
    background = BACKGROUND_PATTERN.findall(output)
    if background:
        return None, "running", background[-1].strip() or None
    matches = EXIT_CODE_PATTERN.findall(output)
    if matches:
        return int(matches[-1]), "completed", None
    return (1 if is_error else 0), ("error" if is_error else "completed"), None


def _signal_exit_code(name: str) -> int | None:
    try:
        return 128 + int(signal.Signals[name.upper()])
    except (KeyError, ValueError):
        return None


def _input_path(input_value: Any) -> str | None:
    if isinstance(input_value, dict):
        for key in ("path", "file_path", "filePath", "filename"):
            value = _str_or_none(input_value.get(key))
            if value:
                return value
    return None


def _command_text(input_value: Any) -> str:
    if isinstance(input_value, dict):
        for key in ("command", "cmd"):
            value = _str_or_none(input_value.get(key))
            if value:
                return value
    return _stringify(input_value)


def _conversation_item(
    role: str, title: str, content: str, timestamp: str | None, row: dict[str, Any]
) -> dict[str, Any]:
    return {"role": role, "timestamp": timestamp, "title": title, "content": content, "uuid": row.get("seq")}


def _summary(title: str, user_input: str | None, assistant_output: str | None, turns: int, tools: int) -> str:
    prompt = user_input or title
    answer = assistant_output or "No final assistant text captured"
    return f"DeepSeek Harness 会话导入: {prompt}。共解析 {turns} 条对话块、{tools} 次工具调用。最终回复: {answer[:160]}"


def _first_content(conversation: list[dict[str, Any]], role: str) -> str | None:
    return next((_str_or_none(item.get("content")) for item in conversation if item.get("role") == role), None)


def _last_content(conversation: list[dict[str, Any]], role: str) -> str | None:
    return next(
        (_str_or_none(item.get("content")) for item in reversed(conversation) if item.get("role") == role), None
    )


def _timestamp_from_ms(value: Any) -> str | None:
    if type(value) not in {int, float}:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("DeepSeek Harness timestamp is outside the supported range") from exc


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
