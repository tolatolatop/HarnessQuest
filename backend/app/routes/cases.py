from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import cast, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import get_current_user
from app.models import AgentCase, AgentSession, AIAnalysis, AIAnalysisStatus, CaseEvent, CaseStatus, ExperienceItem, User
from app.queue import get_queue
from app.schemas import AIAnalysisFeedback, CaseCreate, CaseDetail, CaseEventCreate, CaseRead, CaseUpdate, ExperienceCreate, ExperienceRead
from app.services.analyzer import run_case_analysis

router = APIRouter(prefix="/cases", tags=["cases"])

ALLOWED_TRANSITIONS = {
    CaseStatus.to_triage: {CaseStatus.to_analyze, CaseStatus.in_progress, CaseStatus.closed},
    CaseStatus.to_analyze: {CaseStatus.in_progress, CaseStatus.to_verify, CaseStatus.closed},
    CaseStatus.in_progress: {CaseStatus.to_verify, CaseStatus.closed},
    CaseStatus.to_verify: {CaseStatus.in_progress, CaseStatus.closed},
    CaseStatus.closed: set(),
}


@router.get("", response_model=list[CaseRead])
def list_cases(
    status: CaseStatus | None = None,
    state: str | None = None,
    project_id: str | None = None,
    owner_id: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    tag: list[str] = Query(default_factory=list),
    q: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AgentCase]:
    stmt = select(AgentCase).order_by(AgentCase.created_at.desc()).limit(300)
    if status:
        stmt = stmt.where(AgentCase.status == status)
    if state == "open":
        stmt = stmt.where(AgentCase.status != CaseStatus.closed)
    elif state == "closed":
        stmt = stmt.where(AgentCase.status == CaseStatus.closed)
    if project_id:
        stmt = stmt.where(AgentCase.project_id == project_id)
    if owner_id:
        stmt = stmt.where(AgentCase.owner_id == owner_id)
    if created_from:
        stmt = stmt.where(AgentCase.created_at >= created_from)
    if created_to:
        stmt = stmt.where(AgentCase.created_at <= created_to)
    for item in tag:
        normalized = item.strip()
        if normalized:
            stmt = stmt.where(cast(AgentCase.tags, JSONB).contains([normalized]))
    if q:
        keyword = f"%{q.strip()}%"
        if keyword != "%%":
            stmt = stmt.where(
                or_(
                    AgentCase.title.ilike(keyword),
                    AgentCase.scene_description.ilike(keyword),
                    AgentCase.expected_result.ilike(keyword),
                    AgentCase.actual_result.ilike(keyword),
                    AgentCase.feedback_reporter.ilike(keyword),
                    AgentCase.responsible_owner.ilike(keyword),
                    AgentCase.closure_practice.ilike(keyword),
                    AgentCase.feedback_acceptance_conclusion.ilike(keyword),
                )
            )
    return list(db.scalars(stmt))


@router.post("", response_model=CaseRead)
def create_case(
    payload: CaseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentCase:
    data = payload.model_dump()
    if payload.session_id:
        session = db.get(AgentSession, payload.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if not data.get("project_id"):
            data["project_id"] = session.project_id
    case = AgentCase(**data, created_by_id=current_user.id)
    db.add(case)
    db.flush()
    db.add(CaseEvent(case_id=case.id, event_type="created", actor_id=current_user.id))
    db.commit()
    db.refresh(case)
    return case


@router.get("/experience", response_model=list[ExperienceRead])
def list_experience(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExperienceItem]:
    return list(db.scalars(select(ExperienceItem).order_by(ExperienceItem.created_at.desc()).limit(200)))


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: str, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AgentCase:
    case = db.scalar(
        select(AgentCase)
        .where(AgentCase.id == case_id)
        .options(selectinload(AgentCase.analyses), selectinload(AgentCase.events), selectinload(AgentCase.session))
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.patch("/{case_id}", response_model=CaseRead)
def update_case(
    case_id: str,
    payload: CaseUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentCase:
    case = db.get(AgentCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    before_status = case.status
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] != before_status:
        next_status = data["status"]
        if next_status not in ALLOWED_TRANSITIONS[before_status]:
            detail = f"Illegal transition {before_status.value} -> {next_status.value}"
            raise HTTPException(status_code=400, detail=detail)
        if next_status == CaseStatus.closed:
            case.closed_at = datetime.now(UTC)
    for key, value in data.items():
        setattr(case, key, value)
    db.add(
        CaseEvent(
            case_id=case.id,
            event_type="updated",
            actor_id=current_user.id,
            from_status=before_status.value,
            to_status=case.status.value,
            metadata_json=data,
        )
    )
    db.commit()
    db.refresh(case)
    return case


@router.post("/{case_id}/events")
def add_event(
    case_id: str,
    payload: CaseEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    case = db.get(AgentCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    db.add(
        CaseEvent(
            case_id=case.id,
            event_type=payload.event_type,
            actor_id=current_user.id,
            comment=payload.comment,
            metadata_json=payload.metadata,
        )
    )
    db.commit()
    return {"status": "ok"}


@router.post("/{case_id}/analyze", response_model=CaseRead)
def analyze_case(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentCase:
    case = db.get(AgentCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    case.ai_analysis_status = AIAnalysisStatus.running
    db.add(CaseEvent(case_id=case.id, event_type="analysis_requested", actor_id=current_user.id))
    db.commit()
    get_queue().enqueue(run_case_analysis, case.id)
    db.refresh(case)
    return case


@router.post("/{case_id}/analyses/{analysis_id}/feedback")
def save_analysis_feedback(
    case_id: str,
    analysis_id: str,
    payload: AIAnalysisFeedback,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    analysis = db.get(AIAnalysis, analysis_id)
    if not analysis or analysis.case_id != case_id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    analysis.human_feedback = payload.human_feedback
    db.add(
        CaseEvent(
            case_id=case_id,
            event_type="analysis_feedback",
            actor_id=current_user.id,
            comment=payload.human_feedback,
            metadata_json={"analysis_id": analysis_id, "human_feedback": payload.human_feedback},
        )
    )
    db.commit()
    return {"status": "ok"}


@router.post("/{case_id}/close", response_model=CaseRead)
def close_case(
    case_id: str,
    payload: CaseUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentCase:
    payload.status = CaseStatus.closed
    return update_case(case_id, payload, current_user, db)


@router.post("/{case_id}/experience", response_model=ExperienceRead)
def create_experience(
    case_id: str,
    payload: ExperienceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExperienceItem:
    case = db.get(AgentCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    item = ExperienceItem(
        source_case_id=case.id,
        type=payload.type,
        title=payload.title,
        content=payload.content,
        project_id=case.project_id,
        tags=payload.tags,
    )
    case.extracted_to_experience = True
    db.add(item)
    db.add(CaseEvent(case_id=case.id, event_type="experience_created", actor_id=current_user.id))
    db.commit()
    db.refresh(item)
    return item
