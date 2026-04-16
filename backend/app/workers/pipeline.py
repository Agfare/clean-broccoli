from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import redis as redis_lib

from app.core.config import settings
from app.workers.celery_app import celery_app

redis_client = redis_lib.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _set_progress(job_id: str, step: str, pct: int, msg: str) -> None:
    key = f"job_progress:{job_id}"
    value = json.dumps({"step": step, "progress": pct, "message": msg})
    redis_client.set(key, value, ex=3600)


@celery_app.task(bind=True)
def run_pipeline(self, job_id: str) -> None:
    from app.core.database import SessionLocal, init_db
    from app.core.security import decrypt_api_key
    from app.models.api_key import ApiKey
    from app.models.job import Job, UploadedFile
    from app.models.user import (
        User,  # noqa: F401 — must import before Job to register 'users' in metadata
    )
    init_db()  # ensure all tables exist in this worker process
    from app.schemas.job import JobOptions
    from app.services.exporters.report import export_html_report
    from app.services.exporters.tmx import export_tmx
    from app.services.exporters.xls import export_clean_xls, export_qa_xls
    from app.services.parsers.base import QAIssue, Segment
    from app.services.parsers.csv import parse_csv
    from app.services.parsers.tmx import parse_tmx
    from app.services.parsers.xls import parse_xls
    from app.services.qa.duplicates import find_duplicates
    from app.services.qa.numbers import check_numbers
    from app.services.qa.scripts import check_scripts
    from app.services.qa.tags import check_tags
    from app.services.qa.untranslated import find_untranslated
    from app.services.qa.variables import check_variables

    db = SessionLocal()

    try:
        # ------------------------------------------------------------------ #
        # 1. Load job
        # ------------------------------------------------------------------ #
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return

        job.status = "running"
        db.commit()

        _set_progress(job_id, "parsing", 5, "Starting pipeline...")

        options = JobOptions(**json.loads(job.options_json))
        source_lang = job.source_lang
        target_langs = [t.strip() for t in job.target_lang.split(",") if t.strip()]
        user_id = job.user_id
        n_langs = len(target_langs)

        # ------------------------------------------------------------------ #
        # 2. Load uploaded files for this job
        # ------------------------------------------------------------------ #
        db_files = db.query(UploadedFile).filter(
            UploadedFile.job_id == job_id,
            UploadedFile.user_id == user_id,
        ).all()

        if not db_files:
            raise ValueError("No input files found for this job")

        output_files: List[Path] = []

        def _lang_progress(lang_idx: int, local_pct: int) -> int:
            """Map local 0-100 pct within one lang pass to global 0-99 progress."""
            per_lang = 98 // n_langs
            return lang_idx * per_lang + local_pct * per_lang // 100

        for lang_idx, target_lang in enumerate(target_langs):
            _pfx = f"[{target_lang}] " if n_langs > 1 else ""

            # ------------------------------------------------------------------ #
            # 3. Parse all files
            # ------------------------------------------------------------------ #
            _set_progress(job_id, "parsing", _lang_progress(lang_idx, 10), f"{_pfx}Parsing {len(db_files)} file(s)...")

            all_segments: List[Segment] = []
            parse_warnings: List[str] = []

            for db_file in db_files:
                fpath = Path(db_file.stored_path)
                ext = fpath.suffix.lower()

                if ext == ".tmx":
                    result = parse_tmx(fpath, source_lang, target_lang)
                elif ext in (".xls", ".xlsx"):
                    result = parse_xls(fpath, source_lang, target_lang)
                elif ext == ".csv":
                    result = parse_csv(fpath, source_lang, target_lang)
                else:
                    parse_warnings.append(f"Skipping unsupported file: {db_file.original_filename}")
                    continue

                all_segments.extend(result.segments)
                parse_warnings.extend(result.warnings)

            if not all_segments:
                raise ValueError("No segments were parsed from the input files")

            _set_progress(job_id, "parsing", _lang_progress(lang_idx, 20), f"{_pfx}Parsed {len(all_segments)} segments")

            # ------------------------------------------------------------------ #
            # 4. QA checks
            # ------------------------------------------------------------------ #
            # issues_map: segment_id -> list of QAIssue
            issues_map: Dict[str, List[QAIssue]] = defaultdict(list)

            # Untranslated check
            _set_progress(job_id, "qa_untranslated", _lang_progress(lang_idx, 25), f"{_pfx}Checking untranslated segments...")
            if options.check_untranslated:
                untranslated_ids = find_untranslated(all_segments)
                for sid in untranslated_ids:
                    issues_map[sid].append(
                        QAIssue(
                            segment_id=sid,
                            check="untranslated",
                            severity="error",
                            message="Segment is untranslated (empty or same as source)",
                        )
                    )
            else:
                untranslated_ids = []

            # Duplicate check
            _set_progress(job_id, "qa_duplicates", _lang_progress(lang_idx, 27), f"{_pfx}Checking duplicates...")
            duplicates = find_duplicates(all_segments)
            all_dup_ids: set = set()
            for group in duplicates.get("exact", []):
                for sid in group[1:]:  # Keep first, mark rest as duplicates
                    issues_map[sid].append(
                        QAIssue(
                            segment_id=sid,
                            check="duplicate",
                            severity="warning",
                            message=f"Exact duplicate of segment {group[0]}",
                        )
                    )
                    all_dup_ids.add(sid)
            for group in duplicates.get("same_source_diff_target", []):
                for sid in group:
                    issues_map[sid].append(
                        QAIssue(
                            segment_id=sid,
                            check="duplicate",
                            severity="warning",
                            message="Same source text but different translations exist",
                        )
                    )

            # Tag checks
            _set_progress(job_id, "qa_tags", _lang_progress(lang_idx, 30), f"{_pfx}Checking tags...")
            for seg in all_segments:
                tag_issues = check_tags(seg)
                if tag_issues:
                    issues_map[seg.id].extend(tag_issues)

            # Variable checks
            _set_progress(job_id, "qa_variables", _lang_progress(lang_idx, 40), f"{_pfx}Checking variables...")
            for seg in all_segments:
                var_issues = check_variables(seg)
                if var_issues:
                    issues_map[seg.id].extend(var_issues)

            # Number checks
            _set_progress(job_id, "qa_numbers", _lang_progress(lang_idx, 50), f"{_pfx}Checking numbers...")
            if options.check_numbers:
                for seg in all_segments:
                    num_issues = check_numbers(seg)
                    if num_issues:
                        issues_map[seg.id].extend(num_issues)

            # Script checks
            if options.check_scripts:
                _set_progress(job_id, "qa_scripts", _lang_progress(lang_idx, 55), f"{_pfx}Checking scripts...")
                for seg in all_segments:
                    script_issues = check_scripts(seg)
                    if script_issues:
                        issues_map[seg.id].extend(script_issues)

            # ------------------------------------------------------------------ #
            # 5. MT scoring (if engine != "none")
            # ------------------------------------------------------------------ #
            mt_engine = None
            if job.engine != "none":
                _set_progress(job_id, "mt", _lang_progress(lang_idx, 60), f"{_pfx}Loading {job.engine} MT engine...")
                api_key_record = db.query(ApiKey).filter(
                    ApiKey.user_id == user_id,
                    ApiKey.engine == job.engine,
                ).first()

                if api_key_record:
                    plain_key = decrypt_api_key(api_key_record.encrypted_key)
                    mt_engine = _create_mt_engine(job.engine, plain_key)
                else:
                    parse_warnings.append(
                        f"No API key found for engine '{job.engine}'; skipping MT scoring"
                    )

            if mt_engine is not None:
                _set_progress(job_id, "mt", _lang_progress(lang_idx, 62), f"{_pfx}Scoring {len(all_segments)} segments with MT engine...")
                mt_threshold = 0.6

                for idx, seg in enumerate(all_segments):
                    if idx % 10 == 0:
                        pct = _lang_progress(lang_idx, 62 + int((idx / len(all_segments)) * 15))
                        _set_progress(job_id, "mt", pct, f"{_pfx}MT scoring segment {idx + 1}/{len(all_segments)}...")

                    try:
                        mt_translation = mt_engine.translate(seg.source, source_lang, target_lang)
                        score = mt_engine.similarity_score(mt_translation, seg.target)

                        if score < mt_threshold:
                            issues_map[seg.id].append(
                                QAIssue(
                                    segment_id=seg.id,
                                    check="mt_quality",
                                    severity="warning",
                                    message=f"MT quality score {score:.2f} is below threshold {mt_threshold}",
                                    detail=f"MT translation: {mt_translation[:100]}",
                                )
                            )
                    except Exception as e:
                        parse_warnings.append(f"MT scoring failed for segment {seg.id}: {e}")

            # ------------------------------------------------------------------ #
            # 6. Apply options: filter/separate duplicates and untranslated
            # ------------------------------------------------------------------ #
            _set_progress(job_id, "exporting", _lang_progress(lang_idx, 78), f"{_pfx}Applying options and generating outputs...")

            clean_segments = list(all_segments)
            duplicate_segments: List[Segment] = []
            untranslated_segments: List[Segment] = []

            # Duplicates: collect separate file first, then optionally remove
            if options.remove_duplicates or options.move_duplicates_to_separate_file:
                dup_id_set = set()
                for group in duplicates.get("exact", []):
                    for sid in group[1:]:
                        dup_id_set.add(sid)

                if options.move_duplicates_to_separate_file:
                    duplicate_segments = [s for s in clean_segments if s.id in dup_id_set]

                if options.remove_duplicates:
                    clean_segments = [s for s in clean_segments if s.id not in dup_id_set]

            # Untranslated: collect separate file first, then optionally remove
            if untranslated_ids and (options.remove_untranslated or options.move_untranslated_to_separate_file):
                ut_id_set = set(untranslated_ids)

                if options.move_untranslated_to_separate_file:
                    untranslated_segments = [s for s in clean_segments if s.id in ut_id_set]

                if options.remove_untranslated:
                    clean_segments = [s for s in clean_segments if s.id not in ut_id_set]

            # ------------------------------------------------------------------ #
            # 7. Generate outputs
            # ------------------------------------------------------------------ #
            output_dir = Path(settings.STORAGE_PATH) / str(user_id) / job_id / "output"
            output_dir.mkdir(parents=True, exist_ok=True)

            if options.outputs_tmx:
                tmx_path = output_dir / f"clean_{source_lang}_{target_lang}.tmx"
                export_tmx(clean_segments, tmx_path, source_lang, target_lang)
                output_files.append(tmx_path)

            if options.outputs_clean_xls:
                xls_path = output_dir / f"clean_{source_lang}_{target_lang}.xlsx"
                export_clean_xls(clean_segments, xls_path)
                output_files.append(xls_path)

            if options.outputs_qa_xls:
                qa_xls_path = output_dir / f"qa_{source_lang}_{target_lang}.xlsx"
                export_qa_xls(all_segments, dict(issues_map), qa_xls_path)
                output_files.append(qa_xls_path)

            if options.outputs_html_report:
                report_path = output_dir / f"qa_{source_lang}_{target_lang}.html"
                stats_data = {
                    "total_segments": len(all_segments),
                    "parse_warnings": parse_warnings,
                }
                export_html_report(
                    all_segments,
                    dict(issues_map),
                    duplicates,
                    untranslated_ids,
                    options,
                    stats_data,
                    report_path,
                )
                output_files.append(report_path)

            # Separate duplicates file
            if options.move_duplicates_to_separate_file and duplicate_segments:
                dup_tmx_path = output_dir / f"duplicates_{source_lang}_{target_lang}.tmx"
                export_tmx(duplicate_segments, dup_tmx_path, source_lang, target_lang)
                output_files.append(dup_tmx_path)
                dup_xls_path = output_dir / f"duplicates_{source_lang}_{target_lang}.xlsx"
                export_clean_xls(duplicate_segments, dup_xls_path)
                output_files.append(dup_xls_path)

            # Separate untranslated file
            if options.move_untranslated_to_separate_file and untranslated_segments:
                ut_tmx_path = output_dir / f"untranslated_{source_lang}_{target_lang}.tmx"
                export_tmx(untranslated_segments, ut_tmx_path, source_lang, target_lang)
                output_files.append(ut_tmx_path)
                ut_xls_path = output_dir / f"untranslated_{source_lang}_{target_lang}.xlsx"
                export_clean_xls(untranslated_segments, ut_xls_path)
                output_files.append(ut_xls_path)

        # ------------------------------------------------------------------ #
        # 8. Save output file records to DB
        # ------------------------------------------------------------------ #
        for out_path in output_files:
            db_out = UploadedFile(
                user_id=user_id,
                job_id=job_id,
                original_filename=out_path.name,
                stored_path=str(out_path),
                created_at=datetime.now(timezone.utc),
            )
            db.add(db_out)
        db.commit()

        # ------------------------------------------------------------------ #
        # 9. Mark job complete
        # ------------------------------------------------------------------ #
        job.status = "complete"
        job.progress = 100
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        _set_progress(job_id, "complete", 100, "Done")

    except Exception as exc:
        error_msg = str(exc)

        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = error_msg[:1000]
                db.commit()
        except Exception:
            pass

        _set_progress(job_id, "error", 0, error_msg)
        raise

    finally:
        db.close()


def _create_mt_engine(engine_name: str, api_key: str):
    """Instantiate the appropriate MT engine."""
    from app.services.mt.anthropic import AnthropicEngine
    from app.services.mt.azure import AzureEngine
    from app.services.mt.deepl import DeepLEngine
    from app.services.mt.google import GoogleEngine

    engines = {
        "anthropic": AnthropicEngine,
        "deepl": DeepLEngine,
        "google": GoogleEngine,
        "azure": AzureEngine,
    }
    engine_cls = engines.get(engine_name)
    if engine_cls is None:
        raise ValueError(f"Unknown MT engine: {engine_name}")
    return engine_cls(api_key)
