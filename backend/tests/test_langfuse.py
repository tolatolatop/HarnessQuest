import asyncio
import json

import pytest

from app.schemas import SessionImport
from app.services import langfuse

LANGFUSE_TIMEOUT_SECONDS = 10
MAX_TRACE_BODY_BYTES = 20_000


def _payload() -> SessionImport:
    return SessionImport.model_validate(
        {
            "external_session_id": "session-1",
            "langfuse_session_id": "session-1",
            "langfuse_trace_id": "deepseek_session-1",
            "agent_type": "deepseek_harness",
            "source": "deepseek_harness_jsonl_import",
            "repository": "/workspace/demo",
            "user_input": "hi",
            "assistant_output": "done",
            "tool_calls": [{"name": "bash", "input": {"command": "ls"}, "output": "ok"}],
            "shell_commands": [{"command": "ls", "exit_code": 0, "status": "completed", "output": "ok"}],
            "file_edits": [{"path": "a.py", "change": "x"}],
            "errors": [{"type": "tool_error", "message": "boom"}],
            "metadata": {
                "converter": "harnessquest.deepseek_harness.v1",
                "deepseek_harness": {"session_id": "session-1", "model": "deepseek-chat", "raw_rows": [{"a": 1}]},
                "conversation": [{"role": "user", "content": "hi"}],
                "messages": [{"role": "user", "content": "hi"}],
                "langfuse_shape": {
                    "sessionId": "session-1",
                    "trace": {"id": "deepseek_session-1", "name": "demo"},
                    "observations": [{"id": "obs-1", "output": "ok"}],
                },
            },
        }
    )


def test_trace_metadata_drops_bulk_sections() -> None:
    metadata = langfuse.trace_metadata(_payload())

    assert metadata["source"] == "deepseek_harness_jsonl_import"
    assert metadata["deepseek_harness"]["model"] == "deepseek-chat"
    assert "raw_rows" not in metadata["deepseek_harness"]
    assert "conversation" not in metadata
    assert "messages" not in metadata
    assert "tool_calls" not in metadata
    assert "shell_commands" not in metadata
    assert "file_edits" not in metadata
    assert metadata["langfuse_shape"]["trace"]["id"] == "deepseek_session-1"
    assert "observations" not in metadata["langfuse_shape"]
    assert metadata["langfuse_shape"]["observation_count"] == 1
    assert metadata["counts"] == {
        "conversation": 1,
        "tool_calls": 1,
        "shell_commands": 1,
        "file_edits": 1,
        "errors": 1,
    }
    assert metadata["trimmed_keys"] == [
        "conversation",
        "deepseek_harness.raw_rows",
        "langfuse_shape.observations",
        "messages",
    ]


def test_trace_metadata_keeps_small_metadata_intact() -> None:
    payload = SessionImport.model_validate(
        {
            "external_session_id": "session-2",
            "agent_type": "claude_code",
            "source": "claude_jsonl_import",
            "metadata": {
                "converter": "harnessquest.claude_jsonl.v1",
                "claude": {"session_id": "session-2", "version": "2.0.1"},
            },
        }
    )

    metadata = langfuse.trace_metadata(payload)

    assert metadata["claude"]["version"] == "2.0.1"
    assert "trimmed_keys" not in metadata
    assert metadata["counts"]["conversation"] == 0


@pytest.mark.parametrize("with_observations", [False, True])
def test_trace_metadata_drops_duplicate_large_input_output_without_mutating_payload(with_observations: bool) -> None:
    payload = _payload()
    payload.user_input = "input text " * 100_000
    payload.assistant_output = "answer text " * 100_000
    shape = payload.metadata["langfuse_shape"]
    shape["trace"].update({"input": {"prompt": payload.user_input}, "output": {"answer": payload.assistant_output}})
    if not with_observations:
        shape.pop("observations")
    original = payload.model_dump(mode="json")

    metadata = langfuse.trace_metadata(payload)

    assert "input" not in metadata["langfuse_shape"]["trace"]
    assert "output" not in metadata["langfuse_shape"]["trace"]
    assert metadata["langfuse_shape"]["trace"]["id"] == payload.langfuse_trace_id
    assert "langfuse_shape.trace.input" in metadata["trimmed_keys"]
    assert "langfuse_shape.trace.output" in metadata["trimmed_keys"]
    assert len(json.dumps(metadata).encode()) < MAX_TRACE_BODY_BYTES
    assert payload.model_dump(mode="json") == original


def test_write_langfuse_trace_sends_trimmed_metadata(monkeypatch) -> None:
    class _Settings:
        langfuse_public_key = "pk"
        langfuse_secret_key = "sk"
        langfuse_base_url = "http://langfuse.test"

    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

    class _Client:
        def __init__(self, *, timeout: int) -> None:
            assert timeout == LANGFUSE_TIMEOUT_SECONDS

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

        async def post(self, url: str, *, auth: tuple[str, str], json: dict[str, object]) -> _Response:
            captured["url"] = url
            captured["auth"] = auth
            captured["json"] = json
            return _Response()

    monkeypatch.setattr(langfuse, "get_settings", lambda: _Settings())
    monkeypatch.setattr(langfuse.httpx, "AsyncClient", _Client)

    payload = _payload()
    payload.metadata["langfuse_shape"]["trace"].update(
        {
            "input": {"prompt": payload.user_input},
            "output": {"answer": payload.assistant_output},
        }
    )
    session_id, trace_id, url = asyncio.run(langfuse.write_langfuse_trace(payload))

    assert session_id == "session-1"
    assert trace_id == "deepseek_session-1"
    assert url == "http://langfuse.test/trace/deepseek_session-1"
    assert captured["url"] == "http://langfuse.test/api/public/ingestion"
    body = captured["json"]["batch"][0]["body"]  # type: ignore[index]
    assert body["metadata"]["counts"]["tool_calls"] == 1
    assert "conversation" not in body["metadata"]
    assert body["input"] == payload.user_input
    assert body["output"] == payload.assistant_output
    assert "input" not in body["metadata"]["langfuse_shape"]["trace"]
    assert "output" not in body["metadata"]["langfuse_shape"]["trace"]
    assert len(json.dumps(body)) < MAX_TRACE_BODY_BYTES
