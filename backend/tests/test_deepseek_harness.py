import json
from pathlib import Path
from typing import Any

import pytest
import zstandard
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Project, User
from app.routes import sessions as session_routes
from app.services import deepseek_harness
from app.services.deepseek_harness import (
    convert_deepseek_harness_content,
    decode_harness_log,
    looks_like_harness_log,
)

BASE = "/api/v1/sessions"
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
SESSION_ID = "dsh-session-1"
CWD = "/home/dev/workspace/harness-demo"
PROMPT = "修复登录接口的 500 错误"
FORMAT_VERSION = 4
FULL_LOG_ROWS = 11


class _FakeStorage:
    def put_json(self, prefix: str, payload: dict[str, Any]) -> str:
        return f"memory://{prefix}/{payload.get('external_session_id', 'session')}.json"


async def _fake_write_langfuse_trace(payload: Any) -> tuple[str | None, str | None, str | None]:
    return payload.langfuse_session_id, payload.langfuse_trace_id, payload.langfuse_url


@pytest.fixture(autouse=True)
def _patch_session_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_routes, "ObjectStorage", lambda: _FakeStorage())
    monkeypatch.setattr(session_routes, "write_langfuse_trace", _fake_write_langfuse_trace)


def _header(**overrides: Any) -> dict[str, Any]:
    header: dict[str, Any] = {
        "type": "session",
        "version": FORMAT_VERSION,
        "id": SESSION_ID,
        "createdAt": 1_760_000_000_000,
        "cwd": CWD,
        "isSeeded": False,
        "delegationDepth": 0,
        "agentPreset": "standard",
    }
    header.update(overrides)
    return header


def _user_message(text: str, *, seq: int, time: int, kind: str = "user") -> dict[str, Any]:
    return {
        "type": "user/message",
        "seq": seq,
        "time": time,
        "surfaceOp": "append",
        "data": {
            "role": "user",
            "id": f"msg-{seq}",
            "source": {"kind": kind},
            "content": [{"type": "text", "text": text}],
        },
    }


def _assistant_message(blocks: list[dict[str, Any]], *, seq: int, time: int) -> dict[str, Any]:
    return {
        "type": "assistant/message",
        "seq": seq,
        "time": time,
        "surfaceOp": "append",
        "data": {
            "turn": 1,
            "step": 1,
            "message": {
                "role": "assistant",
                "id": f"msg-{seq}",
                "source": {"kind": "model", "provider": "deepseek", "model": "deepseek-chat"},
                "content": blocks,
            },
        },
    }


def _tool_call(name: str, arguments: dict[str, Any], call_id: str, *, seq: int, time: int) -> dict[str, Any]:
    return {
        "type": "tool/call",
        "seq": seq,
        "time": time,
        "data": {"turn": 1, "step": 1, "callId": call_id, "name": name, "arguments": json.dumps(arguments)},
    }


def _tool_result(
    text: str, call_id: str, *, seq: int, time: int, is_error: bool = False, meta: Any = None
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "turn": 1,
        "step": 1,
        "message": {
            "role": "tool",
            "id": f"msg-{seq}",
            "source": {"kind": "tool", "callId": call_id},
            "toolCallId": call_id,
            "isError": is_error,
            "content": [{"type": "text", "text": text}],
        },
    }
    if meta is not None:
        data["meta"] = meta
    return {"type": "tool/result", "seq": seq, "time": time, "surfaceOp": "append", "data": data}


def _log(*rows: dict[str, Any]) -> str:
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"


