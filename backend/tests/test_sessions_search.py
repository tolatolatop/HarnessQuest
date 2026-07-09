"""Tests for session search features: q parameter."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AgentSession

BASE = "/api/v1/sessions"
HTTP_OK = 200


def _seed_session(
    db: Session,
    ext_id: str,
    summary: str,
    agent_type: str = "claude-code",
    repository: str = "/repo/demo",
    branch: str = "main",
) -> str:
    """Create a session directly in the DB and return its id."""
    session = AgentSession(
        id=ext_id,
        external_session_id=ext_id,
        langfuse_session_id=ext_id,
        agent_type=agent_type,
        repository=repository,
        branch=branch,
        summary=summary,
    )
    db.add(session)
    db.commit()
    return session.id


def test_list_sessions_q_matches_id_prefix(
    client: TestClient, db: Session
) -> None:
    """Search by session id prefix returns matching sessions."""
    _seed_session(db, "alpha-session", "Alpha summary")
    _seed_session(db, "beta-session", "Beta summary")

    # Search by id prefix (>4 chars)
    resp = client.get(f"{BASE}?q=alpha")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["summary"] == "Alpha summary"

    # Search by id prefix that doesn't exist
    resp = client.get(f"{BASE}?q=gamma")
    assert resp.status_code == HTTP_OK
    assert resp.json()["items"] == []


def test_list_sessions_q_matches_summary(
    client: TestClient, db: Session
) -> None:
    """Search by summary text returns matching sessions."""
    _seed_session(db, "summ-sess-1", "Connection timeout error")
    _seed_session(db, "summ-sess-2", "Database migration success")

    resp = client.get(f"{BASE}?q=timeout")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["summary"] == "Connection timeout error"


def test_list_sessions_q_ignored_below_five_chars(
    client: TestClient, db: Session
) -> None:
    """q filter with <=4 chars is ignored (returns all sessions)."""
    _seed_session(db, "min-q-1", "Session A")
    _seed_session(db, "min-q-2", "Session B")

    # 4-char q should be ignored (return all)
    resp = client.get(f"{BASE}?q=abcd")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert len(data["items"]) >= 2

    # 5-char q that doesn't match should return empty
    resp = client.get(f"{BASE}?q=nonex")
    assert resp.status_code == HTTP_OK
    assert resp.json()["items"] == []


def test_list_sessions_q_matches_external_session_id(
    client: TestClient, db: Session
) -> None:
    """Search matches external_session_id field."""
    _seed_session(db, "ext-id-special-001", "External ID test")

    resp = client.get(f"{BASE}?q=special-001")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert len(data["items"]) == 1


def test_list_sessions_q_matches_branch(
    client: TestClient, db: Session
) -> None:
    """Search matches branch field."""
    _seed_session(db, "branch-sess-1", "Branch test", branch="feature/user-auth")
    _seed_session(db, "branch-sess-2", "Other", branch="main")

    resp = client.get(f"{BASE}?q=user-auth")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["branch"] == "feature/user-auth"
