"""Storage and job cleanup utilities.

Usage (run from the backend directory):

    python -m app.workers.cleanup --help
    python -m app.workers.cleanup --dry-run        # show what would be deleted
    python -m app.workers.cleanup                  # delete files + reset DB records
    python -m app.workers.cleanup --days 3         # keep files newer than 3 days (default: 7)
    python -m app.workers.cleanup --purge-queue    # also purge all pending Celery tasks
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path


def cleanup_storage(
    days: int = 7,
    dry_run: bool = False,
    purge_queue: bool = False,
) -> None:
    from app.core.config import settings
    from app.core.database import SessionLocal, init_db
    from app.models.job import Job, UploadedFile

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    storage_root = Path(settings.STORAGE_PATH)

    init_db()
    db = SessionLocal()
    try:
        # ------------------------------------------------------------------
        # 1. Reset any jobs stuck in "running" state
        # ------------------------------------------------------------------
        stuck_jobs = db.query(Job).filter(Job.status == "running").all()
        for job in stuck_jobs:
            print(f"  [stuck] job {job.id} created {job.created_at} → resetting to 'failed'")
            if not dry_run:
                job.status = "failed"
                job.error_message = "Reset by cleanup utility — worker was killed mid-run."

        # ------------------------------------------------------------------
        # 2. Find old completed/failed jobs whose files can be removed
        # ------------------------------------------------------------------
        old_jobs = (
            db.query(Job)
            .filter(
                Job.status.in_(["complete", "failed"]),
                Job.created_at < cutoff,
            )
            .all()
        )

        total_freed = 0
        for job in old_jobs:
            job_dir = storage_root / str(job.user_id) / job.id
            if job_dir.exists():
                size = sum(f.stat().st_size for f in job_dir.rglob("*") if f.is_file())
                total_freed += size
                print(
                    f"  [old job] {job.id} ({job.status}, "
                    f"created {job.created_at:%Y-%m-%d}) — "
                    f"{size // 1024:,} KB  {'(dry run)' if dry_run else '→ deleted'}"
                )
                if not dry_run:
                    shutil.rmtree(job_dir, ignore_errors=True)
                    # Remove file records from DB
                    db.query(UploadedFile).filter(
                        UploadedFile.job_id == job.id
                    ).delete()
            else:
                print(
                    f"  [old job] {job.id} ({job.status}) — no files on disk (already cleaned?)"
                )

        # ------------------------------------------------------------------
        # 3. Orphaned user dirs (no matching job) — safety check only
        # ------------------------------------------------------------------
        if storage_root.exists():
            for user_dir in storage_root.iterdir():
                if not user_dir.is_dir() or user_dir.name == "crash_log.txt":
                    continue
                for job_dir in user_dir.iterdir():
                    if not job_dir.is_dir():
                        continue
                    job = db.query(Job).filter(Job.id == job_dir.name).first()
                    if job is None:
                        size = sum(
                            f.stat().st_size
                            for f in job_dir.rglob("*") if f.is_file()
                        )
                        total_freed += size
                        print(
                            f"  [orphan ] {job_dir}  "
                            f"{size // 1024:,} KB  {'(dry run)' if dry_run else '→ deleted'}"
                        )
                        if not dry_run:
                            shutil.rmtree(job_dir, ignore_errors=True)

        if not dry_run:
            db.commit()

        print(
            f"\nDone.  {'Would free' if dry_run else 'Freed'} "
            f"~{total_freed // (1024 * 1024):,} MB."
        )

        # ------------------------------------------------------------------
        # 4. Optionally purge the Celery Redis queue
        # ------------------------------------------------------------------
        if purge_queue:
            from app.workers.celery_app import celery_app
            count = celery_app.control.purge()
            print(f"Celery queue purged — {count} task(s) discarded.")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TMClean storage cleanup")
    parser.add_argument(
        "--days", type=int, default=7,
        help="Delete files from jobs older than N days (default: 7)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be deleted without actually deleting anything",
    )
    parser.add_argument(
        "--purge-queue", action="store_true",
        help="Also purge all pending tasks from the Celery Redis queue",
    )
    args = parser.parse_args()
    cleanup_storage(days=args.days, dry_run=args.dry_run, purge_queue=args.purge_queue)