def _full_log() -> str:
    return _log(
        _header(),
        {"type": "turn/start", "seq": 1, "time": 1_760_000_001_000, "data": {"turn": 1}},
        _user_message("runtime context snapshot", seq=2, time=1_760_000_001_100, kind="runtime-context"),
        {
            "type": "user/message",
            "seq": 3,
            "time": 1_760_000_001_200,
            "surfaceOp": "append",
            "data": {
                "role": "user",
                "id": "msg-3",
                "source": {"kind": "user"},
                "content": [{"type": "text", "text": PROMPT}, {"type": "text", "text": "补充: 只改后端"}],
            },
        },
        {"type": "session/title", "seq": 4, "time": 1_760_000_001_300, "data": {"title": "修复登录 500"}},
        {
            "type": "request/header",
            "seq": 5,
            "time": 1_760_000_001_400,
            "data": {"header": {"config": {"provider": "deepseek", "model": "deepseek-chat"}}, "reason": "initial"},
        },
        _assistant_message(
            [
                {"type": "reasoning", "text": "先看日志"},
                {
                    "type": "tool-call",
                    "id": "call-1",
                    "name": "bash",
                    "arguments": json.dumps({"command": "pytest -q", "description": "运行测试"}),
                },
            ],
            seq=6,
            time=1_760_000_001_500,
        ),
        _tool_call(
            "bash", {"command": "pytest -q", "description": "运行测试"}, "call-1", seq=7, time=1_760_000_001_600
        ),
        _tool_result("2 failed\n[exit code: 2]", "call-1", seq=8, time=1_760_000_001_700),
        _assistant_message([{"type": "text", "text": "已定位到空指针"}], seq=9, time=1_760_000_001_800),
        {
            "type": "turn/end",
            "seq": 10,
            "time": 1_760_000_001_900,
            "data": {"turn": 1, "reason": {"kind": "completed"}},
        },
    )


def test_converts_messages_tools_and_metadata() -> None:
    payload = convert_deepseek_harness_content(_full_log(), source_name="session.v4.jsonl")

    assert payload["external_session_id"] == SESSION_ID
    assert payload["agent_type"] == "deepseek_harness"
    assert payload["source"] == "deepseek_harness_jsonl_import"
    assert payload["repository"] == CWD
    assert payload["project_name"] == "harness-demo"
    assert payload["started_at"] == "2025-10-09T08:53:20+00:00"
    assert payload["ended_at"] == "2025-10-09T08:53:21.900000+00:00"
    # Only the source.kind == "user" prompt counts, with its text blocks joined.
    assert payload["user_input"] == f"{PROMPT}\n补充: 只改后端"
    assert payload["assistant_output"] == "已定位到空指针"
    roles = [item["role"] for item in payload["metadata"]["conversation"]]
    assert roles == ["context", "user", "thinking", "shell", "assistant"]
    assert payload["tool_calls"][0]["name"] == "bash"
    assert payload["tool_calls"][0]["input"] == {"command": "pytest -q", "description": "运行测试"}
    assert payload["tool_calls"][0]["tool_call_id"] == "call-1"
    assert payload["shell_commands"] == [{"command": "pytest -q", "exit_code": 2, "output": "2 failed\n[exit code: 2]"}]
    assert payload["errors"] == []
    deepseek = payload["metadata"]["deepseek_harness"]
    assert deepseek["format_version"] == FORMAT_VERSION
    assert deepseek["title"] == "修复登录 500"
    assert deepseek["provider"] == "deepseek"
    assert deepseek["model"] == "deepseek-chat"
    assert deepseek["turns"] == [{"turn": 1, "reason": "completed"}]
    assert deepseek["row_count"] == FULL_LOG_ROWS


