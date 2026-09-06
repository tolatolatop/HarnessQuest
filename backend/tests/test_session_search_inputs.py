from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.db import Base
from app.migrations import ensure_agent_session_columns
from app.models import AgentSession
from app.services.session_search import BACKFILL_BATCH_SIZE, backfill_search_inputs, set_search_inputs


@pytest.mark.parametrize(
    "metadata,raw,expected",
    [
        ({"user_input": "one prompt"}, None, ("one prompt", None)),
        ({}, None, (None, None)),
        (
            {
                "conversation": [
                    {"role": "user", "content": "initial prompt"},
                    {"role": "user", "content": "middle prompt"},
                    {"role": "assistant", "content": "assistant answer"},
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": "latest"}, {"type": "text", "text": "prompt"}],
                    },
                    {"role": "user", "content": [{"type": "tool_result", "content": "tool output"}]},
                ]
            },
            None,
            ("initial prompt", "latest\nprompt"),
        ),
        (
            {"user_input": "fallback"},
            {
                "messages": [
                    {
                        "info": {"role": "user"},
                        "parts": [{"type": "text", "text": "first part"}, {"type": "text", "text": "second part"}],
                    },
                    {"info": {"role": "user"}, "parts": [{"type": "text", "text": "last part"}]},
                ]
            },
            ("first part\nsecond part", "last part"),
        ),
        (
            {
                "claude": {
                    "raw_rows": [
                        {"type": "user", "message": {"content": [{"type": "text", "text": "original text"}]}},
                        {"type": "user", "message": {"content": "latest original"}},
                    ]
                },
                "conversation": [{"role": "user", "content": "incomplete normalized message"}],
            },
            None,
            ("original text", "latest original"),
        ),
        (
            {
                "opencode": {
                    "raw": {
                        "messages": [
                            {
                                "info": {"role": "user"},
                                "parts": [{"type": "text", "text": "one"}, {"type": "text", "text": "two"}],
                            },
                        ]
                    }
                }
            },
            None,
            ("one\ntwo", None),
        ),
        ({}, {"metadata": {"messages": [{"role": "user", "content": "nested raw text"}]}}, ("nested raw text", None)),
    ],
)
def test_input_endpoints(metadata, raw, expected):
    session = AgentSession()
    set_search_inputs(session, metadata, raw)
    assert (session.first_user_input, session.latest_user_input) == expected
    assert session.search_inputs_version == 1


def test_migrate_old_schema_and_resume_backfill(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for column in ("first_user_input", "latest_user_input", "search_inputs_version"):
            conn.execute(text(f"ALTER TABLE agent_sessions DROP COLUMN {column}"))
        conn.execute(
            text("""
            INSERT INTO agent_sessions (id, agent_type, source, metadata_json)
            VALUES ('legacy', 'test', 'api', '{"user_input": "legacy prompt"}')
        """)
        )
    ensure_agent_session_columns(engine)
    ensure_agent_session_columns(engine)
    reader = Mock(side_effect=AssertionError("Unexpected object-storage read"))
    assert backfill_search_inputs(engine, read_raw=reader) == 1
    assert backfill_search_inputs(engine, read_raw=reader) == 0
    with Session(engine) as db:
        session = db.get(AgentSession, "legacy")
        assert session.first_user_input == "legacy prompt"
        assert session.latest_user_input is None
    engine.dispose()


def test_backfill_raw_only_failure_is_retriable(db):
    db.add(AgentSession(id="raw-only", agent_type="test", metadata_json={}, raw_artifact_uri="s3://test/raw"))
    db.commit()
    with pytest.raises(OSError, match="unavailable"):
        backfill_search_inputs(db.get_bind(), read_raw=Mock(side_effect=OSError("unavailable")))
    assert db.scalar(select(AgentSession.search_inputs_version)) is None
    reader = Mock(
        return_value={
            "messages": [
                {"role": "user", "content": "oldest raw input"},
                {"role": "user", "content": "newest raw input"},
            ]
        }
    )
    assert backfill_search_inputs(db.get_bind(), read_raw=reader) == 1
    reader.assert_called_once_with("s3://test/raw")
    session = db.get(AgentSession, "raw-only")
    assert session.first_user_input == "oldest raw input"
    assert session.latest_user_input == "newest raw input"


def test_backfill_preserves_completed_batches_on_failure(db):
    db.add_all(
        [
            AgentSession(id=f"batch-{number:04}", agent_type="test", metadata_json={"user_input": "old input"})
            for number in range(BACKFILL_BATCH_SIZE)
        ]
    )
    db.add(AgentSession(id="last-batch", agent_type="test", raw_artifact_uri="s3://test/last"))
    db.commit()
    with pytest.raises(OSError):
        backfill_search_inputs(db.get_bind(), read_raw=Mock(side_effect=OSError("unavailable")))
    assert (
        db.scalar(
            select(func.count())
            .select_from(AgentSession)
            .where(
                AgentSession.search_inputs_version == 1,
            )
        )
        == BACKFILL_BATCH_SIZE
    )
    assert backfill_search_inputs(db.get_bind(), read_raw=Mock(return_value={"user_input": "last input"})) == 1
