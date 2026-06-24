from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import ResponsibleOwner, User
from app.schemas import ResponsibleOwnerCreate, ResponsibleOwnerRead

router = APIRouter(prefix="/responsible-owners", tags=["responsible-owners"])


@router.get("", response_model=list[ResponsibleOwnerRead])
def list_responsible_owners(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ResponsibleOwner]:
    return list(db.scalars(select(ResponsibleOwner).order_by(ResponsibleOwner.name)))


@router.post("", response_model=ResponsibleOwnerRead)
def create_responsible_owner(
    payload: ResponsibleOwnerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    name = payload.name.strip()
    existing = db.scalar(select(ResponsibleOwner).where(ResponsibleOwner.name == name))
    if existing:
        return JSONResponse(
            content=jsonable_encoder(ResponsibleOwnerRead.model_validate(existing).model_dump()),
            status_code=200,
        )
    owner = ResponsibleOwner(name=name)
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return JSONResponse(
        content=jsonable_encoder(ResponsibleOwnerRead.model_validate(owner).model_dump()),
        status_code=201,
    )


@router.delete("/{owner_id}")
def delete_responsible_owner(
    owner_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    owner = db.get(ResponsibleOwner, owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Responsible owner not found")
    db.delete(owner)
    db.commit()
    return {"status": "ok"}
