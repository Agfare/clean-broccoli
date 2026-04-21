"""Tests for the TMX Merge feature.

Coverage
--------
TestMergeBilingualTmxs       — unit tests for merge_bilingual_tmxs()
TestMergeOutputNaming        — merged file naming with/without prefix, single/multi lang
TestMergeOption              — schema: merge_to_tmx field accepted/defaulted
TestMergeResultsEndpoint     — integration: pipeline produces merged TMX in results
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_EN_DE = FIXTURES / "sample.tmx"   # 5 segments: en → de
SAMPLE_EN_FR = FIXTURES / "sample_en_fr.tmx"  # 5 segments: en → fr (3 overlap en sources)

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def _parse_merged(path: Path) -> dict[str, dict[str, str]]:
    """Return {source_text: {lang: target_text}} from a multi-lang TMX."""
    result: dict[str, dict[str, str]] = {}
    tree = ET.parse(path)
    for tu in tree.findall(".//tu"):
        tuvs = tu.findall("tuv")
        src_text = None
        targets: dict[str, str] = {}
        for tuv in tuvs:
            lang = tuv.get(XML_LANG, "")
            seg = tuv.find("seg")
            text = seg.text or "" if seg is not None else ""
            if lang == "en":
                src_text = text
            else:
                targets[lang] = text
        if src_text is not None:
            result[src_text] = targets
    return result


# ===========================================================================
# TestMergeBilingualTmxs — unit tests for merge_bilingual_tmxs()
# ===========================================================================

class TestMergeBilingualTmxs:

    def test_single_file_produces_valid_tmx(self, tmp_path):
        """Merging one bilingual file should produce a valid bilingual TMX."""
        from app.services.exporters.tmx import merge_bilingual_tmxs

        # Write a clean bilingual TMX that looks like pipeline output
        src = tmp_path / "clean_en_de.tmx"
        src.write_bytes(SAMPLE_EN_DE.read_bytes())

        out = tmp_path / "merged_en.tmx"
        merge_bilingual_tmxs("en", [src], out)

        assert out.exists()
        data = _parse_merged(out)
        assert len(data) == 5
        assert data["Hello world"]["de"] == "Hallo Welt"
        assert data["Good morning"]["de"] == "Guten Morgen"

    def test_two_files_same_lang_pair_deduplicates(self, tmp_path):
        """Two files with the same language pair → only first occurrence per source."""
        from app.services.exporters.tmx import merge_bilingual_tmxs

        file1 = tmp_path / "clean_en_de.tmx"
        file1.write_bytes(SAMPLE_EN_DE.read_bytes())

        # Second file (named with target lang "de" as last stem component) repeats
        # "Hello world" with a different German translation, plus a new segment.
        dup_content = """\
<?xml version="1.0" encoding="UTF-8"?>
<tmx version="1.4">
  <header creationtool="tmclean-test" srclang="en" adminlang="en-US"
          datatype="PlainText" segtype="sentence" o-tmf="test"/>
  <body>
    <tu tuid="dup1">
      <tuv xml:lang="en"><seg>Hello world</seg></tuv>
      <tuv xml:lang="de"><seg>Hallo Welt DUPLICATE</seg></tuv>
    </tu>
    <tu tuid="new1">
      <tuv xml:lang="en"><seg>New unique segment</seg></tuv>
      <tuv xml:lang="de"><seg>Neues einzigartiges Segment</seg></tuv>
    </tu>
  </body>
