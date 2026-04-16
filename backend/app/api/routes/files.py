from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.models.job import UploadedFile as DBUploadedFile
from app.models.user import User
from app.services.parsers.csv import detect_csv_languages
from app.services.parsers.tmx import detect_tmx_languages
from app.services.parsers.xls import detect_xls_languages

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_EXTENSIONS = {".tmx", ".xls", ".xlsx", ".csv"}
_SPOOL_CHUNK = 1024 * 1024  # 1 MB read chunks when copying from spool to final path


def _validate_xml_file(path: Path) -> bool:
    """Quick well-formedness check using a streaming parser — no full DOM load."""
    try:
        from lxml import etree

        context = etree.iterparse(str(path), events=("start",), recover=False)
        next(iter(context))
        return True
    except Exception:
        return False


def _check_encoding(path: Path) -> str:
    """Sample the first 8 KB to detect encoding without reading the whole file."""
    with open(path, "rb") as f:
        sample = f.read(8192)
    try:
        sample.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


@router.post("/upload")
async def upload_files(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024

    # Starlette 0.36+ defaults max_part_size to 1 MB, silently killing large uploads.
    # We pass our own limit here so the form parser accepts files up to MAX_FILE_SIZE_MB.
    try:
        # max_part_size is set globally via MultiPartParser.max_file_size in main.py
        # (Starlette 0.36+). We only pass the stable cross-version parameters here.
        form = await request.form(max_fields=100, max_files=20)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not parse upload form: {exc}",
        ) from exc

    raw_files = form.getlist("files")
    if not raw_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided",
        )

    upload_dir = Path(settings.STORAGE_PATH) / str(current_user.id) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for upload in raw_files:
        if not isinstance(upload, UploadFile):
            continue

        warnings: list[str] = []
        filename = upload.filename or "unknown"
        ext = Path(filename).suffix.lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{filename}' has unsupported extension '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        # ── Stream spool → final path, enforcing size limit ───────────────────
        file_id = str(uuid.uuid4())
        stored_name = f"{file_id}_{filename}"
        stored_path = upload_dir / stored_name

        total_bytes = 0
        try:
            with open(stored_path, "wb") as f:
                while True:
                    chunk = await upload.read(_SPOOL_CHUNK)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        stored_path.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"File '{filename}' exceeds maximum size of {settings.MAX_FILE_SIZE_MB} MB",
                        )
                    f.write(chunk)
        except HTTPException:
            raise
        except Exception as exc:
            stored_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save '{filename}': {exc}",
            ) from exc

        # ── Encoding check (sample only) ──────────────────────────────────────
        encoding = _check_encoding(stored_path)
        if encoding != "utf-8":
            warnings.append(f"'{filename}' is not UTF-8 encoded; detected as latin-1")

        # ── XML validation for TMX files (streaming, no full DOM) ─────────────
        if ext == ".tmx":
            if not _validate_xml_file(stored_path):
                stored_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File '{filename}' is not well-formed XML",
                )

        # ── Language detection ────────────────────────────────────────────────
        detected_languages: list[str] = []
        try:
            if ext == ".tmx":
                detected_languages = detect_tmx_languages(stored_path)
            elif ext in (".xls", ".xlsx"):
                detected_languages = detect_xls_languages(stored_path)
            elif ext == ".csv":
                detected_languages = detect_csv_languages(stored_path)
        except Exception:
            pass

        # ── Persist record ────────────────────────────────────────────────────
        db_file = DBUploadedFile(
            id=file_id,
            user_id=current_user.id,
            job_id=None,
            original_filename=filename,
            stored_path=str(stored_path),
            created_at=datetime.now(timezone.utc),
        )
        db.add(db_file)
        db.commit()

        results.append(
            {
                "file_id": file_id,
                "filename": filename,
                "size": total_bytes,
                "warnings": warnings,
                "detected_languages": detected_languages,
            }
        )

    return results
