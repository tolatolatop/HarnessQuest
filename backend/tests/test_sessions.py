from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentSession
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
