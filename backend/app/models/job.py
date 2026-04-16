from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String, default="pending", nullable=False)  # pending/running/complete/failed
    progress = Column(Integer, default=0, nullable=False)
    options_json = Column(String, nullable=False, default="{}")
    engine = Column(String, nullable=False, default="none")
    source_lang = Column(String, nullable=False)
    target_lang = Column(String, nullable=False)
    error_message = Column(String, nullable=True)
    task_id = Column(String, nullable=True)   # Celery AsyncResult.id — used for revocation
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True, index=True)
    original_filename = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