def test_records_file_edits_tool_errors_and_turn_failures() -> None:
    log = _log(
        _header(),
        _user_message(PROMPT, seq=1, time=1_760_000_001_000),
        _tool_call("write", {"path": "src/app.py", "content": "print(1)"}, "call-write", seq=2, time=1_760_000_001_100),
        _tool_result(
            "wrote src/app.py",
            "call-write",
            seq=3,
            time=1_760_000_001_200,
            meta={
                "path": "src/app.py",
                "operation": "create",
                "diffs": [{"path": "src/app.py", "oldText": None, "newText": "print(1)"}],
            },
        ),
        _tool_call("read", {"path": "src/missing.py"}, "call-read", seq=4, time=1_760_000_001_300),
        {
            "type": "tool/result",
            "seq": 5,
            "time": 1_760_000_001_400,
            "surfaceOp": "append",
            "data": {
                "turn": 1,
                "step": 1,
                "message": {
                    "role": "tool",
                    "id": "msg-5",
                    "source": {"kind": "tool", "callId": "call-read"},
                    "toolCallId": "call-read",
                    "isError": True,
                    "content": [{"type": "text", "text": "ENOENT"}],
                },
                "error": {"name": "ToolError", "code": "ENOENT", "reason": "File not found"},
            },
        },
        {
            "type": "turn/end",
            "seq": 6,
            "time": 1_760_000_001_500,
            "data": {
                "turn": 1,
                "reason": {"kind": "error", "error": {"name": "LlmError", "code": "RATE_LIMIT", "message": "429"}},
            },
        },
    )
    payload = convert_deepseek_harness_content(log, source_name="session.jsonl")

    assert payload["file_edits"] == [
        {"path": "src/app.py", "change": payload["file_edits"][0]["change"]},
    ]
    assert "print(1)" in payload["file_edits"][0]["change"]
    assert payload["shell_commands"] == []
    assert [error["type"] for error in payload["errors"]] == ["tool_error", "turn_error"]
    assert payload["errors"][0]["message"] == "File not found"
    assert payload["errors"][0]["code"] == "ENOENT"
    assert payload["errors"][1]["message"] == "429"
    assert payload["errors"][1]["turn"] == 1


def test_header_only_log_is_accepted() -> None:
    payload = convert_deepseek_harness_content(_log(_header()), source_name="session.jsonl")

    assert payload["external_session_id"] == SESSION_ID
    assert payload["user_input"] is None
    assert payload["assistant_output"] is None
    assert payload["metadata"]["conversation"] == []
    assert payload["metadata"]["deepseek_harness"]["event_count"] == 0


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json\n",
        _log({"type": "session", "version": 4, "createdAt": 1, "isSeeded": False}),
        _log({"type": "session", "version": "4", "id": SESSION_ID, "createdAt": 1, "isSeeded": False}),
        _log({"type": "turn/start", "seq": 1, "time": 1, "data": {"turn": 1}}),
    ],
)
def test_rejects_invalid_logs(content: str) -> None:
    with pytest.raises(ValueError):
        convert_deepseek_harness_content(content, source_name="session.jsonl")


def test_detects_header_and_ignores_other_formats() -> None:
    assert looks_like_harness_log(_full_log()) is True
    assert looks_like_harness_log(json.dumps({"session": {"id": "x"}, "messages": []})) is False
    assert looks_like_harness_log("") is False


def test_decodes_concatenated_zstd_frames() -> None:
    frames = [
        _header(),
        {"type": "turn/start", "seq": 1, "time": 1_760_000_001_000, "data": {"turn": 1}},
        _user_message(PROMPT, seq=2, time=1_760_000_001_100),
    ]
    compressor = zstandard.ZstdCompressor()
    content = b"".join(compressor.compress(json.dumps(row, ensure_ascii=False).encode() + b"\n") for row in frames)

    text = decode_harness_log(content)
    payload = convert_deepseek_harness_content(text, source_name="session.jsonl.zstd")

    assert payload["external_session_id"] == SESSION_ID
    assert payload["user_input"] == PROMPT


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("is_error", [False, True])
def test_historical_tool_result_wrappers(version: int, is_error: bool) -> None:
    result = _tool_result("tool output", "call-1", seq=2, time=1_760_000_001_200)
    result["data"]["message"] = {
        "role": "user",
        "id": "msg-2",
        "source": {"kind": "tool", "callId": "call-1"},
        "content": [
            {
                "type": "tool-result",
                "toolCallId": "call-1",
                "isError": is_error,
                "content": [{"type": "text", "text": "tool output"}],
            }
        ],
    }
    log = _log(
        _header(version=version),
        _tool_call("bash", {"command": "pwd"}, "call-1", seq=1, time=1_760_000_001_000),
        result,
    )

    payload = convert_deepseek_harness_content(log, source_name="session.jsonl")

    assert payload["tool_calls"][0]["output"] == "tool output"
    assert payload["tool_calls"][0]["tool_call_id"] == "call-1"
    assert payload["tool_calls"][0]["is_error"] is is_error
    assert bool(payload["errors"]) is is_error
    assert payload["user_input"] is None


