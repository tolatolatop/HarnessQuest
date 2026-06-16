from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import AgentSession, Project, User
from app.schemas import SessionImport, SessionRead
from app.services.langfuse import write_langfuse_trace
from app.services.storage import ObjectStorage

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionRead])
def list_sessions(
    project_id: str | None = None,
    agent_type: str | None = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AgentSession]:
    stmt = select(AgentSession).order_by(AgentSession.created_at.desc()).limit(200)
    if project_id:
        stmt = stmt.where(AgentSession.project_id == project_id)
    if agent_type:
        stmt = stmt.where(AgentSession.agent_type == agent_type)
    return list(db.scalars(stmt))


@router.get("/{session_id}", response_model=SessionRead)
def get_session(session_id: str, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AgentSession:
    session = db.get(AgentSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/{session_id}/raw")
def get_session_raw(
    session_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    session = db.get(AgentSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.raw_artifact_uri:
        raise HTTPException(status_code=404, detail="Session raw artifact not found")
    try:
        return ObjectStorage().get_json(session.raw_artifact_uri)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to read session artifact: {exc}") from exc


@router.post("/import", response_model=SessionRead)
async def import_session(
    payload: SessionImport,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSession:
    user = current_user
    if payload.user_email:
        user = db.scalar(select(User).where(User.email == payload.user_email)) or current_user

    project = None
    if payload.project_name:
        project = db.scalar(select(Project).where(Project.name == payload.project_name))
        if not project:
            project = Project(name=payload.project_name, repository=payload.repository)
            db.add(project)
            db.flush()

    raw_payload: dict[str, Any] = payload.raw or payload.model_dump(mode="json")
    raw_uri = ObjectStorage().put_json("sessions", raw_payload)

    langfuse_session_id = payload.langfuse_session_id
    langfuse_trace_id = payload.langfuse_trace_id
    langfuse_url = payload.langfuse_url
    try:
        langfuse_session_id, langfuse_trace_id, langfuse_url = await write_langfuse_trace(payload)
    except Exception as exc:  # noqa: BLE001
        payload.metadata["langfuse_write_warning"] = str(exc)

    session = AgentSession(
        external_session_id=payload.external_session_id,
        langfuse_session_id=langfuse_session_id,
        langfuse_trace_id=langfuse_trace_id,
        langfuse_url=langfuse_url,
        agent_type=payload.agent_type,
        user_id=user.id,
        project_id=project.id if project else None,
        repository=payload.repository,
        branch=payload.branch,
        commit_sha=payload.commit_sha,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        source=payload.source,
        raw_artifact_uri=raw_uri,
        summary=payload.summary,
        metadata_json={
            **payload.metadata,
            "user_input": payload.user_input,
            "assistant_output": payload.assistant_output,
            "tool_calls": payload.tool_calls,
            "shell_commands": payload.shell_commands,
            "file_edits": payload.file_edits,
            "errors": payload.errors,
            "git_diff": payload.git_diff,
        },
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/upload", response_model=SessionRead)
async def upload_session_file(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSession:
    import json

    content = await file.read()
    try:
        payload = SessionImport.model_validate(json.loads(content.decode("utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}") from exc
    return await import_session(payload, current_user, db)
