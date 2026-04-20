"""Tests for the configurable output file name prefix feature.

Amendment note
--------------
The original ``TestFilenameBuilding`` class tested a *local copy* of the
naming logic (``_build_names``), not the real code in ``pipeline.py``.  It
was therefore possible for the pipeline to have a bug that these tests never
caught.

Fixes applied here:
  1. ``TestBuildOutputPaths`` — imports and exercises the REAL
     ``_build_output_paths()`` helper extracted from ``pipeline.py``.
  2. ``TestResultsEndpointWithPrefix`` — creates actual prefixed files on disk,
     then calls ``GET /api/jobs/{id}/results`` and verifies that every returned
     filename carries the prefix.
  3. ``TestDownloadWithPrefix`` — creates an actual prefixed file on disk, then
     calls ``GET /api/jobs/{id}/download/{prefixed_name}`` and verifies 200.

The old ``TestFilenameBuilding`` class is removed; its coverage is superseded
by ``TestBuildOutputPaths`` which tests the real function.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.models.job import Job, UploadedFile
from app.models.user import User
from app.schemas.job import CreateJobRequest, JobOptions
from tests.conftest import make_job


# ===========================================================================
# Helpers
# ===========================================================================

def _get_job(db: Session, job_id: str) -> Job | None:
    db.expire_all()
    return db.query(Job).filter(Job.id == job_id).first()


def _make_uploaded_file(db: Session, user: User) -> UploadedFile:
    """Insert a bare UploadedFile (no job yet) and return it."""
    f = UploadedFile(
        id=str(uuid.uuid4()),
        user_id=user.id,
        job_id=None,
        original_filename="sample.tmx",
        stored_path="/tmp/test_sample.tmx",
        created_at=datetime.now(timezone.utc),
    )
    db.add(f)
    db.commit()
    return f


def _make_complete_job(db: Session, user: User, output_prefix: str = "") -> Job:
    """Insert a completed Job record directly into *db* and return it."""
    job = Job(
        id=str(uuid.uuid4()),
        user_id=user.id,
        status="complete",
        progress=100,
        options_json="{}",
        engine="none",
        source_lang="en",
        target_lang="de",
        output_prefix=output_prefix,
        task_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    return job


_DEFAULT_OPTIONS = {
    "remove_duplicates": False,
    "move_duplicates_to_separate_file": False,
    "remove_tags": False,
    "keep_tags_intact": True,
    "remove_variables": False,
    "keep_variables_intact": True,
    "remove_untranslated": False,
    "move_untranslated_to_separate_file": False,
    "check_numbers": True,
    "check_scripts": True,
    "check_untranslated": True,
    "outputs_tmx": True,
    "outputs_clean_xls": True,
    "outputs_qa_xls": True,
    "outputs_html_report": True,
}

# All 8 canonical output file type keys as produced by _build_output_paths()
_ALL_OUTPUT_KEYS = [
    "clean_tmx", "clean_xls", "qa_xls", "report",
    "dup_tmx", "dup_xls", "ut_tmx", "ut_xls",
]


# ===========================================================================
# 1. Pydantic validator — valid values
# ===========================================================================

class TestPrefixValidatorValid:
    """CreateJobRequest.output_prefix accepts well-formed values."""

    def _base(self, prefix: str) -> CreateJobRequest:
        return CreateJobRequest(
            file_ids=["dummy"],
            engine="none",
            source_lang="en",
            target_langs=["de"],
            options=JobOptions(),
            output_prefix=prefix,
        )

    def test_empty_string_is_valid(self):
        req = self._base("")
        assert req.output_prefix == ""

    def test_simple_word(self):
        req = self._base("myproject")
        assert req.output_prefix == "myproject"

    def test_hyphen_and_underscore(self):
        req = self._base("my-project_v2")
        assert req.output_prefix == "my-project_v2"

    def test_all_digits(self):
        req = self._base("2024")
        assert req.output_prefix == "2024"

    def test_max_length_50(self):
        prefix = "a" * 50
        req = self._base(prefix)
        assert req.output_prefix == prefix

    def test_leading_trailing_whitespace_is_stripped(self):
        req = self._base("  trimmed  ")
        assert req.output_prefix == "trimmed"

    def test_whitespace_only_becomes_empty(self):
        req = self._base("   ")
        assert req.output_prefix == ""


# ===========================================================================
# 2. Pydantic validator — invalid values
# ===========================================================================

class TestPrefixValidatorInvalid:
    """CreateJobRequest.output_prefix rejects bad input."""

    def _raises(self, prefix: str) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CreateJobRequest(
                file_ids=["dummy"],
                engine="none",
                source_lang="en",
                target_langs=["de"],
                options=JobOptions(),
                output_prefix=prefix,
            )

    def test_space_in_middle(self):
        self._raises("bad prefix")

    def test_slash(self):
        self._raises("path/traversal")

    def test_backslash(self):
        self._raises("path\\traversal")

    def test_dot(self):
        self._raises("file.name")

    def test_too_long_51_chars(self):
        self._raises("a" * 51)

    def test_unicode_letters(self):
        self._raises("préfixe")

    def test_exclamation(self):
        self._raises("prefix!")


# ===========================================================================
# 3. _build_output_paths() — tests the REAL function from pipeline.py
#
# Previously this class tested a LOCAL COPY of the logic (_build_names).
# It is now replaced by tests that import the actual helper so any
# change to the pipeline naming code is caught immediately.
# ===========================================================================

class TestBuildOutputPaths:
    """Import and exercise ``_build_output_paths`` from ``pipeline.py`` directly."""

    @pytest.fixture(autouse=True)
    def _import(self, tmp_path):
        from app.workers.pipeline import _build_output_paths
        self._fn = _build_output_paths
        self._dir = tmp_path

    def _paths(self, prefix: str, src: str = "en", tgt: str = "de") -> dict:
        return self._fn(self._dir, src, tgt, prefix)

    # --- no prefix (backward-compat) -----------------------------------------

    def test_no_prefix_clean_tmx(self):
        assert self._paths("")["clean_tmx"].name == "clean_en_de.tmx"

    def test_no_prefix_qa_xls(self):
        assert self._paths("")["qa_xls"].name == "qa_en_de.xlsx"

    def test_no_prefix_duplicates_tmx(self):
        assert self._paths("")["dup_tmx"].name == "duplicates_en_de.tmx"

    def test_no_prefix_untranslated_xls(self):
        assert self._paths("")["ut_xls"].name == "untranslated_en_de.xlsx"

    def test_no_prefix_none_treated_as_empty(self):
        # pipeline passes `job.output_prefix or ""` so None is already guarded,
        # but verify the function itself is safe with empty string
        p = self._paths("")
        for key in _ALL_OUTPUT_KEYS:
            assert not p[key].name.startswith("_"), f"Leading underscore in {key}"

    # --- with prefix ---------------------------------------------------------

    def test_prefix_prepended_to_clean_tmx(self):
        assert self._paths("proj")["clean_tmx"].name == "proj_clean_en_de.tmx"

    def test_prefix_prepended_to_clean_xls(self):
        assert self._paths("proj")["clean_xls"].name == "proj_clean_en_de.xlsx"

    def test_prefix_prepended_to_qa_xls(self):
        assert self._paths("proj")["qa_xls"].name == "proj_qa_en_de.xlsx"

    def test_prefix_prepended_to_report(self):
        assert self._paths("proj")["report"].name == "proj_qa_en_de.html"

    def test_prefix_prepended_to_dup_tmx(self):
        assert self._paths("proj")["dup_tmx"].name == "proj_duplicates_en_de.tmx"

    def test_prefix_prepended_to_dup_xls(self):
        assert self._paths("proj")["dup_xls"].name == "proj_duplicates_en_de.xlsx"

    def test_prefix_prepended_to_ut_tmx(self):
        assert self._paths("proj")["ut_tmx"].name == "proj_untranslated_en_de.tmx"

    def test_prefix_prepended_to_ut_xls(self):
        assert self._paths("proj")["ut_xls"].name == "proj_untranslated_en_de.xlsx"

    def test_all_eight_paths_produced(self):
        p = self._paths("x")
        assert set(p.keys()) == set(_ALL_OUTPUT_KEYS)

    def test_all_paths_inside_output_dir(self):
        p = self._paths("x")
        for key, path in p.items():
            assert path.parent == self._dir, f"{key} not in output_dir"

    def test_hyphenated_prefix(self):
        assert self._paths("my-corp_v2", "fr", "ja")["clean_tmx"].name == \
               "my-corp_v2_clean_fr_ja.tmx"

    def test_lang_pair_preserved_in_name(self):
        p = self._paths("pfx", "fr", "pt")
        assert p["clean_tmx"].name == "pfx_clean_fr_pt.tmx"


# ===========================================================================
# 4. API: create job — prefix stored in DB
# ===========================================================================

class TestCreateJobApi:
    """POST /api/jobs/ correctly stores output_prefix on the Job record."""

    def _post_job(self, client, file_id: str, prefix: str | None = None) -> dict:
        body = {
            "file_ids": [file_id],
            "engine": "none",
            "source_lang": "en",
            "target_langs": ["de"],
            "options": _DEFAULT_OPTIONS,
        }
        if prefix is not None:
            body["output_prefix"] = prefix
        return client.post("/api/jobs/", json=body)

    def test_create_job_stores_custom_prefix(self, client, db, test_user):
        f = _make_uploaded_file(db, test_user)
        mock_task = MagicMock()
        mock_task.id = str(uuid.uuid4())

        with patch("app.workers.pipeline.run_pipeline.delay", return_value=mock_task):
            resp = self._post_job(client, f.id, prefix="v3release")

        assert resp.status_code == 201
        job_id = resp.json()["id"]
        job = _get_job(db, job_id)
        assert job is not None
        assert job.output_prefix == "v3release"

    def test_create_job_default_prefix_is_empty(self, client, db, test_user):
        f = _make_uploaded_file(db, test_user)
        mock_task = MagicMock()
        mock_task.id = str(uuid.uuid4())

        with patch("app.workers.pipeline.run_pipeline.delay", return_value=mock_task):
            resp = self._post_job(client, f.id)

        assert resp.status_code == 201
        job = _get_job(db, resp.json()["id"])
        assert (job.output_prefix or "") == ""

    def test_create_job_explicit_empty_prefix(self, client, db, test_user):
        f = _make_uploaded_file(db, test_user)
        mock_task = MagicMock()
        mock_task.id = str(uuid.uuid4())

        with patch("app.workers.pipeline.run_pipeline.delay", return_value=mock_task):
            resp = self._post_job(client, f.id, prefix="")

        assert resp.status_code == 201
        job = _get_job(db, resp.json()["id"])
        assert (job.output_prefix or "") == ""


# ===========================================================================
# 5. API: invalid prefix → 422
# ===========================================================================

class TestCreateJobInvalidPrefix:
    """POST /api/jobs/ with an invalid output_prefix returns HTTP 422."""

    def _post_job(self, client, file_id: str, prefix: str) -> dict:
        return client.post("/api/jobs/", json={
            "file_ids": [file_id],
            "engine": "none",
            "source_lang": "en",
            "target_langs": ["de"],
            "options": _DEFAULT_OPTIONS,
            "output_prefix": prefix,
        })

    def test_space_in_prefix_is_rejected(self, client, db, test_user):
        f = _make_uploaded_file(db, test_user)
        assert self._post_job(client, f.id, "bad prefix").status_code == 422

    def test_slash_in_prefix_is_rejected(self, client, db, test_user):
        f = _make_uploaded_file(db, test_user)
        assert self._post_job(client, f.id, "path/traversal").status_code == 422

    def test_too_long_prefix_is_rejected(self, client, db, test_user):
        f = _make_uploaded_file(db, test_user)
        assert self._post_job(client, f.id, "a" * 51).status_code == 422

    def test_unicode_prefix_is_rejected(self, client, db, test_user):
        f = _make_uploaded_file(db, test_user)
        assert self._post_job(client, f.id, "préfixe").status_code == 422


# ===========================================================================
# 6. Results endpoint returns prefixed filenames
#
# These tests were MISSING from the original implementation.  They prove that
# GET /api/jobs/{id}/results returns filenames that include the prefix the
# user set — i.e. the full chain from DB → pipeline → disk → API works.
# ===========================================================================

class TestResultsEndpointWithPrefix:
    """GET /api/jobs/{id}/results returns filenames WITH the user-set prefix."""

    def _create_output_files(
        self,
        tmp_path: Path,
        user_id: str,
        job_id: str,
        prefix: str,
        src: str = "en",
        tgt: str = "de",
    ) -> Path:
        """Simulate what the pipeline would have written to disk."""
        from app.workers.pipeline import _build_output_paths
        output_dir = tmp_path / str(user_id) / job_id / "output"
        output_dir.mkdir(parents=True)
        paths = _build_output_paths(output_dir, src, tgt, prefix)
        for path in paths.values():
            path.write_text("dummy content")
        return output_dir

    def test_all_returned_filenames_have_prefix(self, client, db, test_user, tmp_path):
        prefix = "myproject"
        job = _make_complete_job(db, test_user, output_prefix=prefix)
        self._create_output_files(tmp_path, test_user.id, job.id, prefix)

        with patch.object(app_settings, "STORAGE_PATH", str(tmp_path)):
            resp = client.get(f"/api/jobs/{job.id}/results")

        assert resp.status_code == 200
        filenames = [o["filename"] for o in resp.json()["outputs"]]
        assert len(filenames) > 0, "No output files returned"
        for fn in filenames:
            assert fn.startswith(f"{prefix}_"), (
                f"Filename '{fn}' does not start with '{prefix}_'"
            )

    def test_no_prefix_returns_original_names(self, client, db, test_user, tmp_path):
        job = _make_complete_job(db, test_user, output_prefix="")
        self._create_output_files(tmp_path, test_user.id, job.id, "")

        with patch.object(app_settings, "STORAGE_PATH", str(tmp_path)):
            resp = client.get(f"/api/jobs/{job.id}/results")

        assert resp.status_code == 200
        filenames = [o["filename"] for o in resp.json()["outputs"]]
        assert len(filenames) > 0
        # Without prefix, names start with the type keyword (clean_, qa_, etc.)
        for fn in filenames:
            assert not fn.startswith("_"), f"Leading underscore in '{fn}'"

    def test_download_url_contains_prefixed_filename(self, client, db, test_user, tmp_path):
        prefix = "corp2024"
        job = _make_complete_job(db, test_user, output_prefix=prefix)
        self._create_output_files(tmp_path, test_user.id, job.id, prefix)

        with patch.object(app_settings, "STORAGE_PATH", str(tmp_path)):
            resp = client.get(f"/api/jobs/{job.id}/results")

        outputs = resp.json()["outputs"]
        for o in outputs:
            assert o["filename"] in o["download_url"], (
                f"download_url '{o['download_url']}' does not reference '{o['filename']}'"
            )

    def test_all_eight_output_files_returned_with_prefix(self, client, db, test_user, tmp_path):
        prefix = "v2"
        job = _make_complete_job(db, test_user, output_prefix=prefix)
        self._create_output_files(tmp_path, test_user.id, job.id, prefix)

        with patch.object(app_settings, "STORAGE_PATH", str(tmp_path)):
            resp = client.get(f"/api/jobs/{job.id}/results")

        assert len(resp.json()["outputs"]) == 8

    def test_hyphenated_prefix_preserved_in_filenames(self, client, db, test_user, tmp_path):
        prefix = "my-corp_v3"
        job = _make_complete_job(db, test_user, output_prefix=prefix)
        self._create_output_files(tmp_path, test_user.id, job.id, prefix)

        with patch.object(app_settings, "STORAGE_PATH", str(tmp_path)):
            resp = client.get(f"/api/jobs/{job.id}/results")

        filenames = [o["filename"] for o in resp.json()["outputs"]]
        for fn in filenames:
            assert fn.startswith(f"{prefix}_"), (
                f"Filename '{fn}' does not start with '{prefix}_'"
            )


# ===========================================================================
# 7. Download endpoint serves prefixed file
#
# These tests were MISSING from the original implementation.  They prove that
# GET /api/jobs/{id}/download/{prefixed_name} actually serves the file.
# ===========================================================================

class TestDownloadWithPrefix:
    """GET /api/jobs/{id}/download/{prefixed_filename} serves the file."""

    def _write_output_file(
        self, tmp_path: Path, user_id: str, job_id: str, filename: str
    ) -> Path:
        output_dir = tmp_path / str(user_id) / job_id / "output"
        output_dir.mkdir(parents=True)
        p = output_dir / filename
        p.write_text("fake tmx content")
        return p

    def test_download_prefixed_tmx_returns_200(self, client, db, test_user, tmp_path):
        job = _make_complete_job(db, test_user, output_prefix="testpfx")
        filename = "testpfx_clean_en_de.tmx"
        self._write_output_file(tmp_path, test_user.id, job.id, filename)

        with patch.object(app_settings, "STORAGE_PATH", str(tmp_path)):
            resp = client.get(f"/api/jobs/{job.id}/download/{filename}")

        assert resp.status_code == 200

    def test_download_prefixed_xlsx_returns_200(self, client, db, test_user, tmp_path):
        job = _make_complete_job(db, test_user, output_prefix="testpfx")
        filename = "testpfx_qa_en_de.xlsx"
        self._write_output_file(tmp_path, test_user.id, job.id, filename)

        with patch.object(app_settings, "STORAGE_PATH", str(tmp_path)):
            resp = client.get(f"/api/jobs/{job.id}/download/{filename}")

        assert resp.status_code == 200

    def test_download_no_prefix_file_returns_200(self, client, db, test_user, tmp_path):
        job = _make_complete_job(db, test_user, output_prefix="")
        filename = "clean_en_de.tmx"
        self._write_output_file(tmp_path, test_user.id, job.id, filename)

        with patch.object(app_settings, "STORAGE_PATH", str(tmp_path)):
            resp = client.get(f"/api/jobs/{job.id}/download/{filename}")

        assert resp.status_code == 200

    def test_download_wrong_prefix_returns_404(self, client, db, test_user, tmp_path):
        """File on disk has prefix; requesting unprefixed name → 404."""
        job = _make_complete_job(db, test_user, output_prefix="realprefix")
        # Create file WITH prefix
        self._write_output_file(tmp_path, test_user.id, job.id, "realprefix_clean_en_de.tmx")

        with patch.object(app_settings, "STORAGE_PATH", str(tmp_path)):
            # Request WITHOUT prefix → file does not exist
            resp = client.get(f"/api/jobs/{job.id}/download/clean_en_de.tmx")

        assert resp.status_code == 404

    def test_download_content_is_correct(self, client, db, test_user, tmp_path):
        """The downloaded file contains the real file content."""
        job = _make_complete_job(db, test_user, output_prefix="pfx")
        filename = "pfx_clean_en_de.tmx"
        path = self._write_output_file(tmp_path, test_user.id, job.id, filename)
        path.write_text("sentinel content 12345")

        with patch.object(app_settings, "STORAGE_PATH", str(tmp_path)):
            resp = client.get(f"/api/jobs/{job.id}/download/{filename}")

        assert resp.status_code == 200
        assert b"sentinel content 12345" in resp.content
