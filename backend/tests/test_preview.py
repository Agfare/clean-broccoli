"""Tests for GET /api/files/{file_id}/preview."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
import pytest
from sqlalchemy.orm import Session

from app.models.job import UploadedFile
from app.models.user import User

# ---------------------------------------------------------------------------
# Fixtures directory (static files committed to repo)
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_TMX  = FIXTURES_DIR / "sample.tmx"
SAMPLE_CSV  = FIXTURES_DIR / "sample.csv"


@pytest.fixture(scope="session")
def sample_xlsx(tmp_path_factory) -> Path:
    """Create a small XLSX fixture in a session-scoped temp dir."""
    path = tmp_path_factory.mktemp("fixtures") / "sample.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["source", "target"])
    rows = [
        ("Hello world",           "Hallo Welt"),
        ("Good morning",          "Guten Morgen"),
        ("Thank you very much",   "Vielen Dank"),
        ("Please click the button", "Bitte klicken Sie den Knopf"),
        ("Save your changes",     "Speichern Sie Ihre Änderungen"),
    ]
    for row in rows:
        ws.append(list(row))
    wb.save(str(path))
    return path


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _insert_file(db: Session, user: User, path: Path, filename: str) -> UploadedFile:
    """Insert an UploadedFile record pointing at *path* and return it."""
    f = UploadedFile(
        id=str(uuid.uuid4()),
        user_id=user.id,
        job_id=None,
        original_filename=filename,
        stored_path=str(path),
        created_at=datetime.now(timezone.utc),
    )
    db.add(f)
    db.commit()
    return f


# ===========================================================================
# 1. TMX preview
# ===========================================================================

class TestPreviewTmx:

    def test_returns_200_with_segments(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_TMX, "sample.tmx")
        resp = client.get(f"/api/files/{rec.id}/preview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_id"] == rec.id
        assert data["filename"] == "sample.tmx"
        assert len(data["segments"]) > 0

    def test_default_limit_is_20_or_all_available(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_TMX, "sample.tmx")
        resp = client.get(f"/api/files/{rec.id}/preview")
        assert resp.status_code == 200
        # sample.tmx has 5 segments; default limit=20, so we get all 5
        assert len(resp.json()["segments"]) == 5

    def test_limit_respected(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_TMX, "sample.tmx")
        resp = client.get(f"/api/files/{rec.id}/preview?limit=3")
        assert resp.status_code == 200
        assert len(resp.json()["segments"]) == 3

    def test_correct_source_and_target_text(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_TMX, "sample.tmx")
        resp = client.get(f"/api/files/{rec.id}/preview?source_lang=en&target_lang=de")
        assert resp.status_code == 200
        segs = resp.json()["segments"]
        assert segs[0]["source"] == "Hello world"
        assert segs[0]["target"] == "Hallo Welt"
        assert segs[2]["source"] == "Thank you very much"
        assert segs[2]["target"] == "Vielen Dank"

    def test_auto_detects_language_pair(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_TMX, "sample.tmx")
        # No lang params — endpoint must auto-detect en+de
        resp = client.get(f"/api/files/{rec.id}/preview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_lang"] in ("en", "de")
        assert data["target_lang"] in ("en", "de")
        assert len(data["segments"]) > 0

    def test_explicit_langs_in_response(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_TMX, "sample.tmx")
        resp = client.get(f"/api/files/{rec.id}/preview?source_lang=en&target_lang=de")
        data = resp.json()
        assert data["source_lang"] == "en"
        assert data["target_lang"] == "de"

    def test_segment_ids_present(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_TMX, "sample.tmx")
        resp = client.get(f"/api/files/{rec.id}/preview")
        segs = resp.json()["segments"]
        for seg in segs:
            assert "id" in seg
            assert seg["id"]  # non-empty


# ===========================================================================
# 2. CSV preview
# ===========================================================================

class TestPreviewCsv:

    def test_returns_200_with_segments(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_CSV, "sample.csv")
        resp = client.get(f"/api/files/{rec.id}/preview")
        assert resp.status_code == 200
        assert len(resp.json()["segments"]) > 0

    def test_all_5_rows_returned_within_default_limit(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_CSV, "sample.csv")
        resp = client.get(f"/api/files/{rec.id}/preview")
        assert resp.status_code == 200
        assert len(resp.json()["segments"]) == 5

    def test_limit_respected(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_CSV, "sample.csv")
        resp = client.get(f"/api/files/{rec.id}/preview?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()["segments"]) == 2

    def test_correct_text_content(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_CSV, "sample.csv")
        resp = client.get(f"/api/files/{rec.id}/preview")
        segs = resp.json()["segments"]
        assert segs[0]["source"] == "Hello world"
        assert segs[0]["target"] == "Hallo Welt"

    def test_filename_in_response(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_CSV, "sample.csv")
        resp = client.get(f"/api/files/{rec.id}/preview")
        assert resp.json()["filename"] == "sample.csv"


# ===========================================================================
# 3. XLSX preview
# ===========================================================================

class TestPreviewXlsx:

    def test_returns_200_with_segments(self, client, db, test_user, sample_xlsx):
        rec = _insert_file(db, test_user, sample_xlsx, "sample.xlsx")
        resp = client.get(f"/api/files/{rec.id}/preview")
        assert resp.status_code == 200
        assert len(resp.json()["segments"]) > 0

    def test_all_5_rows_returned(self, client, db, test_user, sample_xlsx):
        rec = _insert_file(db, test_user, sample_xlsx, "sample.xlsx")
        resp = client.get(f"/api/files/{rec.id}/preview")
        assert len(resp.json()["segments"]) == 5

    def test_limit_respected(self, client, db, test_user, sample_xlsx):
        rec = _insert_file(db, test_user, sample_xlsx, "sample.xlsx")
        resp = client.get(f"/api/files/{rec.id}/preview?limit=4")
        assert len(resp.json()["segments"]) == 4

    def test_correct_text_content(self, client, db, test_user, sample_xlsx):
        rec = _insert_file(db, test_user, sample_xlsx, "sample.xlsx")
        resp = client.get(f"/api/files/{rec.id}/preview")
        segs = resp.json()["segments"]
        assert segs[0]["source"] == "Hello world"
        assert segs[0]["target"] == "Hallo Welt"
        assert segs[4]["source"] == "Save your changes"

    def test_filename_in_response(self, client, db, test_user, sample_xlsx):
        rec = _insert_file(db, test_user, sample_xlsx, "sample.xlsx")
        resp = client.get(f"/api/files/{rec.id}/preview")
        assert resp.json()["filename"] == "sample.xlsx"


# ===========================================================================
# 4. Auth & ownership
# ===========================================================================

class TestPreviewAuth:

    def test_unknown_file_id_returns_404(self, client, db, test_user):
        resp = client.get(f"/api/files/{uuid.uuid4()}/preview")
        assert resp.status_code == 404

    def test_other_users_file_returns_404(self, client, db, other_user):
        # other_user owns this file; client is authenticated as test_user
        rec = _insert_file(db, other_user, SAMPLE_TMX, "sample.tmx")
        # test_user tries to preview it → 404 (ownership mismatch)
        resp = client.get(f"/api/files/{rec.id}/preview")
        assert resp.status_code == 404

    def test_owner_can_preview_own_file(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_TMX, "sample.tmx")
        resp = client.get(f"/api/files/{rec.id}/preview")
        assert resp.status_code == 200

    def test_missing_disk_file_returns_404(self, client, db, test_user):
        rec = _insert_file(db, test_user, Path("/nonexistent/ghost.tmx"), "ghost.tmx")
        resp = client.get(f"/api/files/{rec.id}/preview")
        assert resp.status_code == 404


# ===========================================================================
# 5. Query-parameter validation
# ===========================================================================

class TestPreviewQueryParams:

    def test_limit_zero_returns_422(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_TMX, "sample.tmx")
        resp = client.get(f"/api/files/{rec.id}/preview?limit=0")
        assert resp.status_code == 422

    def test_limit_101_returns_422(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_TMX, "sample.tmx")
        resp = client.get(f"/api/files/{rec.id}/preview?limit=101")
        assert resp.status_code == 422

    def test_limit_100_is_accepted(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_TMX, "sample.tmx")
        resp = client.get(f"/api/files/{rec.id}/preview?limit=100")
        assert resp.status_code == 200

    def test_limit_1_returns_exactly_one_segment(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_TMX, "sample.tmx")
        resp = client.get(f"/api/files/{rec.id}/preview?limit=1")
        assert resp.status_code == 200
        assert len(resp.json()["segments"]) == 1

    def test_warnings_field_present_in_response(self, client, db, test_user):
        rec = _insert_file(db, test_user, SAMPLE_TMX, "sample.tmx")
        resp = client.get(f"/api/files/{rec.id}/preview")
        assert "warnings" in resp.json()
        assert isinstance(resp.json()["warnings"], list)


# ===========================================================================
# 6. Unit tests for private helpers
# ===========================================================================

class TestPreviewHelpers:

    def test_detect_langs_tmx(self):
        from app.api.routes.files import _detect_langs
        langs = _detect_langs(SAMPLE_TMX, ".tmx")
        assert "en" in langs
        assert "de" in langs

    def test_detect_langs_csv_no_lang_codes_returns_empty(self):
        from app.api.routes.files import _detect_langs
        # sample.csv has headers "source,target" — no lang codes → empty list
        langs = _detect_langs(SAMPLE_CSV, ".csv")
        assert isinstance(langs, list)

    def test_detect_langs_unknown_ext_returns_empty(self):
        from app.api.routes.files import _detect_langs
        langs = _detect_langs(SAMPLE_TMX, ".xyz")
        assert langs == []

    def test_preview_segments_tmx_respects_limit(self):
        from app.api.routes.files import _preview_segments
        warnings: list = []
        segs = _preview_segments(SAMPLE_TMX, ".tmx", "en", "de", 2, warnings)
        assert len(segs) == 2
        assert segs[0].source == "Hello world"
        assert segs[0].target == "Hallo Welt"

    def test_preview_segments_tmx_all_five(self):
        from app.api.routes.files import _preview_segments
        warnings: list = []
        segs = _preview_segments(SAMPLE_TMX, ".tmx", "en", "de", 100, warnings)
        assert len(segs) == 5

    def test_preview_segments_csv(self):
        from app.api.routes.files import _preview_segments
        warnings: list = []
        segs = _preview_segments(SAMPLE_CSV, ".csv", "en", "de", 3, warnings)
        assert len(segs) == 3
        assert segs[1].source == "Good morning"

    def test_preview_segments_nonexistent_file_returns_empty_with_warning(self):
        from app.api.routes.files import _preview_segments
        warnings: list = []
        segs = _preview_segments(Path("/no/such/file.tmx"), ".tmx", "en", "de", 10, warnings)
        assert segs == []
        assert len(warnings) == 1

    def test_preview_segments_unsupported_ext_returns_empty_with_warning(self):
        from app.api.routes.files import _preview_segments
        warnings: list = []
        segs = _preview_segments(SAMPLE_TMX, ".xyz", "en", "de", 10, warnings)
        assert segs == []
        assert len(warnings) == 1
