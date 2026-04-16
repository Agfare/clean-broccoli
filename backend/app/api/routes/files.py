from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.models.job import UploadedFile
from app.models.user import User
from app.services.parsers.csv import detect_csv_languages
from app.services.parsers.tmx import detect_tmx_languages
from app.services.parsers.xls import detect_xls_languages

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_EXTENSIONS = {".tmx", ".xls", ".xlsx", ".csv"}


def _validate_xml(content: bytes) -> bool:
    try:
        from lxml import etree
        etree.fromstring(content)
        return True
    except Exception:
        return False


@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    results = []

    upload_dir = Path(settings.STORAGE_PATH) / str(current_user.id) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    for upload in files:
        warnings = []
        filename = upload.filename or "unknown"
        ext = Path(filename).suffix.lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{filename}' has unsupported extension '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        content = await upload.read()

        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File '{filename}' exceeds maximum size of {settings.MAX_FILE_SIZE_MB} MB",
            )

        # Check encoding
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content.decode("latin-1")
                warnings.append(f"'{filename}' is not UTF-8 encoded; detected as latin-1")
            except UnicodeDecodeError:
                warnings.append(f"'{filename}' encoding could not be determined")

        # Validate XML for TMX files
        if ext == ".tmx":
            if not _validate_xml(content):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File '{filename}' is not well-formed XML",
                )

        file_id = str(uuid.uuid4())
        stored_name = f"{file_id}_{filename}"
        stored_path = str(upload_dir / stored_name)

        with open(stored_path, "wb") as f:
            f.write(content)

        # Detect languages from file
        detected_languages: list[str] = []
        try:
            fpath_obj = Path(stored_path)
            if ext == ".tmx":
                detected_languages = detect_tmx_languages(fpath_obj)
            elif ext in (".xls", ".xlsx"):
                detected_languages = detect_xls_languages(fpath_obj)
            elif ext == ".csv":
                detected_languages = detect_csv_languages(fpath_obj)
        except Exception:
            pass

        db_file = UploadedFile(
            id=file_id,
            user_id=current_user.id,
            job_id=None,
            original_filename=filename,
            stored_path=stored_path,
            created_at=datetime.now(timezone.utc),
        )
        db.add(db_file)
        db.commit()

        results.append(
            {
                "file_id": file_id,
                "filename": filename,
                "size": len(content),
                "warnings": warnings,
                "detected_languages": detected_languages,
            }
        )

    return results