def test_incomplete_tool_calls_are_preserved_in_call_order() -> None:
    log = _log(
        _header(),
        _tool_call("bash", {"command": "pytest"}, "pending", seq=1, time=1_760_000_001_000),
        _tool_call("read", {"path": "README.md"}, "finished", seq=2, time=1_760_000_001_100),
        _tool_result("read output", "finished", seq=3, time=1_760_000_001_200),
    )

    payload = convert_deepseek_harness_content(log, source_name="session.jsonl")

    assert [call["tool_call_id"] for call in payload["tool_calls"]] == ["pending", "finished"]
    assert [call["status"] for call in payload["tool_calls"]] == ["pending", "completed"]
    assert payload["tool_calls"][0]["output"] is None
    assert "Pending" in payload["metadata"]["conversation"][0]["content"]
    assert payload["shell_commands"] == []
    assert payload["errors"] == []


def test_orphan_tool_result_keeps_output() -> None:
    log = _log(_header(), _tool_result("orphan output", "orphan", seq=1, time=1_760_000_001_000))

    payload = convert_deepseek_harness_content(log, source_name="session.jsonl")

    assert payload["tool_calls"][0]["tool_call_id"] == "orphan"
    assert payload["tool_calls"][0]["output"] == "orphan output"
    assert payload["tool_calls"][0]["name"] == "tool"


def test_assistant_text_blocks_are_joined_and_unknown_events_retained() -> None:
    unknown = {"type": "plugin:example/event", "time": 1_760_000_001_000, "seq": 1, "data": {"value": "extension"}}
    log = "\n" + _log(
        _header(),
        unknown,
        _assistant_message(
            [
                {"type": "text", "text": "first paragraph"},
                {"type": "text", "text": "last paragraph"},
                {"type": "image", "url": "image-reference"},
            ],
            seq=2,
            time=1_760_000_001_100,
        ),
    )

    payload = convert_deepseek_harness_content(log, source_name="session.jsonl", project_name="override")

    assert payload["assistant_output"] == "first paragraph\nlast paragraph"
    assert payload["metadata"]["deepseek_harness"]["raw_rows"][1] == unknown
    assert payload["project_name"] == "override"
    assert looks_like_harness_log(log)


def test_timestamps_are_always_epoch_milliseconds() -> None:
    payload = convert_deepseek_harness_content(_log(_header(createdAt=1000)), source_name="session.jsonl")

    assert payload["started_at"] == "1970-01-01T00:00:01+00:00"
    assert payload["ended_at"] == payload["started_at"]


@pytest.mark.parametrize("compressed", [False, True])
def test_decoded_log_size_boundary(monkeypatch: pytest.MonkeyPatch, compressed: bool) -> None:
    content = _full_log().encode()
    monkeypatch.setattr(deepseek_harness, "MAX_LOG_BYTES", len(content))
    encode = zstandard.ZstdCompressor().compress if compressed else lambda value: value

    assert decode_harness_log(encode(content)) == content.decode()
    with pytest.raises(ValueError, match="import limit"):
        decode_harness_log(encode(content + b"\n"))


def _restore_upload_user(db: Session) -> None:
    # The shared client fixture recreates tables after its token fixture runs.
    db.expunge_all()
    db.add(User(id="test-admin-id", email="test-upload@example.com", display_name="Upload tester"))
    db.commit()


def test_auto_upload_recognizes_deepseek_log(client: TestClient, db: Session) -> None:
    _restore_upload_user(db)
    response = client.post(f"{BASE}/upload/auto", files={"file": ("session.v4.jsonl", _full_log(), "application/json")})

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["agent_type"] == "deepseek_harness"
    assert body["external_session_id"] == SESSION_ID
    assert body["metadata_json"]["deepseek_harness"]["model"] == "deepseek-chat"


