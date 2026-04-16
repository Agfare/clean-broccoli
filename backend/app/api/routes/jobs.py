from __future__ import annotations

import asyncio
import json
import logging
import shutil
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

log = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

redis_client = redis_lib.Redis.from_url(settings.REDIS_URL, decode_responses=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_job_files(job_id: str, user_id: str, db: Session) -> None:
    """Delete all storage files and UploadedFile records for *job_id*.

    Safe to call multiple times (idempotent).  Used both by the cancel
    endpoint (for pending jobs) and by the pipeline worker on cooperative
    cancellation.
    """
    # 1. Remove the entire job directory (inputs + outputs)
    job_dir = Path(settings.STORAGE_PATH) / str(user_id) / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
        log.info("cancel: removed job dir %s", job_dir)

    # 2. Remove uploaded input files that live outside the job dir
    db_files = db.query(UploadedFile).filter(UploadedFile.job_id == job_id).all()
    for db_file in db_files:
        try:
            p = Path(db_file.stored_path)
            if p.exists():
                p.unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(db_file)

    if db_files:
        db.commit()
        log.info("cancel: removed %d file record(s) for job %s", len(db_files), job_id)

    # 3. Delete Redis progress key
    redis_client.delete(f"job_progress:{job_id}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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
        target_lang=",".join(body.target_langs),
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

    # Launch Celery task and persist its ID for possible revocation
    async_result = run_pipeline.delay(job_id)
    job.task_id = async_result.id
    db.commit()
    log.info("job %s created; celery task_id=%s", job_id, job.task_id)

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


@router.post("/{job_id}/cancel", status_code=status.HTTP_200_OK)
def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a pending or running job.

    * **pending** — revoked from the Celery queue before it starts; files are
      cleaned up immediately.
    * **running** — marked cancelled in the DB; the worker detects the flag
      cooperatively and cleans up its own output files before exiting.
    * **complete / failed / cancelled** — returns 409 (nothing to cancel).
    """
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.status in ("complete", "failed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel a job with status '{job.status}'",
        )

    was_pending = job.status == "pending"
    old_status = job.status
    job.status = "cancelled"
    db.commit()
    log.info("cancel: job %s status %s → cancelled", job_id, old_status)

    # Revoke from Celery queue (effective for pending; no-op for running with solo pool)
    task_id = job.task_id
    if task_id:
        try:
            from app.workers.celery_app import celery_app
            celery_app.control.revoke(task_id, terminate=False)
            log.info("cancel: revoked celery task %s", task_id)
        except Exception as exc:
            log.warning("cancel: could not revoke task %s: %s", task_id, exc)

    # For pending jobs the worker will never run, so clean up here.
    # For running jobs the worker cleans up cooperatively when it detects cancellation.
    if was_pending:
        _cleanup_job_files(job_id, current_user.id, db)

    # Push a "cancelled" event so the SSE stream terminates immediately
    redis_client.set(
        f"job_progress:{job_id}",
        json.dumps({"step": "cancelled", "progress": 0, "message": "Job was cancelled"}),
        ex=300,
    )

    return {"status": "cancelled", "job_id": job_id}


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
                if data.get("step") in ("complete", "error", "cancelled"):
                    break
            else:
                # Redis key missing — fall back to DB for terminal state
                current_job = db.query(Job).filter(Job.id == job_id).first()
                if current_job and current_job.status in ("complete", "failed", "cancelled"):
                    if current_job.status == "complete":
                        step, pct, msg = "complete", 100, "Done"
                    elif current_job.status == "cancelled":
                        step, pct, msg = "cancelled", 0, "Job was cancelled"
                    else:
                        step, pct, msg = "error", 0, current_job.error_message or "Failed"
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
