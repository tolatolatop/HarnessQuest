from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User, UserRole
from app.security import hash_password


def bootstrap_admin(db: Session) -> None:
    settings = get_settings()
    existing = db.scalar(select(User).where(User.email == settings.bootstrap_admin_email))
    if existing:
        return
    admin = User(
        email=settings.bootstrap_admin_email,
        display_name=settings.bootstrap_admin_name,
        password_hash=hash_password(settings.bootstrap_admin_password),
        role=UserRole.admin,
    )
    db.add(admin)
    db.commit()

