import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentSession, User
from app.routes import sessions as session_routes
from app.schemas import SessionImport

BASE = "/api/v1/sessions"
HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409


class _FakeStorage:
    def put_json(self, prefix: str, payload: dict[str, Any]) -> str:
        return f"memory://{prefix}/{payload.get('external_session_id', 'session')}.json"


async def _fake_write_langfuse_trace(payload: SessionImport) -> tuple[str | None, str | None, str | None]:
    return payload.langfuse_session_id, payload.langfuse_trace_id, payload.langfuse_url


@pytest.fixture(autouse=True)
def _patch_session_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_routes, "ObjectStorage", lambda: _FakeStorage())
    monkeypatch.setattr(session_routes, "write_langfuse_trace", _fake_write_langfuse_trace)


def _payload(session_id: str, summary: str) -> dict[str, Any]:
    return {
        "external_session_id": session_id,
        "langfuse_session_id": session_id,
        "agent_type": "claude-code",
        "repository": "/repo/demo",
        "branch": "main",
        "summary": summary,
        "raw": {"external_session_id": session_id, "summary": summary},
    }


def test_search_user_endpoints_update_clear_and_delete(client: TestClient) -> None:
    payload = _payload("endpoint-session", "summary-marker")
    payload["metadata"] = {"conversation": [
        {"role": "user", "content": "initial-marker 处理用户最初的请求 literal%_\\value"},
        {"role": "user", "content": "middle-marker"},
        {"role": "user", "content": "latest-marker"},
        {"role": "assistant", "content": "assistant-marker"},
    ]}
    assert client.post(f"{BASE}/import", json=payload).status_code == HTTP_OK
    for keyword in ("initial-marker", "LATEST-MARKER", "summary-marker", "用户最初的请求", "literal%_\\value"):
        result = client.get(BASE, params={"q": keyword}).json()
        assert result["total"] == 1, keyword
    for keyword in ("middle-marker", "assistant-marker", "initial marker", "literalXY\\value", "%%%%%", "_____"):
        assert client.get(BASE, params={"q": keyword}).json()["total"] == 0, keyword

    payload["metadata"]["conversation"].append({"role": "user", "content": "replacement-marker"})
    assert client.put(f"{BASE}/import", json=payload).status_code == HTTP_OK
    assert client.get(BASE, params={"q": "latest-marker"}).json()["total"] == 0
    assert client.get(BASE, params={"q": "replacement-marker"}).json()["total"] == 1

    payload["metadata"] = {}
    assert client.put(f"{BASE}/import", json=payload).status_code == HTTP_OK
    assert client.get(BASE, params={"q": "initial-marker"}).json()["total"] == 0
    assert client.delete(f"{BASE}/endpoint-session").status_code == HTTP_OK
    assert client.get(BASE, params={"q": "summary-marker"}).json()["total"] == 0


def test_search_import_raw_and_single_input(client: TestClient) -> None:
    raw_payload = _payload("raw-search-session", "unrelated summary")
    raw_payload["raw"] = {"messages": [
        {"role": "user", "content": "raw-first-marker"},
        {"role": "user", "content": "raw-latest-marker"},
    ]}
    assert client.post(f"{BASE}/import", json=raw_payload).status_code == HTTP_OK
    for keyword in ("raw-first-marker", "raw-latest-marker"):
        assert client.get(BASE, params={"q": keyword}).json()["total"] == 1
    single = _payload("single-search-session", "unrelated summary")
    single["user_input"] = "single-input-marker"
    assert client.post(f"{BASE}/import", json=single).status_code == HTTP_OK
    assert client.get(BASE, params={"q": "single-input-marker"}).json()["total"] == 1


