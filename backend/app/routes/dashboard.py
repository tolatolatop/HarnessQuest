from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import AgentCase, AgentSession, CaseSeverity, CaseStatus, ExperienceItem, User

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
    closure_rate = closed_cases / total_cases if total_cases else 0
    return {
        "total_sessions": total_sessions,
        "total_cases": total_cases,
        "open_cases": open_cases,
        "closed_cases": closed_cases,
        "closure_rate": closure_rate,
        "high_risk_cases": high_risk,
        "experience_count": experience_count,
    }


@router.get("/case-breakdown")
def case_breakdown(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    def grouped(column: Any) -> list[dict[str, Any]]:
        rows = db.execute(select(column, func.count()).select_from(AgentCase).group_by(column)).all()
        return [{"key": str(key.value if hasattr(key, "value") else key), "count": count} for key, count in rows]

    agent_rows = db.execute(select(AgentSession.agent_type, func.count()).group_by(AgentSession.agent_type)).all()
    return {
        "by_status": grouped(AgentCase.status),
        "by_severity": grouped(AgentCase.severity),
        "by_problem_type": grouped(AgentCase.problem_type),
        "by_agent_type": [{"key": key or "unknown", "count": count} for key, count in agent_rows],
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
