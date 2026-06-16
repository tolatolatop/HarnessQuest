from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Project, User
from app.schemas import ProjectCreate, ProjectRead

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def list_projects(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.name)))


@router.post("", response_model=ProjectRead)
def create_project(
    payload: ProjectCreate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    existing = db.scalar(select(Project).where(Project.name == payload.name))
    if existing:
        raise HTTPException(status_code=409, detail="Project already exists")
    project = Project(name=payload.name, repository=payload.repository, default_owner_id=payload.default_owner_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project