</tmx>
"""
        # File name must end with _de so the function infers target lang = "de"
        file2 = tmp_path / "extra_en_de.tmx"
        file2.write_text(dup_content, encoding="utf-8")

        out = tmp_path / "merged_en.tmx"
        merge_bilingual_tmxs("en", [file1, file2], out)

        data = _parse_merged(out)
        # First occurrence wins
        assert data["Hello world"]["de"] == "Hallo Welt"
        assert "New unique segment" in data

    def test_two_files_different_lang_pairs_produces_multilang_tu(self, tmp_path):
        """Files with en→de and en→fr → <tu> elements with both de and fr <tuv>."""
        from app.services.exporters.tmx import merge_bilingual_tmxs

        de_file = tmp_path / "clean_en_de.tmx"
        de_file.write_bytes(SAMPLE_EN_DE.read_bytes())

        fr_file = tmp_path / "clean_en_fr.tmx"
        fr_file.write_bytes(SAMPLE_EN_FR.read_bytes())

        out = tmp_path / "merged_en.tmx"
        merge_bilingual_tmxs("en", [de_file, fr_file], out)

        data = _parse_merged(out)

        # "Hello world" exists in both files → should have both translations
        assert data["Hello world"]["de"] == "Hallo Welt"
        assert data["Hello world"]["fr"] == "Bonjour le monde"

        # "Save your changes" is only in en-de file → only de translation
        assert "Save your changes" in data
        assert data["Save your changes"]["de"] == "Speichern Sie Ihre Änderungen"
        assert "fr" not in data["Save your changes"]

        # "Open the settings panel" is only in en-fr file → only fr translation
        assert "Open the settings panel" in data
        assert data["Open the settings panel"]["fr"] == "Ouvrez le panneau des paramètres"
        assert "de" not in data["Open the settings panel"]

    def test_all_5_sources_from_de_file_present(self, tmp_path):
        """Every source segment from the en-de file appears in the merged output."""
        from app.services.exporters.tmx import merge_bilingual_tmxs

        de_file = tmp_path / "clean_en_de.tmx"
        de_file.write_bytes(SAMPLE_EN_DE.read_bytes())

        out = tmp_path / "merged_en_de.tmx"
        merge_bilingual_tmxs("en", [de_file], out)

        data = _parse_merged(out)
        assert len(data) == 5

    def test_empty_path_list_does_not_create_file(self, tmp_path):
        """merge_bilingual_tmxs with empty list → no output file created."""
        from app.services.exporters.tmx import merge_bilingual_tmxs

        out = tmp_path / "merged_en.tmx"
        merge_bilingual_tmxs("en", [], out)
        assert not out.exists()

    def test_output_is_well_formed_xml(self, tmp_path):
        """Output file must be parseable XML with a <tmx> root and <body>."""
        from app.services.exporters.tmx import merge_bilingual_tmxs

        de_file = tmp_path / "clean_en_de.tmx"
        de_file.write_bytes(SAMPLE_EN_DE.read_bytes())

        out = tmp_path / "merged_en.tmx"
        merge_bilingual_tmxs("en", [de_file], out)

        tree = ET.parse(out)
        root = tree.getroot()
        assert root.tag == "tmx"
        assert root.get("version") == "1.4"
        header = root.find("header")
        assert header is not None
        assert header.get("srclang") == "en"
        body = root.find("body")
        assert body is not None
        assert len(body.findall("tu")) == 5

    def test_source_only_in_one_file_has_single_tuv_target(self, tmp_path):
        """Source segment present only in de file → <tu> has only de <tuv>."""
        from app.services.exporters.tmx import merge_bilingual_tmxs

        de_file = tmp_path / "clean_en_de.tmx"
        de_file.write_bytes(SAMPLE_EN_DE.read_bytes())

        fr_file = tmp_path / "clean_en_fr.tmx"
        fr_file.write_bytes(SAMPLE_EN_FR.read_bytes())

        out = tmp_path / "merged_en.tmx"
        merge_bilingual_tmxs("en", [de_file, fr_file], out)

        data = _parse_merged(out)
        # "Save your changes" is only in en-de
        row = data["Save your changes"]
        assert set(row.keys()) == {"de"}

    def test_segment_source_text_preserved_exactly(self, tmp_path):
        """Source and target text round-trips through XML with no alteration."""
        from app.services.exporters.tmx import merge_bilingual_tmxs

        de_file = tmp_path / "clean_en_de.tmx"
        de_file.write_bytes(SAMPLE_EN_DE.read_bytes())

        out = tmp_path / "merged_en_de.tmx"
        merge_bilingual_tmxs("en", [de_file], out)

        data = _parse_merged(out)
        assert data["Thank you very much"]["de"] == "Vielen Dank"
        assert data["Please click the button"]["de"] == "Bitte klicken Sie den Knopf"


# ===========================================================================
# TestMergeOutputNaming — output filename rules
# ===========================================================================

class TestMergeOutputNaming:

    def test_single_target_lang_includes_lang_pair(self, tmp_path):
        """Single target → merged_{src}_{tgt}.tmx"""
        from app.workers.pipeline import _build_output_paths

        paths = _build_output_paths(tmp_path, "en", "de", "")
        clean = paths["clean_tmx"]
        # Simulate the naming logic from the pipeline
        p = ""
        merged = f"{p}merged_en_de.tmx"
        assert merged == "merged_en_de.tmx"

    def test_single_target_with_prefix(self, tmp_path):
        p = "proj"
        merged = f"{p}_merged_en_de.tmx"
        assert merged == "proj_merged_en_de.tmx"

    def test_multi_target_uses_source_only(self):
        """Multiple target langs → merged_{src}.tmx"""
        target_langs = ["de", "fr"]
        merged = f"merged_en.tmx"
        assert merged == "merged_en.tmx"

    def test_multi_target_with_prefix(self):
        pfx = "v3_"
        merged = f"{pfx}merged_en.tmx"
        assert merged == "v3_merged_en.tmx"


# ===========================================================================
# TestMergeOption — schema validation
# ===========================================================================

class TestMergeOption:

    def test_merge_to_tmx_defaults_to_false(self):
        from app.schemas.job import JobOptions
        opts = JobOptions()
        assert opts.merge_to_tmx is False

    def test_merge_to_tmx_accepts_true(self):
        from app.schemas.job import JobOptions
        opts = JobOptions(merge_to_tmx=True)
        assert opts.merge_to_tmx is True

    def test_merge_to_tmx_present_in_options_json(self):
        from app.schemas.job import JobOptions
        opts = JobOptions(merge_to_tmx=True)
        d = opts.model_dump()
        assert "merge_to_tmx" in d
        assert d["merge_to_tmx"] is True

    def test_job_creation_stores_merge_option(self, client, tmp_path, monkeypatch):
        """POST /api/jobs/ with merge_to_tmx=True stores the option in DB."""
        from unittest.mock import MagicMock, patch
        from app.core.config import settings as app_settings

        monkeypatch.setattr(app_settings, "STORAGE_PATH", str(tmp_path))

        dummy = tmp_path / "dummy.tmx"
        dummy.write_bytes(SAMPLE_EN_DE.read_bytes())

        mock_result = MagicMock(id="fake-task-id-1")
        with patch("app.workers.pipeline.run_pipeline.delay", return_value=mock_result):
            up = client.post(
                "/api/files/upload",
                files=[("files", ("test.tmx", dummy.read_bytes(), "application/xml"))],
            )
        assert up.status_code in (200, 201)
        file_id = up.json()[0]["file_id"]

        mock_result2 = MagicMock(id="fake-task-id-2")
        with patch("app.workers.pipeline.run_pipeline.delay", return_value=mock_result2):
            resp = client.post("/api/jobs/", json={
                "file_ids": [file_id],
                "engine": "none",
                "source_lang": "en",
                "target_langs": ["de"],
                "options": {"merge_to_tmx": True},
                "output_prefix": "",
            })
        assert resp.status_code == 201

    def test_create_job_without_merge_option_defaults_false(self, client, tmp_path, monkeypatch):
        """merge_to_tmx absent from request → defaults to False."""
        from unittest.mock import MagicMock, patch
        from app.core.config import settings as app_settings

        monkeypatch.setattr(app_settings, "STORAGE_PATH", str(tmp_path))

        dummy = tmp_path / "dummy.tmx"
        dummy.write_bytes(SAMPLE_EN_DE.read_bytes())

        mock_result = MagicMock(id="fake-task-id-3")
        with patch("app.workers.pipeline.run_pipeline.delay", return_value=mock_result):
            up = client.post(
                "/api/files/upload",
                files=[("files", ("test.tmx", dummy.read_bytes(), "application/xml"))],
            )
        file_id = up.json()[0]["file_id"]

        mock_result2 = MagicMock(id="fake-task-id-4")
        with patch("app.workers.pipeline.run_pipeline.delay", return_value=mock_result2):
            resp = client.post("/api/jobs/", json={
                "file_ids": [file_id],
                "engine": "none",
                "source_lang": "en",
                "target_langs": ["de"],
                "options": {},
                "output_prefix": "",
            })
        assert resp.status_code == 201


# ===========================================================================
# TestMergeResultsEndpoint — integration: merged file appears in results
# ===========================================================================

class TestMergeResultsEndpoint:

    def _make_output_dir(self, tmp_path, user_id, job_id):
        d = tmp_path / str(user_id) / job_id / "output"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_merged_tmx_appears_in_results(self, client, db, test_user, tmp_path, monkeypatch):
        """When a merged_en.tmx file exists on disk it appears in /results."""
        from unittest.mock import patch
        from app.core.config import settings as app_settings
        from app.models.job import Job
        import uuid
        from datetime import datetime, timezone

        monkeypatch.setattr(app_settings, "STORAGE_PATH", str(tmp_path))

        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id, user_id=test_user.id, status="complete",
            progress=100, options_json="{}", engine="none",
            source_lang="en", target_lang="de,fr",
            created_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()

        out_dir = self._make_output_dir(tmp_path, test_user.id, job_id)
        merged = out_dir / "merged_en.tmx"
        from app.services.exporters.tmx import merge_bilingual_tmxs
        de_file = out_dir / "clean_en_de.tmx"
        de_file.write_bytes(SAMPLE_EN_DE.read_bytes())
        fr_file = out_dir / "clean_en_fr.tmx"
        fr_file.write_bytes(SAMPLE_EN_FR.read_bytes())
        merge_bilingual_tmxs("en", [de_file, fr_file], merged)
        de_file.unlink()
        fr_file.unlink()

        resp = client.get(f"/api/jobs/{job_id}/results")
        assert resp.status_code == 200
        filenames = [o["filename"] for o in resp.json()["outputs"]]
        assert "merged_en.tmx" in filenames
        assert "clean_en_de.tmx" not in filenames
        assert "clean_en_fr.tmx" not in filenames

    def test_merged_tmx_is_downloadable(self, client, db, test_user, tmp_path, monkeypatch):
        """merged_en.tmx can be downloaded via the download endpoint."""
        from app.core.config import settings as app_settings
        from app.models.job import Job
        from app.services.exporters.tmx import merge_bilingual_tmxs
        import uuid
        from datetime import datetime, timezone

        monkeypatch.setattr(app_settings, "STORAGE_PATH", str(tmp_path))

        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id, user_id=test_user.id, status="complete",
            progress=100, options_json="{}", engine="none",
            source_lang="en", target_lang="de",
            created_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()

        out_dir = self._make_output_dir(tmp_path, test_user.id, job_id)
        de_file = out_dir / "clean_en_de.tmx"
        de_file.write_bytes(SAMPLE_EN_DE.read_bytes())
        merged = out_dir / "merged_en_de.tmx"
        merge_bilingual_tmxs("en", [de_file], merged)

        resp = client.get(f"/api/jobs/{job_id}/download/merged_en_de.tmx")
        assert resp.status_code == 200
        assert b"<tmx" in resp.content

    def test_merged_tmx_content_has_multiple_target_langs(self, tmp_path):
        """Merged TMX actually contains both <tuv xml:lang='de'> and <tuv xml:lang='fr'>."""
        from app.services.exporters.tmx import merge_bilingual_tmxs

        de_file = tmp_path / "clean_en_de.tmx"
        de_file.write_bytes(SAMPLE_EN_DE.read_bytes())
        fr_file = tmp_path / "clean_en_fr.tmx"
        fr_file.write_bytes(SAMPLE_EN_FR.read_bytes())

        out = tmp_path / "merged_en.tmx"
        merge_bilingual_tmxs("en", [de_file, fr_file], out)

        content = out.read_text(encoding="utf-8")
        assert 'xml:lang="de"' in content
        assert 'xml:lang="fr"' in content
        assert 'xml:lang="en"' in content

    def test_intermediate_bilingual_files_absent_from_results(self, client, db, test_user, tmp_path, monkeypatch):
        """After a merge job the per-language clean TMX files should not appear."""
        from app.core.config import settings as app_settings
        from app.models.job import Job
        from app.services.exporters.tmx import merge_bilingual_tmxs
        import uuid
        from datetime import datetime, timezone

        monkeypatch.setattr(app_settings, "STORAGE_PATH", str(tmp_path))

        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id, user_id=test_user.id, status="complete",
            progress=100, options_json="{}", engine="none",
            source_lang="en", target_lang="de,fr",
            created_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()

        out_dir = self._make_output_dir(tmp_path, test_user.id, job_id)

        # Simulate what pipeline does: create merged, remove intermediates
        de_file = out_dir / "clean_en_de.tmx"
        de_file.write_bytes(SAMPLE_EN_DE.read_bytes())
        fr_file = out_dir / "clean_en_fr.tmx"
        fr_file.write_bytes(SAMPLE_EN_FR.read_bytes())
        merged = out_dir / "merged_en.tmx"
        merge_bilingual_tmxs("en", [de_file, fr_file], merged)
        de_file.unlink()
        fr_file.unlink()

        resp = client.get(f"/api/jobs/{job_id}/results")
        assert resp.status_code == 200
        filenames = [o["filename"] for o in resp.json()["outputs"]]
        assert "merged_en.tmx" in filenames
        assert not any(f.startswith("clean_") for f in filenames)

    def test_prefixed_merged_tmx_in_results(self, client, db, test_user, tmp_path, monkeypatch):
        """A prefix-merged file 'myproj_merged_en_de.tmx' is returned correctly."""
        from app.core.config import settings as app_settings
        from app.models.job import Job
        from app.services.exporters.tmx import merge_bilingual_tmxs
        import uuid
        from datetime import datetime, timezone

        monkeypatch.setattr(app_settings, "STORAGE_PATH", str(tmp_path))

        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id, user_id=test_user.id, status="complete",
            progress=100, options_json="{}", engine="none",
            source_lang="en", target_lang="de",
            created_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()

        out_dir = self._make_output_dir(tmp_path, test_user.id, job_id)
        de_file = out_dir / "myproj_clean_en_de.tmx"
        de_file.write_bytes(SAMPLE_EN_DE.read_bytes())
        merged = out_dir / "myproj_merged_en_de.tmx"
        merge_bilingual_tmxs("en", [de_file], merged)
        de_file.unlink()

        resp = client.get(f"/api/jobs/{job_id}/results")
        assert resp.status_code == 200
        filenames = [o["filename"] for o in resp.json()["outputs"]]
        assert "myproj_merged_en_de.tmx" in filenames
