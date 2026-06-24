from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.migrations import ensure_agent_case_columns, ensure_responsible_owners_table
from app.routes import auth, cases, dashboard, projects, responsible_owners, sessions, uploads
from app.services.bootstrap import bootstrap_admin


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    ensure_agent_case_columns(engine)
    ensure_responsible_owners_table(engine)
    db = SessionLocal()
    try:
        bootstrap_admin(db)
    finally:
        db.close()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(cases.router, prefix="/api/v1")
app.include_router(responsible_owners.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(uploads.router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
