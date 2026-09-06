"""Literal session search with a single PostgreSQL GIN expression index.

Only the two user-input endpoints are materialized; the combined search text
exists only as an index expression, never as another stored conversation copy.
"""

from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import and_, func, literal_column, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import AgentSession
from app.services.storage import ObjectStorage

SEARCH_INPUTS_VERSION = 1
BACKFILL_BATCH_SIZE = 100
SEARCH_INDEX_NAME = "ix_agent_sessions_search_trgm"


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            part["text"]
            for part in value
            if isinstance(part, dict)
            and part.get("type") in {"text", "input_text"}
            and isinstance(part.get("text"), str)
        )
    return ""


def _user_inputs(messages: list[Any]) -> Iterable[str]:
    for item in messages:
        if not isinstance(item, dict):
            continue
        message = item.get("message") or item.get("info")
        message = message if isinstance(message, dict) else item
        if (message.get("role") or item.get("role") or item.get("type")) != "user":
            continue
        content = item.get("parts", message.get("content", message.get("text")))
        value = _message_text(content)
        if value.strip():
            yield value


def _message_lists(source: dict[str, Any]) -> Iterable[list[Any]]:
    # Converter originals preserve multi-part messages as a single user turn.
    claude = source.get("claude")
    if isinstance(claude, dict) and isinstance(claude.get("raw_rows"), list):
        yield claude["raw_rows"]
    opencode = source.get("opencode")
    if isinstance(opencode, dict) and isinstance(opencode.get("raw"), dict):
        yield from _message_lists(opencode["raw"])
    for key in ("conversation", "messages", "message"):
        if isinstance(source.get(key), list):
            yield source[key]
    metadata = source.get("metadata")
    if isinstance(metadata, dict):
        yield from _message_lists(metadata)


def conversation_inputs(source: dict[str, Any]) -> tuple[str, str] | None:
    """Use source order, as the importers do; tool results are never user text."""
    for messages in _message_lists(source):
        inputs = iter(_user_inputs(messages))
        first = next(inputs, None)
        if first is not None:
            latest = first
            for value in inputs:
                latest = value
            return first, latest
    return None


def set_search_inputs(
    session: AgentSession,
    metadata: dict[str, Any],
    raw: dict[str, Any] | None = None,
) -> None:
    endpoints = conversation_inputs(metadata) or conversation_inputs(raw or {})
    fallback = metadata.get("user_input") or (raw or {}).get("user_input")
    first, latest = endpoints or (fallback, fallback)
    session.first_user_input = first if isinstance(first, str) and first.strip() else None
    # Single-turn / identical endpoints need only one stored copy.
    session.latest_user_input = latest if isinstance(latest, str) and latest != first and latest.strip() else None
    session.search_inputs_version = SEARCH_INPUTS_VERSION


def _search_columns() -> list[Any]:
    return [
        AgentSession.id,
        AgentSession.external_session_id,
        AgentSession.langfuse_session_id,
        AgentSession.langfuse_trace_id,
        AgentSession.agent_type,
        AgentSession.repository,
        AgentSession.branch,
        AgentSession.summary,
        AgentSession.first_user_input,
        AgentSession.latest_user_input,
    ]


def search_expression() -> ColumnElement[str]:
    # Literal constants keep the expression identical in DDL and prepared queries.
    fields = [func.coalesce(column, literal_column("''")) for column in _search_columns()]
    expression: ColumnElement[str] = fields[0]
    for field in fields[1:]:
        expression = expression.concat(literal_column("chr(31)")).concat(field)
    return expression


def search_predicate(keyword: str, *, postgresql: bool) -> ColumnElement[bool]:
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    exact = or_(*(column.ilike(pattern, escape="\\") for column in _search_columns()))
    if not postgresql:
        return exact
    # Recheck individual fields so a query cannot match across field boundaries.
    return and_(search_expression().ilike(pattern, escape="\\"), exact)


def ensure_search_index(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    expression = search_expression().compile(
        dialect=engine.dialect,
        compile_kwargs={"literal_binds": True, "include_table": False},
    )
    # Migration-managed: create_all runs before new columns/extensions exist.
    # Only a compiled static expression is interpolated here, never user input.
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        connection.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {SEARCH_INDEX_NAME} ON agent_sessions "
                f"USING gin (({expression}) gin_trgm_ops) WHERE deleted_at IS NULL"
            )
        )


def backfill_search_inputs(
    engine: Engine,
    *,
    read_raw: Callable[[str], dict[str, Any]] | None = None,
) -> int:
    """Resumable, bounded batches. Read object storage only for raw-only records.

    An unavailable artifact fails the migration instead of marking an incomplete
    row as indexed. Committed batches survive a retry. Row locks serialize this
    work with PUT imports and other startup workers on PostgreSQL.
    """
    updated = 0
    with Session(engine) as db:
        while True:
            rows = list(
                db.scalars(
                    select(AgentSession)
                    .where(AgentSession.search_inputs_version.is_(None), AgentSession.deleted_at.is_(None))
                    .order_by(AgentSession.id)
                    .limit(BACKFILL_BATCH_SIZE)
                    .with_for_update()
                )
            )
            if not rows:
                return updated
            for session in rows:
                metadata = session.metadata_json or {}
                raw = None
                if conversation_inputs(metadata) is None and session.raw_artifact_uri:
                    if read_raw is None:
                        read_raw = ObjectStorage().get_json
                    raw = read_raw(session.raw_artifact_uri)
                set_search_inputs(session, metadata, raw)
            db.commit()
            updated += len(rows)
