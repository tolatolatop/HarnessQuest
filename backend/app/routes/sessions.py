import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import AgentSession, Project, User
from app.schemas import SessionImport, SessionRead
from app.services.claude_jsonl import convert_claude_jsonl_content
from app.services.langfuse import write_langfuse_trace
from app.services.opencode_export import convert_opencode_export_content
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
    return await _persist_session(payload, current_user, db, update_existing=False)


@router.put("/import", response_model=SessionRead)
async def update_imported_session(
    payload: SessionImport,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSession:
    return await _persist_session(payload, current_user, db, update_existing=True)


async def _persist_session(
    payload: SessionImport,
    current_user: User,
    db: Session,
    *,
    update_existing: bool,
) -> AgentSession:
    existing = _find_existing_session(payload, db)
    if existing and not update_existing:
        raise HTTPException(status_code=409, detail={"message": "Session already exists", "session_id": existing.id})
    if update_existing and not existing:
        if not _session_identity(payload):
            raise HTTPException(status_code=400, detail="Session id is required for PUT updates")
        raise HTTPException(status_code=404, detail="Session not found")

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

    session = existing or AgentSession()
    session.external_session_id = payload.external_session_id
    session.langfuse_session_id = langfuse_session_id
    session.langfuse_trace_id = langfuse_trace_id
    session.langfuse_url = langfuse_url
    session.agent_type = payload.agent_type
    session.user_id = user.id if user else None
    session.project_id = project.id if project else None
    session.repository = payload.repository
    session.branch = payload.branch
    session.commit_sha = payload.commit_sha
    session.started_at = payload.started_at
    session.ended_at = payload.ended_at
    session.source = payload.source
    session.raw_artifact_uri = raw_uri
    session.summary = payload.summary
    session.metadata_json = {
        **payload.metadata,
        "user_input": payload.user_input,
        "assistant_output": payload.assistant_output,
        "tool_calls": payload.tool_calls,
        "shell_commands": payload.shell_commands,
        "file_edits": payload.file_edits,
        "errors": payload.errors,
        "git_diff": payload.git_diff,
    }
    if not existing:
        db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _find_existing_session(payload: SessionImport, db: Session) -> AgentSession | None:
    identity = _session_identity(payload)
    if not identity:
        return None
    field, value = identity
    column = AgentSession.external_session_id if field == "external_session_id" else AgentSession.langfuse_session_id
    return db.scalar(select(AgentSession).where(column == value).order_by(AgentSession.created_at.desc()))


def _session_identity(payload: SessionImport) -> tuple[str, str] | None:
    if payload.external_session_id:
        return ("external_session_id", payload.external_session_id)
    if payload.langfuse_session_id:
        return ("langfuse_session_id", payload.langfuse_session_id)
    return None


@router.post("/upload", response_model=SessionRead)
async def upload_session_file(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSession:
    payload = await _parse_harnessquest_upload(file)
    return await import_session(payload, current_user, db)


@router.put("/upload", response_model=SessionRead)
async def update_session_file(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSession:
    payload = await _parse_harnessquest_upload(file)
    return await update_imported_session(payload, current_user, db)


async def _parse_harnessquest_upload(file: UploadFile) -> SessionImport:
    content = await file.read()
    try:
        return SessionImport.model_validate(json.loads(content.decode("utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}") from exc


@router.post("/upload/auto", response_model=SessionRead)
async def upload_auto_session_file(
    file: UploadFile,
    project_name: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSession:
    payload = await _parse_auto_upload(file, project_name, current_user)
    return await import_session(payload, current_user, db)


@router.put("/upload/auto", response_model=SessionRead)
async def update_auto_session_file(
    file: UploadFile,
    project_name: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSession:
    payload = await _parse_auto_upload(file, project_name, current_user)
    return await update_imported_session(payload, current_user, db)


async def _parse_auto_upload(file: UploadFile, project_name: str | None, current_user: User) -> SessionImport:
    content = await file.read()
    text = content.decode("utf-8")
    filename = file.filename or "agent-session"
    errors: list[str] = []

    if _looks_like_claude_jsonl(text):
        try:
            payload_data = convert_claude_jsonl_content(
                text,
                source_name=filename,
                project_name=project_name,
                user_email=current_user.email,
            )
            return SessionImport.model_validate(payload_data)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Claude Code JSONL: {exc}")

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            if _looks_like_opencode_json(data):
                try:
                    payload_data = convert_opencode_export_content(
                        text,
                        source_name=filename,
                        project_name=project_name,
                        user_email=current_user.email,
                    )
                    return SessionImport.model_validate(payload_data)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"opencode JSON: {exc}")
            try:
                return SessionImport.model_validate(data)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"HarnessQuest JSON: {exc}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"JSON object: {exc}")

    detail = (
        "Unable to identify session record format. Supported formats: "
        "Claude Code JSONL, opencode JSON export, HarnessQuest JSON."
    )
    if errors:
        detail = f"{detail} Tried: {'; '.join(errors)}"
    raise HTTPException(status_code=400, detail=detail)


@router.post("/upload/claude-jsonl", response_model=SessionRead)
async def upload_claude_jsonl_file(
    file: UploadFile,
    project_name: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSession:
    payload = await _parse_claude_jsonl_upload(file, project_name, current_user)
    return await import_session(payload, current_user, db)


@router.put("/upload/claude-jsonl", response_model=SessionRead)
async def update_claude_jsonl_file(
    file: UploadFile,
    project_name: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSession:
    payload = await _parse_claude_jsonl_upload(file, project_name, current_user)
    return await update_imported_session(payload, current_user, db)


async def _parse_claude_jsonl_upload(file: UploadFile, project_name: str | None, current_user: User) -> SessionImport:
    content = await file.read()
    try:
        payload_data = convert_claude_jsonl_content(
            content.decode("utf-8"),
            source_name=file.filename or "claude-session.jsonl",
            project_name=project_name,
            user_email=current_user.email,
        )
        return SessionImport.model_validate(payload_data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Claude Code JSONL payload: {exc}") from exc


def _looks_like_claude_jsonl(content: str) -> bool:
    seen = 0
    for line in content.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            return False
        if not isinstance(row, dict):
            return False
        seen += 1
        if row.get("sessionId") and row.get("type") in {"user", "assistant", "system"}:
            return True
        if row.get("message") and row.get("type") in {"user", "assistant"}:
            return True
    return seen > 1


def _looks_like_opencode_json(data: dict[str, Any]) -> bool:
    session = data.get("session") or data.get("info")
    messages = data.get("messages") or data.get("message") or data.get("conversation")
    if isinstance(session, dict) and isinstance(messages, list):
        return True
    if isinstance(messages, list):
        return any(
            isinstance(item, dict) and isinstance(item.get("info"), dict) and isinstance(item.get("parts"), list)
            for item in messages
        )
    return False


@router.post("/upload/opencode-json", response_model=SessionRead)
async def upload_opencode_json_file(
    file: UploadFile,
    project_name: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSession:
    payload = await _parse_opencode_json_upload(file, project_name, current_user)
    return await import_session(payload, current_user, db)


@router.put("/upload/opencode-json", response_model=SessionRead)
async def update_opencode_json_file(
    file: UploadFile,
    project_name: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSession:
    payload = await _parse_opencode_json_upload(file, project_name, current_user)
    return await update_imported_session(payload, current_user, db)


async def _parse_opencode_json_upload(file: UploadFile, project_name: str | None, current_user: User) -> SessionImport:
    content = await file.read()
    try:
        payload_data = convert_opencode_export_content(
            content.decode("utf-8"),
            source_name=file.filename or "opencode-session.json",
            project_name=project_name,
            user_email=current_user.email,
        )
        return SessionImport.model_validate(payload_data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid opencode JSON export payload: {exc}") from exc
