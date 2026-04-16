from __future__ import annotations

from celery import Celery
from celery.signals import worker_ready

from app.core.config import settings

celery_app = Celery(
    "tmclean",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.pipeline"],
)

celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "UTC"
celery_app.conf.enable_utc = True


# ---------------------------------------------------------------------------
# Worker startup: reset any jobs that were left in "running" state from a
# previous worker crash (OOM kill, Ctrl-C, etc.).  Without this, those jobs
# stay stuck at "running" forever and — more critically — their Celery tasks
# may still be sitting in the Redis queue.  When the worker restarts it picks
# them up again, causing the same crash on the same file in a tight loop.
# ---------------------------------------------------------------------------

@worker_ready.connect
def _reset_stuck_jobs(sender, **kwargs) -> None:  # noqa: ANN001
    """Mark abandoned 'running' jobs as failed so they don't re-crash the worker."""
    try:
        from app.core.database import SessionLocal, init_db
        from app.models.job import Job
        init_db()
        db = SessionLocal()
        try:
            stuck = db.query(Job).filter(Job.status == "running").all()
            if stuck:
                print(
                    f"[startup] Resetting {len(stuck)} stuck job(s) to 'failed': "
                    + ", ".join(j.id for j in stuck)
                )
            for job in stuck:
                job.status = "failed"
                job.error_message = (
                    "Worker restarted while job was running — "
                    "the previous worker process was killed (likely OOM). "
                    "Please re-submit the job."
                )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        print(f"[startup] Failed to reset stuck jobs: {exc}")
