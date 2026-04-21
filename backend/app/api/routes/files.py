from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.api.deps import get_current_user, get_db
from app.constants import PREVIEW_LIMIT_DEFAULT, PREVIEW_LIMIT_MAX
from app.core.config import settings
from app.models.job import UploadedFile as DBUploadedFile
from app.models.user import User
from app.schemas.file import PreviewResponse, PreviewSegment
from app.services.parsers.csv import detect_csv_languages, iter_csv
from app.services.parsers.tmx import detect_tmx_languages, iter_tmx
from app.services.parsers.xls import detect_xls_languages, iter_xls

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


# ---------------------------------------------------------------------------
# Preview helpers
# ---------------------------------------------------------------------------

def _detect_langs(path: Path, ext: str) -> list[str]:
    """Return detected language codes for *path* based on its file extension."""
    try:
        if ext == ".tmx":
            return detect_tmx_languages(path)
        if ext in (".xls", ".xlsx"):
            return detect_xls_languages(path)
        if ext == ".csv":
            return detect_csv_languages(path)
    except Exception:
        pass
    return []


def _preview_segments(
    path: Path,
    ext: str,
    source_lang: str,
    target_lang: str,
    limit: int,
    warnings: list[str],
) -> List[PreviewSegment]:
    """Stream up to *limit* segments from *path* and return as PreviewSegments."""
    try:
        if ext == ".tmx":
            iterator = iter_tmx(path, source_lang, target_lang, warnings=warnings)
        elif ext in (".xls", ".xlsx"):
            iterator = iter_xls(path, source_lang, target_lang, warnings=warnings)
        elif ext == ".csv":
            iterator = iter_csv(path, source_lang, target_lang, warnings=warnings)
        else:
            warnings.append(f"Unsupported file type: {ext}")
            return []
    except Exception as exc:
        warnings.append(f"Could not open file for preview: {exc}")
        return []

    results: List[PreviewSegment] = []
    for seg in iterator:
        results.append(PreviewSegment(id=str(seg.id), source=seg.source, target=seg.target))
        if len(results) >= limit:
            break
    return results


# ---------------------------------------------------------------------------
# Preview endpoint
# ---------------------------------------------------------------------------

@router.get("/{file_id}/preview", response_model=PreviewResponse)
def preview_file(
    file_id: str,
    limit: int = Query(default=PREVIEW_LIMIT_DEFAULT, ge=1, le=PREVIEW_LIMIT_MAX),
    source_lang: Optional[str] = Query(default=None),
    target_lang: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the first *limit* segments of an uploaded file for preview.

    *source_lang* and *target_lang* are optional.  When omitted, the endpoint
    auto-detects the language pair from the file itself using the same language
    detection logic used at upload time.
    """
    db_file = db.query(DBUploadedFile).filter(
        DBUploadedFile.id == file_id,
        DBUploadedFile.user_id == current_user.id,
    ).first()
    if not db_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    path = Path(db_file.stored_path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File no longer exists on disk",
        )

    ext = Path(db_file.original_filename).suffix.lower()

    # Auto-detect languages when caller did not supply them
    if not source_lang or not target_lang:
        langs = _detect_langs(path, ext)
        source_lang = source_lang or (langs[0] if len(langs) > 0 else "en")
        target_lang  = target_lang  or (langs[1] if len(langs) > 1 else source_lang)

    warnings: list[str] = []
    segments = _preview_segments(path, ext, source_lang, target_lang, limit, warnings)

    return PreviewResponse(
        file_id=file_id,
        filename=db_file.original_filename,
        source_lang=source_lang,
        target_lang=target_lang,
        segments=segments,
        warnings=warnings,
    )
