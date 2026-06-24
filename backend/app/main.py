from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.migrations import ensure_agent_case_columns
from app.routes import auth, cases, dashboard, projects, sessions, uploads
from app.services.bootstrap import bootstrap_admin


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    ensure_agent_case_columns(engine)
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
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(uploads.router, prefix="/api/v1")

# Serve uploaded images at /api/v1/uploads/images/<filename>
upload_dir = Path(settings.upload_dir)
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/v1/uploads/images", StaticFiles(directory=str(upload_dir)), name="uploads")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
