"""Tests for the configurable output file name prefix feature."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

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
        # non-ASCII characters not in [A-Za-z0-9_-]
        self._raises("préfixe")

    def test_exclamation(self):
        self._raises("prefix!")


# ===========================================================================
# 3. Filename building logic
# ===========================================================================

class TestFilenameBuilding:
    """Mirrors the `_fname_pfx` logic in pipeline.py."""

    @staticmethod
    def _build_names(prefix: str, src: str, tgt: str) -> dict[str, str]:
        p = (prefix + "_") if prefix else ""
        return {
            "clean_tmx":  f"{p}clean_{src}_{tgt}.tmx",
            "clean_xls":  f"{p}clean_{src}_{tgt}.xlsx",
            "qa_xls":     f"{p}qa_{src}_{tgt}.xlsx",
            "qa_html":    f"{p}qa_{src}_{tgt}.html",
            "dup_tmx":    f"{p}duplicates_{src}_{tgt}.tmx",
            "dup_xls":    f"{p}duplicates_{src}_{tgt}.xlsx",
            "ut_tmx":     f"{p}untranslated_{src}_{tgt}.tmx",
            "ut_xls":     f"{p}untranslated_{src}_{tgt}.xlsx",
        }

    def test_no_prefix_preserves_original_names(self):
        names = self._build_names("", "en", "de")
        assert names["clean_tmx"]  == "clean_en_de.tmx"
        assert names["qa_xls"]     == "qa_en_de.xlsx"
        assert names["dup_tmx"]    == "duplicates_en_de.tmx"
        assert names["ut_xls"]     == "untranslated_en_de.xlsx"

    def test_prefix_prepended_to_all_files(self):
        names = self._build_names("proj", "en", "de")
        assert names["clean_tmx"]  == "proj_clean_en_de.tmx"
        assert names["clean_xls"]  == "proj_clean_en_de.xlsx"
        assert names["qa_xls"]     == "proj_qa_en_de.xlsx"
        assert names["qa_html"]    == "proj_qa_en_de.html"
        assert names["dup_tmx"]    == "proj_duplicates_en_de.tmx"
        assert names["dup_xls"]    == "proj_duplicates_en_de.xlsx"
        assert names["ut_tmx"]     == "proj_untranslated_en_de.tmx"
        assert names["ut_xls"]     == "proj_untranslated_en_de.xlsx"

    def test_hyphenated_prefix(self):
        names = self._build_names("my-corp_v2", "fr", "ja")
        assert names["clean_tmx"] == "my-corp_v2_clean_fr_ja.tmx"

    def test_empty_prefix_does_not_add_leading_underscore(self):
        names = self._build_names("", "en", "fr")
        for name in names.values():
            assert not name.startswith("_"), f"Leading underscore in: {name}"


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
            resp = self._post_job(client, f.id)  # no output_prefix key

        assert resp.status_code == 201
        job_id = resp.json()["id"]
        job = _get_job(db, job_id)
        assert job is not None
        assert (job.output_prefix or "") == ""

    def test_create_job_explicit_empty_prefix(self, client, db, test_user):
        f = _make_uploaded_file(db, test_user)
        mock_task = MagicMock()
        mock_task.id = str(uuid.uuid4())

        with patch("app.workers.pipeline.run_pipeline.delay", return_value=mock_task):
            resp = self._post_job(client, f.id, prefix="")

        assert resp.status_code == 201
        job_id = resp.json()["id"]
        job = _get_job(db, job_id)
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
        resp = self._post_job(client, f.id, "bad prefix")
        assert resp.status_code == 422

    def test_slash_in_prefix_is_rejected(self, client, db, test_user):
        f = _make_uploaded_file(db, test_user)
        resp = self._post_job(client, f.id, "path/traversal")
        assert resp.status_code == 422

    def test_too_long_prefix_is_rejected(self, client, db, test_user):
        f = _make_uploaded_file(db, test_user)
        resp = self._post_job(client, f.id, "a" * 51)
        assert resp.status_code == 422

    def test_unicode_prefix_is_rejected(self, client, db, test_user):
        f = _make_uploaded_file(db, test_user)
        resp = self._post_job(client, f.id, "préfixe")
        assert resp.status_code == 422