@pytest.mark.parametrize("format_name", ["claude", "opencode", "deepseek"])
def test_search_auto_upload_preserves_complete_user_turns(client: TestClient, db: Session, format_name: str) -> None:
    # The shared client fixture recreates tables after its token fixture runs.
    # Upload converters need an actual current user, so restore that test row.
    db.expunge_all()
    db.add(User(id="test-admin-id", email="test-upload@example.com", display_name="Upload tester"))
    db.commit()
    first_parts = [{"type": "text", "text": "first-block-marker"},
                   {"type": "text", "text": "second-block-marker"}]
    last_parts = [{"type": "text", "text": "latest-block-marker"},
                  {"type": "text", "text": "x" * 20_000 + " untruncated-tail-marker"}]
    if format_name == "claude":
        content = "\n".join(json.dumps(row) for row in [
            {"type": "user", "sessionId": "claude-search", "message": {"role": "user", "content": first_parts}},
            {"type": "user", "sessionId": "claude-search", "message": {"role": "user", "content": last_parts}},
            {"type": "user", "sessionId": "claude-search", "message": {"role": "user", "content": [
                {"type": "tool_result", "content": "excluded-tool-marker"},
            ]}},
        ])
    elif format_name == "opencode":
        content = json.dumps({"session": {"id": "opencode-search"}, "messages": [
            {"info": {"role": "user"}, "parts": first_parts},
            {"info": {"role": "user"}, "parts": last_parts},
        ]})
    else:
        content = "\n".join(json.dumps(row) for row in [
            {"type": "session", "version": 4, "id": "deepseek-search", "createdAt": 1_760_000_000_000,
             "isSeeded": False, "delegationDepth": 0},
            {"type": "user/message", "seq": 1, "time": 1_760_000_001_000, "surfaceOp": "append",
             "data": {"role": "user", "id": "m1", "source": {"kind": "user"}, "content": first_parts}},
            # Injected context is not a user turn and must stay out of the endpoints.
            {"type": "user/message", "seq": 2, "time": 1_760_000_001_100, "surfaceOp": "append",
             "data": {"role": "user", "id": "m2", "source": {"kind": "runtime-context"},
                      "content": [{"type": "text", "text": "excluded-context-marker"}]}},
            {"type": "user/message", "seq": 3, "time": 1_760_000_001_200, "surfaceOp": "append",
             "data": {"role": "user", "id": "m3", "source": {"kind": "user"}, "content": last_parts}},
            {"type": "tool/result", "seq": 4, "time": 1_760_000_001_300, "surfaceOp": "append",
             "data": {"turn": 1, "step": 1, "message": {
                 "role": "tool", "id": "m4", "source": {"kind": "tool", "callId": "c1"},
                 "toolCallId": "c1", "isError": False,
                 "content": [{"type": "text", "text": "excluded-tool-marker"}]}}},
        ]) + "\n"
    result = client.post(f"{BASE}/upload/auto", files={"file": ("session.json", content, "application/json")})
    assert result.status_code == HTTP_OK, result.text
    for keyword in ("first-block-marker\nsecond-block-marker", "latest-block-marker", "untruncated-tail-marker"):
        assert client.get(BASE, params={"q": keyword}).json()["total"] == 1, (keyword, result.json())
    for keyword in ("excluded-tool-marker", "excluded-context-marker"):
        assert client.get(BASE, params={"q": keyword}).json()["total"] == 0, keyword


def test_search_combines_filters_and_pagination(client: TestClient) -> None:
    for number in range(3):
        payload = _payload(f"paged-search-{number}", "summary")
        payload["user_input"] = "shared-input-marker"
        payload["project_name"] = "project-a" if number < 2 else "project-b"
        payload["started_at"] = f"2026-08-{number + 1:02}T00:00:00Z"
        result = client.post(f"{BASE}/import", json=payload)
        assert result.status_code == HTTP_OK
        if number == 0:
            project_id = result.json()["project_id"]
    params = {"q": "shared-input-marker", "project_id": project_id, "page_size": 1}
    first = client.get(BASE, params=params).json()
    second = client.get(BASE, params={**params, "page": 2}).json()
    assert first["total"] == second["total"] == 2
    assert first["items"][0]["id"] != second["items"][0]["id"]
    filtered = client.get(BASE, params={**params, "created_from": "2026-08-02T00:00:00Z"}).json()
    assert filtered["total"] == 1


