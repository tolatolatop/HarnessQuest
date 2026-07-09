"""Tests for case search features: session_id filter."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AgentCase, AgentSession

BASE = "/api/v1/cases"
HTTP_OK = 200


@pytest.fixture(autouse=True)
def _skip_external_deps():
    """No external deps to mock for cases -- session creation is done via DB directly."""
    yield


def _seed_session(db: Session, session_id: str) -> str:
    """Create a session directly in the DB and return its id."""
    session = AgentSession(
        id=session_id,
        external_session_id=session_id,
        langfuse_session_id=session_id,
        agent_type="claude-code",
    )
    db.add(session)
    db.commit()
    return session_id


def _seed_case(db: Session, session_id: str | None, title: str) -> str:
    """Create a case directly in the DB and return its id."""
    case = AgentCase(
        title=title,
        session_id=session_id,
        severity="medium",
        problem_type="other",
    )
    db.add(case)
    db.commit()
    return case.id


def test_list_cases_with_session_id_returns_matching_cases(
    client: TestClient, db: Session
) -> None:
    """session_id filter returns only cases linked to that session."""
    session_id = _seed_session(db, "filter-session-1")

    _seed_case(db, session_id, "Linked case")
    _seed_case(db, None, "Unlinked case")

    resp = client.get(f"{BASE}?session_id={session_id}")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["session_id"] == session_id
    assert data["items"][0]["title"] == "Linked case"


def test_list_cases_with_session_id_returns_empty_when_no_match(
    client: TestClient, db: Session
) -> None:
    """session_id filter returns empty list for non-existent session."""
    resp = client.get(f"{BASE}?session_id=nonexistent-session-id-xyz")
    assert resp.status_code == HTTP_OK
    assert resp.json()["items"] == []


def test_list_cases_session_id_min_length_guard(
    client: TestClient, db: Session
) -> None:
    """session_id filter with <=4 chars is ignored (returns all cases)."""
    session_id = _seed_session(db, "min-length-session")
    _seed_case(db, session_id, "Linked case")

    # Query with a 4-char session_id -- should be ignored
    resp = client.get(f"{BASE}?session_id=abcd")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert len(data["items"]) >= 1

    # Query with a 5-char session_id -- should filter but no match
    resp = client.get(f"{BASE}?session_id=nonex")
    assert resp.status_code == HTTP_OK
    assert resp.json()["items"] == []


def test_list_cases_session_id_combined_with_status(
    client: TestClient, db: Session
) -> None:
    """session_id filter can be combined with status filter."""
    from app.models import CaseStatus

    session_id = _seed_session(db, "combined-filter-session")

    case_id = _seed_case(db, session_id, "Combined case")

    # Query with session_id + status
    resp = client.get(f"{BASE}?session_id={session_id}&status=to_triage")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == case_id

    # Query with session_id + non-matching status
    resp = client.get(f"{BASE}?session_id={session_id}&status=closed")
    assert resp.status_code == HTTP_OK
    assert resp.json()["items"] == []
