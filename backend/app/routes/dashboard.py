from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import AgentCase, AgentSession, AIAnalysis, CaseSeverity, CaseStatus, ExperienceItem, User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    total_sessions = db.scalar(select(func.count()).select_from(AgentSession)) or 0
    total_cases = db.scalar(select(func.count()).select_from(AgentCase)) or 0
    open_cases_query = select(func.count()).select_from(AgentCase).where(AgentCase.status != CaseStatus.closed)
    open_cases = db.scalar(open_cases_query) or 0
    closed_cases = total_cases - open_cases
    high_risk = (
        db.scalar(
            select(func.count())
            .select_from(AgentCase)
            .where(AgentCase.severity.in_([CaseSeverity.high, CaseSeverity.critical]))
        )
        or 0
    )
    experience_count = db.scalar(select(func.count()).select_from(ExperienceItem)) or 0
    feedback_count = db.scalar(select(func.count()).select_from(AIAnalysis).where(AIAnalysis.human_feedback.is_not(None))) or 0
    analysis_count = db.scalar(select(func.count()).select_from(AIAnalysis)) or 0
    avg_closure_seconds = (
        db.scalar(
            select(func.avg(func.extract("epoch", AgentCase.closed_at - AgentCase.created_at))).where(
                AgentCase.closed_at.is_not(None)
            )
        )
        or 0
    )
    closure_rate = closed_cases / total_cases if total_cases else 0
    return {
        "total_sessions": total_sessions,
        "total_cases": total_cases,
        "open_cases": open_cases,
        "closed_cases": closed_cases,
        "closure_rate": closure_rate,
        "high_risk_cases": high_risk,
        "experience_count": experience_count,
        "avg_closure_hours": round(float(avg_closure_seconds) / 3600, 2) if avg_closure_seconds else 0,
        "analysis_feedback_count": feedback_count,
        "analysis_acceptance_rate": feedback_count / analysis_count if analysis_count else 0,
    }


@router.get("/case-breakdown")
def case_breakdown(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    def grouped(column: Any) -> list[dict[str, Any]]:
        rows = db.execute(select(column, func.count()).select_from(AgentCase).group_by(column)).all()
        return [{"key": str(key.value if hasattr(key, "value") else key), "count": count} for key, count in rows]

    agent_rows = db.execute(select(AgentSession.agent_type, func.count()).group_by(AgentSession.agent_type)).all()
    repo_rows = db.execute(
        select(AgentSession.repository, func.count()).where(AgentSession.repository.is_not(None)).group_by(AgentSession.repository).limit(8)
    ).all()
    owner_rows = db.execute(
        select(AgentCase.responsible_owner, func.count())
        .where(AgentCase.responsible_owner.is_not(None))
        .group_by(AgentCase.responsible_owner)
        .limit(8)
    ).all()
    tag_counts: dict[str, int] = {}
    for tags in db.scalars(select(AgentCase.tags)):
        if isinstance(tags, list):
            for tag in tags:
                tag_counts[str(tag)] = tag_counts.get(str(tag), 0) + 1
    return {
        "by_status": grouped(AgentCase.status),
        "by_severity": grouped(AgentCase.severity),
        "by_problem_type": grouped(AgentCase.problem_type),
        "by_agent_type": [{"key": key or "unknown", "count": count} for key, count in agent_rows],
        "by_repository": [{"key": key or "unknown", "count": count} for key, count in repo_rows],
        "by_owner": [{"key": key or "unknown", "count": count} for key, count in owner_rows],
        "by_tag": [{"key": key, "count": count} for key, count in sorted(tag_counts.items(), key=lambda item: item[1], reverse=True)[:8]],
    }


@router.get("/trends")
def trends(days: int = 14, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    case_rows = db.execute(
        select(func.date(AgentCase.created_at), func.count())
        .where(AgentCase.created_at >= since)
        .group_by(func.date(AgentCase.created_at))
    ).all()
    session_rows = db.execute(
        select(func.date(AgentSession.created_at), func.count())
        .where(AgentSession.created_at >= since)
        .group_by(func.date(AgentSession.created_at))
    ).all()
    return {
        "cases": [{"date": str(day), "count": count} for day, count in case_rows],
        "sessions": [{"date": str(day), "count": count} for day, count in session_rows],
    }