def test_post_duplicate_session_id_returns_conflict(client: TestClient, db: Session) -> None:
    first = client.post(f"{BASE}/import", json=_payload("session-1", "first import"))
    assert first.status_code == HTTP_OK

    duplicate = client.post(f"{BASE}/import", json=_payload("session-1", "duplicate import"))

    assert duplicate.status_code == HTTP_CONFLICT
    assert duplicate.json()["detail"]["message"] == "Session already exists"
    sessions = list(db.scalars(select(AgentSession).where(AgentSession.external_session_id == "session-1")))
    assert len(sessions) == 1
    assert sessions[0].summary == "first import"


def test_put_updates_existing_session_content(client: TestClient, db: Session) -> None:
    first = client.post(f"{BASE}/import", json=_payload("session-2", "before update"))
    assert first.status_code == HTTP_OK
    session_id = first.json()["id"]

    updated = client.put(f"{BASE}/import", json=_payload("session-2", "after update"))

    assert updated.status_code == HTTP_OK
    data = updated.json()
    assert data["id"] == session_id
    assert data["summary"] == "after update"
    session = db.get(AgentSession, session_id)
    assert session is not None
    db.refresh(session)
    assert session.summary == "after update"
    assert session.raw_artifact_uri == "memory://sessions/session-2.json"


def test_put_missing_session_returns_not_found(client: TestClient) -> None:
    response = client.put(f"{BASE}/import", json=_payload("missing-session", "missing"))

    assert response.status_code == HTTP_NOT_FOUND
    assert response.json()["detail"] == "Session not found"


def test_delete_by_prompt_id_soft_deletes_and_reupload_cannot_restore(
    client: TestClient, db: Session
) -> None:
    created = client.post(f"{BASE}/import", json=_payload("prompt-delete-1", "to delete"))
    assert created.status_code == HTTP_OK
    internal_id = created.json()["id"]

    deleted = client.delete(f"{BASE}/prompt-delete-1")
    assert deleted.status_code == HTTP_OK
    assert deleted.json() == {"status": "deleted", "session_id": internal_id}

    session = db.get(AgentSession, internal_id)
    assert session is not None
    db.refresh(session)
    deleted_at = session.deleted_at
    assert deleted_at is not None
    assert client.get(BASE).json() == {"items": [], "total": 0}
    assert client.get(f"{BASE}/{internal_id}").status_code == HTTP_NOT_FOUND
    assert client.get(f"{BASE}/{internal_id}/raw").status_code == HTTP_NOT_FOUND

    duplicate = client.post(f"{BASE}/import", json=_payload("prompt-delete-1", "new post"))
    assert duplicate.status_code == HTTP_CONFLICT
    update = client.put(f"{BASE}/import", json=_payload("prompt-delete-1", "new put"))
    assert update.status_code == HTTP_NOT_FOUND
    db.refresh(session)
    assert session.deleted_at == deleted_at
    assert session.summary == "to delete"


def test_import_parses_creation_and_latest_user_or_assistant_reply_time(client: TestClient) -> None:
    payload = _payload("timed-session", "with timestamps")
    payload["metadata"] = {
        "conversation": [
            {"role": "user", "timestamp": "2026-08-20T01:00:00Z", "content": "first"},
            {"role": "tool", "timestamp": "2026-08-20T04:00:00Z", "content": "ignored"},
            {"role": "assistant", "timestamp": "2026-08-20T02:00:00Z", "content": "reply"},
            {"role": "user", "timestamp": "2026-08-20T03:00:00Z", "content": "latest"},
        ]
    }

    response = client.post(f"{BASE}/import", json=payload)

    assert response.status_code == HTTP_OK
    # SQLite drops timezone information; the production PostgreSQL column preserves it.
    assert response.json()["started_at"].startswith("2026-08-20T01:00:00")
    assert response.json()["ended_at"].startswith("2026-08-20T03:00:00")
