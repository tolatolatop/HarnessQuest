import httpx

from app.config import get_settings
from app.schemas import SessionImport


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
                    "metadata": {
                        "source": payload.source,
                        "repository": payload.repository,
                        "branch": payload.branch,
                        "commit_sha": payload.commit_sha,
                        **payload.metadata,
                    },
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
