from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.models.job import Job, UploadedFile
from app.models.user import User
from app.schemas.job import CreateJobRequest, JobResponse, JobResultsResponse, ResultFile

router = APIRouter(prefix="/jobs", tags=["jobs"])

redis_client = redis_lib.Redis.from_url(settings.REDIS_URL, decode_responses=True)


@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    body: CreateJobRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.workers.pipeline import run_pipeline

    # Verify all files belong to this user
    for file_id in body.file_ids:
        db_file = db.query(UploadedFile).filter(
            UploadedFile.id == file_id, UploadedFile.user_id == current_user.id
        ).first()
        if not db_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File '{file_id}' not found or does not belong to you",
            )

    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        user_id=current_user.id,
        status="pending",
        progress=0,
        options_json=body.options.model_dump_json(),
        engine=body.engine,
        source_lang=body.source_lang,
        target_lang=body.target_lang,
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)

    # Associate files with this job
    for file_id in body.file_ids:
        db_file = db.query(UploadedFile).filter(UploadedFile.id == file_id).first()
        if db_file:
            db_file.job_id = job_id

    db.commit()
    db.refresh(job)

    # Launch Celery task
    run_pipeline.delay(job_id)

    return job


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.get("/{job_id}/stream")
async def stream_job(
    job_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    async def event_generator() -> AsyncGenerator[dict, None]:
        redis_key = f"job_progress:{job_id}"
        while True:
            if await request.is_disconnected():
                break

            raw = redis_client.get(redis_key)
            if raw:
                data = json.loads(raw)
                yield {"data": json.dumps(data)}
                if data.get("step") in ("complete", "error"):
                    break
            else:
                # Check DB for terminal state
                session = db
                current_job = session.query(Job).filter(Job.id == job_id).first()
                if current_job and current_job.status in ("complete", "failed"):
                    step = "complete" if current_job.status == "complete" else "error"
                    pct = 100 if step == "complete" else 0
                    msg = "Done" if step == "complete" else (current_job.error_message or "Failed")
                    yield {"data": json.dumps({"step": step, "progress": pct, "message": msg})}
                    break

            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


@router.get("/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    output_dir = Path(settings.STORAGE_PATH) / str(current_user.id) / job_id / "output"

    outputs = []
    if output_dir.exists():
        for f in sorted(output_dir.iterdir()):
            if f.is_file():
                ext = f.suffix.lower()
                if ext == ".tmx":
                    ftype = "tmx"
                elif ext in (".xls", ".xlsx"):
                    ftype = "xls"
                elif ext == ".html":
                    ftype = "html"
                else:
                    ftype = "other"
                outputs.append(
                    ResultFile(
                        type=ftype,
                        filename=f.name,
                        download_url=f"/api/jobs/{job_id}/download/{f.name}",
                    )
                )

    return JobResultsResponse(job_id=job_id, outputs=outputs)


@router.get("/{job_id}/download/{filename}")
def download_file(
    job_id: str,
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    output_dir = Path(settings.STORAGE_PATH) / str(current_user.id) / job_id / "output"
    file_path = output_dir / filename

    # Prevent path traversal
    try:
        file_path.resolve().relative_to(output_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    return FileResponse(path=str(file_path), filename=filename)