def test_auto_upload_accepts_zstd_artifact(client: TestClient, db: Session) -> None:
    _restore_upload_user(db)
    compressor = zstandard.ZstdCompressor()
    content = compressor.compress(_full_log().encode())

    response = client.post(
        f"{BASE}/upload/auto", files={"file": ("session.v4.jsonl.zstd", content, "application/octet-stream")}
    )

    assert response.status_code == HTTP_OK, response.text
    assert response.json()["agent_type"] == "deepseek_harness"


def test_dedicated_endpoint_imports_and_updates(client: TestClient, db: Session) -> None:
    _restore_upload_user(db)
    response = client.post(
        f"{BASE}/upload/deepseek-jsonl",
        files={"file": ("session.jsonl", _full_log(), "application/x-ndjson")},
    )
    assert response.status_code == HTTP_OK, response.text

    update = client.put(
        f"{BASE}/upload/deepseek-jsonl",
        files={"file": ("session.jsonl", _full_log(), "application/x-ndjson")},
    )
    assert update.status_code == HTTP_OK, update.text


def test_dedicated_endpoint_rejects_non_harness_json(client: TestClient, db: Session) -> None:
    _restore_upload_user(db)
    response = client.post(
        f"{BASE}/upload/deepseek-jsonl",
        files={"file": ("session.jsonl", json.dumps({"messages": []}), "application/json")},
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert "DeepSeek Harness" in response.json()["detail"]


def test_auto_upload_updates_existing_session(client: TestClient, db: Session) -> None:
    _restore_upload_user(db)
    files = {"file": ("session.v4.jsonl", _full_log(), "application/x-ndjson")}
    first = client.post(f"{BASE}/upload/auto", files=files)
    assert first.status_code == HTTP_OK, first.text

    updated_log = _full_log() + _log(
        _assistant_message([{"type": "text", "text": "fixed"}], seq=11, time=1_760_000_002_000)
    )
    updated = client.put(
        f"{BASE}/upload/auto",
        params={"project_name": "my-project"},
        files={"file": ("session.v4.jsonl", updated_log, "application/x-ndjson")},
    )

    assert updated.status_code == HTTP_OK, updated.text
    assert updated.json()["id"] == first.json()["id"]
    assert updated.json()["metadata_json"]["assistant_output"] == "fixed"
    project = db.get(Project, updated.json()["project_id"])
    assert project is not None
    assert project.name == "my-project"


@pytest.mark.parametrize("endpoint", ["auto", "deepseek-jsonl"])
@pytest.mark.parametrize("content", [b"\xff", deepseek_harness.ZSTD_MAGIC + b"invalid"])
def test_upload_rejects_unreadable_bytes(client: TestClient, db: Session, endpoint: str, content: bytes) -> None:
    _restore_upload_user(db)
    response = client.post(f"{BASE}/upload/{endpoint}", files={"file": ("session.jsonl.zstd", content)})

    assert response.status_code == HTTP_BAD_REQUEST


@pytest.mark.parametrize("version", [0, 1, 999])
def test_auto_upload_explains_unsupported_versions(client: TestClient, db: Session, version: int) -> None:
    _restore_upload_user(db)
    response = client.post(
        f"{BASE}/upload/auto",
        files={"file": ("session.jsonl", _log(_header(version=version)))},
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert "Unsupported DeepSeek Harness version" in response.json()["detail"]


def test_documented_example_is_importable() -> None:
    path = Path(__file__).resolve().parents[2] / "examples" / "deepseek-harness-session.v4.jsonl"

    payload = convert_deepseek_harness_content(path.read_text(encoding="utf-8"), source_name=path.name)

    assert payload["external_session_id"] == "dsh-example-session"
    assert payload["user_input"] == "Check the project test command."
    assert payload["assistant_output"] == "Use uv run pytest to run the tests."
    assert payload["shell_commands"][0]["exit_code"] == 0
