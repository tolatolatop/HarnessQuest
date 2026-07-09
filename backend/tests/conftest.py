"""
Test fixtures for HarnessQuest backend tests.

Uses a file-based SQLite database (same file = same DB across connections).
Patches app.db at module level so the lifespan uses the test DB.
"""

import os
import tempfile

# Unique temp DB path — shared across the test run
_TEST_DB = tempfile.mktemp(suffix="_hq_test.db")
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_TEST_DB}"

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base, get_db
from app.dependencies import get_current_user
from app.main import app
from app.models import User, UserRole
from app.security import create_access_token, hash_password

# ---------------------------------------------------------------
# Single shared SQLite engine — file-based so all connections share
# ---------------------------------------------------------------
TEST_ENGINE = create_engine(
    f"sqlite+pysqlite:///{_TEST_DB}",
    connect_args={"check_same_thread": False},
)

@event.listens_for(TEST_ENGINE, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TEST_SESSION_LOCAL = sessionmaker(bind=TEST_ENGINE, autoflush=False, autocommit=False)

# ---------------------------------------------------------------
# Monkey-patch app.db.engine and app.main's local references
# ---------------------------------------------------------------
import app.db as app_db_module
app_db_module.engine = TEST_ENGINE
app_db_module.SessionLocal = TEST_SESSION_LOCAL

import app.main as app_main_module
app_main_module.engine = TEST_ENGINE
app_main_module.SessionLocal = TEST_SESSION_LOCAL


@pytest.fixture(autouse=True)
def _reset_db() -> Generator[None, None, None]:
    """Re-create all tables before every test for full isolation."""
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


def override_get_db() -> Generator[Session, None, None]:
    db = TEST_SESSION_LOCAL()
    try:
        yield db
    finally:
        db.close()


def _seed_admin(db: Session) -> User:
    admin = User(
        id="test-admin-id",
        email="admin@test.local",
        display_name="Test Admin",
        role=UserRole.admin,
        password_hash=hash_password("testpass"),
        is_active=True,
    )
    db.add(admin)
    db.commit()
    return admin


@pytest.fixture
def admin_token(db: Session) -> str:
    """Return a valid JWT for the seeded admin user."""
    user = _seed_admin(db)
    return create_access_token(user.id)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Provide a fresh SQLAlchemy session for each test."""
    session = TEST_SESSION_LOCAL()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(admin_token: str) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with overridden dependencies."""

    def _override_user() -> User | None:
        s = next(override_get_db())
        try:
            return s.get(User, "test-admin-id")
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = _override_user

    # Drop + recreate tables so TestClient lifespan sees a fresh DB
    Base.metadata.drop_all(bind=TEST_ENGINE)
    Base.metadata.create_all(bind=TEST_ENGINE)

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_db_file() -> Generator[None, None, None]:
    """Remove the temp DB file after the session."""
    yield
    try:
        os.unlink(_TEST_DB)
        os.unlink(_TEST_DB + "-wal")
        os.unlink(_TEST_DB + "-shm")
    except OSError:
        pass
