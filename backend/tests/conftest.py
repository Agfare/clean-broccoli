"""Shared test fixtures for the TMClean backend test suite."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# ---------------------------------------------------------------------------
# In-memory SQLite database (isolated per test session)
# ---------------------------------------------------------------------------

from app.core.database import Base, get_db
from app.models.job import Job, UploadedFile  # noqa: F401 — register tables
from app.models.user import User              # noqa: F401

TEST_DB_URL = "sqlite://"  # pure in-memory, no file

_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
Base.metadata.create_all(bind=_engine)


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    """Yield a fresh DB session, rolling back after each test."""
    connection = _engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# ---------------------------------------------------------------------------
# FastAPI TestClient with overridden DB dependency
# ---------------------------------------------------------------------------

from app.main import app
from app.api.deps import get_current_user


@pytest.fixture()
def client(db: Session, test_user: User) -> TestClient:
    """TestClient with DB and auth injected.

    * Database dependency is overridden to use the test session so all
      operations share the same in-memory store.
    * Authentication is bypassed by overriding get_current_user to always
      return ``test_user``.
    """
    def _override_db():
        yield db

    def _override_user():
        return test_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def other_client(db: Session, other_user: User) -> TestClient:
    """TestClient authenticated as a *different* user (for 404-ownership tests)."""
    from app.core.database import get_db as _get_db

    def _override_db():
        yield db

    def _override_user():
        return other_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# User factories
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_user(db: Session) -> User:
    user = User(
        id=str(uuid.uuid4()),
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def other_user(db: Session) -> User:
    user = User(
        id=str(uuid.uuid4()),
        username="otheruser",
        email="other@example.com",
        hashed_password="hashed",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    return user


# ---------------------------------------------------------------------------
# Job factory
# ---------------------------------------------------------------------------

def make_job(
    db: Session,
    user: User,
    *,
    status: str = "pending",
    task_id: str | None = None,
) -> Job:
    """Insert a Job row and an associated UploadedFile row into *db*."""
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        user_id=user.id,
        status=status,
        progress=0,
        options_json="{}",
        engine="none",
        source_lang="en",
        target_lang="de",
        task_id=task_id or str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)

    # Attach a dummy uploaded-file record so cleanup code has something to find
    db_file = UploadedFile(
        id=str(uuid.uuid4()),
        user_id=user.id,
        job_id=job_id,
        original_filename="test.tmx",
        stored_path="/tmp/nonexistent_test.tmx",
        created_at=datetime.now(timezone.utc),
    )
    db.add(db_file)
    db.commit()
    return job
