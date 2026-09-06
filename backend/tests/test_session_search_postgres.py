"""Opt-in PostgreSQL integration/scale check; uses an isolated temporary schema.

HQ_SEARCH_TEST_DATABASE_URL=postgresql+psycopg://... PYTHONPATH=backend \
    python -m pytest backend/tests/test_session_search_postgres.py -s
"""

import json
import os
import time
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, insert, select, text, update

from app.db import Base
from app.models import AgentSession
from app.services.session_search import SEARCH_INDEX_NAME, ensure_search_index, search_predicate

DATABASE_URL = os.environ.get("HQ_SEARCH_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Set HQ_SEARCH_TEST_DATABASE_URL for PostgreSQL checks")


@pytest.fixture
def postgres_engine():
    admin = create_engine(DATABASE_URL)
    schema = "search_test_" + uuid.uuid4().hex
    with admin.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(DATABASE_URL, connect_args={"options": f"-csearch_path={schema},public"})
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def _plan(connection, statement):
    compiled = statement.compile(dialect=connection.dialect)
    return connection.exec_driver_sql(
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + str(compiled),
        compiled.params,
    ).scalar_one()[0]


def test_postgres_index_correctness_and_12000_session_scale(postgres_engine):
    engine = postgres_engine
    count = 12_000
    with engine.begin() as conn:
        for start in range(0, count, 200):
            conn.execute(
                insert(AgentSession),
                [
                    {
                        "id": str(number),
                        "external_session_id": f"session-{number}",
                        "agent_type": "test",
                        "summary": f"Summary for session {number}",
                        "first_user_input": f"Please implement task {number} " + "普通用户的初始输入文本 " * 30,
                        "latest_user_input": (
                            "unique-marker 用户最后输入关键词 literal%_\\value"
                            if number == 42
                            else f"Please verify task {number} " + "普通用户的最终输入文本 " * 30
                        ),
                        "search_inputs_version": 1,
                        "metadata_json": {"conversation": [{"role": "assistant", "content": "irrelevant " * 800}]},
                    }
                    for number in range(start, min(start + 200, count))
                ],
            )
    started = time.perf_counter()
    ensure_search_index(engine)
    build_seconds = time.perf_counter() - started
    ensure_search_index(engine)
    with engine.begin() as conn:
        conn.execute(text("ANALYZE agent_sessions"))
        predicate = search_predicate("unique-marker", postgresql=True)
        base = select(AgentSession).where(AgentSession.deleted_at.is_(None), predicate)
        page = base.order_by(func.coalesce(AgentSession.started_at, AgentSession.created_at).desc()).limit(30)
        total = select(func.count()).select_from(base.order_by(None).with_only_columns(AgentSession.id).subquery())
        page_plan = _plan(conn, page)
        count_plan = _plan(conn, total)
        baseline = (
            select(func.count())
            .select_from(AgentSession)
            .where(
                AgentSession.deleted_at.is_(None),
                search_predicate("unique-marker", postgresql=False),
            )
        )
        baseline_plan = _plan(conn, baseline)
        assert SEARCH_INDEX_NAME in json.dumps(page_plan)
        assert SEARCH_INDEX_NAME in json.dumps(count_plan)
        assert conn.scalar(total) == 1
        for keyword, expected in [
            ("UNIQUE-MARKER", ["42"]),
            ("用户最后输入关键词", ["42"]),
            ("literal%_\\value", ["42"]),
            ("unique marker", []),
            ("%%%%%", []),
            ("irrelevant", []),
            ("missing-marker", []),
        ]:
            assert (
                list(
                    conn.scalars(
                        select(AgentSession.id).where(
                            AgentSession.deleted_at.is_(None),
                            search_predicate(keyword, postgresql=True),
                        )
                    )
                )
                == expected
            )
        sizes = (
            conn.execute(
                text("""
            SELECT pg_relation_size('ix_agent_sessions_search_trgm') AS index_bytes,
                   sum(octet_length(first_user_input) + coalesce(octet_length(latest_user_input), 0)) AS input_bytes
            FROM agent_sessions
        """)
            )
            .mappings()
            .one()
        )
        print(
            json.dumps(
                {
                    "sessions": count,
                    "index_build_seconds": round(build_seconds, 3),
                    **dict(sizes),
                    "indexed_page_ms": page_plan["Execution Time"],
                    "indexed_count_ms": count_plan["Execution Time"],
                    "unindexed_count_ms": baseline_plan["Execution Time"],
                    "page_plan": page_plan["Plan"],
                    "count_plan": count_plan["Plan"],
                },
                ensure_ascii=False,
                default=str,
            )
        )

        # PostgreSQL maintains the expression index for updates/deletes itself.
        conn.execute(update(AgentSession).where(AgentSession.id == "42").values(latest_user_input="changed-marker"))
        assert conn.scalar(total) == 0
        changed = select(AgentSession.id).where(
            AgentSession.deleted_at.is_(None),
            search_predicate("changed-marker", postgresql=True),
        )
        assert conn.scalar(changed) == "42"
        conn.execute(update(AgentSession).where(AgentSession.id == "42").values(deleted_at=datetime.now(UTC)))
        assert conn.scalar(changed) is None

        # A separator in the literal query must not join two distinct fields.
        conn.execute(
            update(AgentSession)
            .where(AgentSession.id == "43")
            .values(
                summary="boundary-first",
                first_user_input="boundary-last",
            )
        )
        assert (
            conn.scalar(
                select(AgentSession.id).where(
                    search_predicate("boundary-first\x1fboundary-last", postgresql=True),
                )
            )
            is None
        )
