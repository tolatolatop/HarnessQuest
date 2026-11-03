from typing import Any

import httpx

from app.config import get_settings
from app.schemas import SessionImport

# Trace metadata carries routing and summary fields for filtering. Parsed
# conversations, raw rows and tool dumps stay in HarnessQuest: spreading them
# into the ingestion payload made every import ship the whole session log to
# Langfuse, which rejects or times out on large traces.
LANGFUSE_BULK_METADATA_KEYS = frozenset(
    {"conversation", "messages", "raw", "raw_rows", "tool_calls", "shell_commands", "file_edits"}
)
LANGFUSE_NESTED_METADATA_KEYS = ("claude", "deepseek_harness", "opencode")


def trace_metadata(payload: SessionImport) -> dict[str, Any]:
    """Build the small metadata object sent with a Langfuse trace."""
    metadata: dict[str, Any] = {
        "source": payload.source,
        "repository": payload.repository,
        "branch": payload.branch,
        "commit_sha": payload.commit_sha,
        **payload.metadata,
    }
    trimmed = [key for key in LANGFUSE_BULK_METADATA_KEYS if key in metadata]
    for key in trimmed:
        metadata.pop(key)
    for name in LANGFUSE_NESTED_METADATA_KEYS:
        section = metadata.get(name)
        if not isinstance(section, dict):
            continue
        removed = [key for key in ("raw_rows", "raw") if key in section]
        if not removed:
            continue
        metadata[name] = {key: value for key, value in section.items() if key not in removed}
        trimmed.extend(f"{name}.{key}" for key in removed)

    conversation = payload.metadata.get("conversation")
    shape = metadata.get("langfuse_shape")
    if isinstance(shape, dict):
        metadata["langfuse_shape"], shape_trimmed = _trim_trace_shape(shape)
        trimmed.extend(shape_trimmed)

    metadata["counts"] = {
        "conversation": len(conversation) if isinstance(conversation, list) else 0,
        "tool_calls": len(payload.tool_calls),
        "shell_commands": len(payload.shell_commands),
        "file_edits": len(payload.file_edits),
        "errors": len(payload.errors),
    }
    if trimmed:
        metadata["trimmed_keys"] = sorted(trimmed)
    return metadata


def _trim_trace_shape(shape: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    result = dict(shape)
    trimmed: list[str] = []
    if "observations" in result:
        observations = result.pop("observations")
        result["observation_count"] = len(observations) if isinstance(observations, list) else 0
        trimmed.append("langfuse_shape.observations")
    trace = result.get("trace")
    if isinstance(trace, dict):
        removed = [key for key in ("input", "output") if key in trace]
        if removed:
            result["trace"] = {key: value for key, value in trace.items() if key not in removed}
            trimmed.extend(f"langfuse_shape.trace.{key}" for key in removed)
    return result, trimmed


async def write_langfuse_trace(payload: SessionImport) -> tuple[str | None, str | None, str | None]:
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return payload.langfuse_session_id, payload.langfuse_trace_id, payload.langfuse_url

    trace_id = payload.langfuse_trace_id or payload.external_session_id
    if not trace_id:
        return payload.langfuse_session_id, payload.langfuse_trace_id, payload.langfuse_url
    timestamp = payload.started_at or payload.ended_at

    body = {
        "batch": [
            {
                "id": f"{trace_id}-trace",
                "type": "trace-create",
                "timestamp": timestamp.isoformat() if timestamp else None,
                "body": {
                    "id": trace_id,
                    "sessionId": payload.langfuse_session_id or payload.external_session_id,
                    "name": f"{payload.agent_type} session",
                    "input": payload.user_input,
                    "output": payload.assistant_output,
                    "metadata": trace_metadata(payload),
                },
            }
        ]
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{settings.langfuse_base_url.rstrip('/')}/api/public/ingestion",
            auth=(settings.langfuse_public_key, settings.langfuse_secret_key),
            json=body,
        )
        response.raise_for_status()

    session_id = payload.langfuse_session_id or payload.external_session_id
    url = payload.langfuse_url
    if not url:
        url = f"{settings.langfuse_base_url.rstrip('/')}/trace/{trace_id}"
    return session_id, trace_id, url
