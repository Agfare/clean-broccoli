from __future__ import annotations

import gc
import hashlib
import json
from collections import defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import redis as redis_lib

from app.core.config import settings
from app.workers.celery_app import celery_app

redis_client = redis_lib.Redis.from_url(settings.REDIS_URL, decode_responses=True)


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

def _set_progress(job_id: str, step: str, pct: int, msg: str) -> None:
    key = f"job_progress:{job_id}"
    value = json.dumps({"step": step, "progress": pct, "message": msg})
    redis_client.set(key, value, ex=3600)


def _lang_progress(lang_idx: int, n_langs: int, local_pct: int) -> int:
    """Map a 0-100 local percentage within one lang pass to global 0-99 progress."""
    per_lang = 98 // n_langs
    return lang_idx * per_lang + local_pct * per_lang // 100


# ---------------------------------------------------------------------------
# Streaming segment iterators
# ---------------------------------------------------------------------------

def _iter_all_files(
    db_files,
    source_lang: str,
    target_lang: str,
    warnings_list: List[str],
    progress_callback=None,
) -> Iterator:
    """Yield every Segment from every uploaded file, one at a time.

    Delegates to the appropriate parser iterator; appends parse warnings to
    *warnings_list*.  No segment list is ever accumulated — memory stays flat.
    """
    from app.services.parsers.csv import iter_csv
    from app.services.parsers.tmx import iter_tmx
    from app.services.parsers.xls import iter_xls

    for db_file in db_files:
        fpath = Path(db_file.stored_path)
        ext = fpath.suffix.lower()
        fname = db_file.original_filename
        file_warnings: List[str] = []

        cb = None
        if progress_callback is not None:
            cb = progress_callback

        if ext == ".tmx":
            it = iter_tmx(fpath, source_lang, target_lang,
                          warnings=file_warnings, progress_callback=cb)
        elif ext in (".xls", ".xlsx"):
            it = iter_xls(fpath, source_lang, target_lang,
                          warnings=file_warnings, progress_callback=cb)
        elif ext == ".csv":
            it = iter_csv(fpath, source_lang, target_lang,
                          warnings=file_warnings, progress_callback=cb)
        else:
            warnings_list.append(f"Skipping unsupported file: {fname}")
            continue

        yield from it
        warnings_list.extend(file_warnings)


# ---------------------------------------------------------------------------
# Pass 1 — lightweight scan
# ---------------------------------------------------------------------------

def _scan_pass(
    db_files,
    source_lang: str,
    target_lang: str,
    job_id: str,
    lang_idx: int,
    n_langs: int,
    pfx: str,
) -> tuple:
    """Stream every segment and record only SHA-256 hashes.

    Memory cost: ~140 bytes per segment (two 64-char hex strings + ID) instead
    of ~20 KB per segment with full text.  Returns (scan_data, parse_warnings).

    scan_data keys
    --------------
    exact_dup_ids        — IDs of exact duplicates (all but the first in each group)
    same_src_diff_tgt_ids — IDs in same-source / different-target groups
    exact_groups         — list of ID-lists (for HTML report)
    same_src_diff_tgt_groups — list of ID-lists (for HTML report)
    untranslated_id_set  — set of untranslated IDs (fast O(1) lookup)
    untranslated_ids     — ordered list of untranslated IDs (for HTML report)
    total                — total segment count
    """

    def _h(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

    def _norm(text: str) -> str:
        return text.strip().lower()

    exact_map: Dict[str, List[str]] = defaultdict(list)    # exact_key → [ids]
    src_map: Dict[str, List[str]] = defaultdict(list)       # src_hash → [ids]
    src_tgt_map: Dict[str, List[str]] = defaultdict(list)   # src_hash → [tgt_hashes]
    untranslated_id_set: set = set()
    untranslated_ids: List[str] = []
    parse_warnings: List[str] = []
    total = 0

    def _progress_cb(n: int) -> None:
        pct = _lang_progress(lang_idx, n_langs, 5 + min(13, n // 5_000))
        _set_progress(job_id, "scanning", pct,
                      f"{pfx}Scanning… {n:,} segments read")

    for seg in _iter_all_files(db_files, source_lang, target_lang,
                               parse_warnings, progress_callback=_progress_cb):
        total += 1

        src_h = _h(_norm(seg.source))
        tgt_h = _h(_norm(seg.target))
        exact_key = src_h + tgt_h

        exact_map[exact_key].append(seg.id)
        src_map[src_h].append(seg.id)
        src_tgt_map[src_h].append(tgt_h)

        if not seg.target.strip() or src_h == tgt_h:
            untranslated_id_set.add(seg.id)
            untranslated_ids.append(seg.id)

    # Build exact-duplicate sets
    exact_groups = [ids for ids in exact_map.values() if len(ids) > 1]
    exact_dup_ids: set = set()
    for group in exact_groups:
        for sid in group[1:]:   # keep the first occurrence
            exact_dup_ids.add(sid)

    # Build same-source-different-target sets
    same_src_diff_tgt_groups = []
    same_src_diff_tgt_ids: set = set()
    for src_h, ids in src_map.items():
        if len(ids) > 1 and len(set(src_tgt_map[src_h])) > 1:
            same_src_diff_tgt_groups.append(ids)
            same_src_diff_tgt_ids.update(ids)

    # Free the large intermediate dicts immediately
    del exact_map, src_map, src_tgt_map
    gc.collect()

    scan_data = {
        "exact_dup_ids": exact_dup_ids,
        "same_src_diff_tgt_ids": same_src_diff_tgt_ids,
        "exact_groups": exact_groups,
        "same_src_diff_tgt_groups": same_src_diff_tgt_groups,
        "untranslated_id_set": untranslated_id_set,
        "untranslated_ids": untranslated_ids,
        "total": total,
    }
    return scan_data, parse_warnings


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(bind=True)
def run_pipeline(self, job_id: str) -> None:  # noqa: C901
    from app.core.database import SessionLocal, init_db
    from app.core.security import decrypt_api_key
    from app.models.api_key import ApiKey
    from app.models.job import Job, UploadedFile
    from app.models.user import User  # noqa: F401 — registers 'users' in metadata
    init_db()
    from app.schemas.job import JobOptions
    from app.services.exporters.report import HtmlStatsAccumulator
    from app.services.exporters.tmx import TmxWriter
    from app.services.exporters.xls import CleanXlsWriter, QaXlsWriter
    from app.services.parsers.base import QAIssue
    from app.services.qa.duplicates import (  # noqa: F401 — kept for import hygiene
        find_duplicates,
    )
    from app.services.qa.numbers import check_numbers
    from app.services.qa.scripts import check_scripts
    from app.services.qa.tags import check_tags
    from app.services.qa.untranslated import find_untranslated  # noqa: F401
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

        _set_progress(job_id, "starting", 2, "Starting pipeline…")

        options = JobOptions(**json.loads(job.options_json))
        source_lang = job.source_lang
        target_langs = [t.strip() for t in job.target_lang.split(",") if t.strip()]
        user_id = job.user_id
        n_langs = len(target_langs)

        # ------------------------------------------------------------------ #
        # 2. Load uploaded files
        # ------------------------------------------------------------------ #
        db_files = db.query(UploadedFile).filter(
            UploadedFile.job_id == job_id,
            UploadedFile.user_id == user_id,
        ).all()

        if not db_files:
            raise ValueError("No input files found for this job")

        output_files: List[Path] = []

        for lang_idx, target_lang in enumerate(target_langs):
            _pfx = f"[{target_lang}] " if n_langs > 1 else ""

            # -------------------------------------------------------------- #
            # PASS 1 — lightweight scan (hashes only, ~140 B/segment)
            # -------------------------------------------------------------- #
            _set_progress(job_id, "scanning",
                          _lang_progress(lang_idx, n_langs, 3),
                          f"{_pfx}Scanning for duplicates…")

            scan_data, parse_warnings = _scan_pass(
                db_files, source_lang, target_lang,
                job_id, lang_idx, n_langs, _pfx,
            )

            total_segments = scan_data["total"]
            if total_segments == 0:
                raise ValueError("No segments were parsed from the input files")

            _set_progress(job_id, "scanning",
                          _lang_progress(lang_idx, n_langs, 20),
                          f"{_pfx}Scanned {total_segments:,} segments — "
                          f"{len(scan_data['exact_dup_ids'])} duplicates, "
                          f"{len(scan_data['untranslated_ids'])} untranslated")

            # -------------------------------------------------------------- #
            # Load MT engine (if requested)
            # -------------------------------------------------------------- #
            mt_engine = None
            if job.engine != "none":
                _set_progress(job_id, "mt_init",
                              _lang_progress(lang_idx, n_langs, 22),
                              f"{_pfx}Loading {job.engine} engine…")
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

            # -------------------------------------------------------------- #
            # PASS 2 — stream + QA + write outputs
            # Each Segment is created, checked, routed to writers, then freed.
            # Peak RAM = one Segment + open file handles.
            # -------------------------------------------------------------- #
            output_dir = Path(settings.STORAGE_PATH) / str(user_id) / job_id / "output"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Output paths
            clean_tmx_path = output_dir / f"clean_{source_lang}_{target_lang}.tmx"
            clean_xls_path = output_dir / f"clean_{source_lang}_{target_lang}.xlsx"
            qa_xls_path    = output_dir / f"qa_{source_lang}_{target_lang}.xlsx"
            report_path    = output_dir / f"qa_{source_lang}_{target_lang}.html"
            dup_tmx_path   = output_dir / f"duplicates_{source_lang}_{target_lang}.tmx"
            dup_xls_path   = output_dir / f"duplicates_{source_lang}_{target_lang}.xlsx"
            ut_tmx_path    = output_dir / f"untranslated_{source_lang}_{target_lang}.tmx"
            ut_xls_path    = output_dir / f"untranslated_{source_lang}_{target_lang}.xlsx"

            # Decide which separate-file writers to open
            has_dups = bool(scan_data["exact_dup_ids"])
            has_untranslated = bool(scan_data["untranslated_ids"])

            html_acc: Optional[HtmlStatsAccumulator] = None
            if options.outputs_html_report:
                html_acc = HtmlStatsAccumulator(
                    total_segments=total_segments,
                    exact_groups=scan_data["exact_groups"],
                    same_src_diff_tgt_groups=scan_data["same_src_diff_tgt_groups"],
                    untranslated_ids=scan_data["untranslated_ids"],
                    parse_warnings=parse_warnings,
                    options=options,
                )

            _set_progress(job_id, "processing",
                          _lang_progress(lang_idx, n_langs, 25),
                          f"{_pfx}Running QA checks and writing outputs…")

            mt_consecutive_errors = 0
            MT_ERROR_LIMIT = 3
            mt_aborted = False
            seg_count = 0

            with ExitStack() as stack:
                # Open only the writers that are actually needed
                clean_tmx_w = (
                    stack.enter_context(TmxWriter(clean_tmx_path, source_lang, target_lang))
                    if options.outputs_tmx else None
                )
                clean_xls_w = (
                    stack.enter_context(CleanXlsWriter(clean_xls_path))
                    if options.outputs_clean_xls else None
                )
                qa_xls_w = (
                    stack.enter_context(QaXlsWriter(qa_xls_path))
                    if options.outputs_qa_xls else None
                )
                dup_tmx_w = (
                    stack.enter_context(TmxWriter(dup_tmx_path, source_lang, target_lang))
                    if (options.move_duplicates_to_separate_file and has_dups) else None
                )
                dup_xls_w = (
                    stack.enter_context(CleanXlsWriter(dup_xls_path))
                    if (options.move_duplicates_to_separate_file and has_dups) else None
                )
                ut_tmx_w = (
                    stack.enter_context(TmxWriter(ut_tmx_path, source_lang, target_lang))
                    if (options.move_untranslated_to_separate_file and has_untranslated) else None
                )
                ut_xls_w = (
                    stack.enter_context(CleanXlsWriter(ut_xls_path))
                    if (options.move_untranslated_to_separate_file and has_untranslated) else None
                )

                for seg in _iter_all_files(db_files, source_lang, target_lang, parse_warnings):
                    seg_count += 1

                    if seg_count % 1_000 == 0:
                        pct = _lang_progress(
                            lang_idx, n_langs,
                            25 + int(seg_count / total_segments * 65),
                        )
                        _set_progress(
                            job_id, "processing", pct,
                            f"{_pfx}Processing {seg_count:,} / {total_segments:,} segments…",
                        )

                    is_dup = seg.id in scan_data["exact_dup_ids"]
                    is_same_src_diff_tgt = seg.id in scan_data["same_src_diff_tgt_ids"]
                    is_untranslated = seg.id in scan_data["untranslated_id_set"]

                    # ---- QA checks (all stateless — no list accumulation) ----
                    issues: List[QAIssue] = []

                    if is_untranslated and options.check_untranslated:
                        issues.append(QAIssue(
                            segment_id=seg.id, check="untranslated", severity="error",
                            message="Segment is untranslated (empty or same as source)",
                        ))

                    if is_dup:
                        issues.append(QAIssue(
                            segment_id=seg.id, check="duplicate", severity="warning",
                            message="Exact duplicate segment",
                        ))
                    if is_same_src_diff_tgt:
                        issues.append(QAIssue(
                            segment_id=seg.id, check="duplicate", severity="warning",
                            message="Same source text but different translations exist",
                        ))

                    issues.extend(check_tags(seg))
                    issues.extend(check_variables(seg))
                    if options.check_numbers:
                        issues.extend(check_numbers(seg))
                    if options.check_scripts:
                        issues.extend(check_scripts(seg))

                    # ---- MT scoring ----
                    if mt_engine and not mt_aborted and not is_untranslated:
                        try:
                            mt_translation = mt_engine.translate(
                                seg.source, source_lang, target_lang
                            )
                            score = mt_engine.similarity_score(mt_translation, seg.target)
                            mt_consecutive_errors = 0
                            if score < 0.6:
                                issues.append(QAIssue(
                                    segment_id=seg.id, check="mt_quality",
                                    severity="warning",
                                    message=f"MT quality score {score:.2f} is below threshold 0.60",
                                    detail=f"MT translation: {mt_translation[:100]}",
                                ))
                        except Exception as e:
                            mt_consecutive_errors += 1
                            parse_warnings.append(
                                f"MT scoring failed for segment {seg.id}: {e}"
                            )
                            if mt_consecutive_errors >= MT_ERROR_LIMIT:
                                mt_aborted = True
                                parse_warnings.append(
                                    f"MT scoring aborted after {MT_ERROR_LIMIT} consecutive "
                                    f"errors — check your API key and engine settings."
                                )

                    # ---- Route to output writers ----
                    exclude_from_clean = (
                        (options.remove_duplicates and is_dup)
                        or (options.remove_untranslated and is_untranslated)
                    )

                    if not exclude_from_clean:
                        if clean_tmx_w:
                            clean_tmx_w.write(seg)
                        if clean_xls_w:
                            clean_xls_w.write(seg)

                    if is_dup and options.move_duplicates_to_separate_file:
                        if dup_tmx_w:
                            dup_tmx_w.write(seg)
                        if dup_xls_w:
                            dup_xls_w.write(seg)

                    if is_untranslated and options.move_untranslated_to_separate_file:
                        if ut_tmx_w:
                            ut_tmx_w.write(seg)
                        if ut_xls_w:
                            ut_xls_w.write(seg)

                    if qa_xls_w:
                        qa_xls_w.write(seg, issues)

                    if html_acc:
                        html_acc.update(seg, issues)

            # ExitStack.__exit__ has saved/closed all open writer files by here

            # ---- Collect output paths ----
            if options.outputs_tmx and clean_tmx_path.exists():
                output_files.append(clean_tmx_path)
            if options.outputs_clean_xls and clean_xls_path.exists():
                output_files.append(clean_xls_path)
            if options.outputs_qa_xls and qa_xls_path.exists():
                output_files.append(qa_xls_path)
            if html_acc:
                _set_progress(job_id, "report",
                              _lang_progress(lang_idx, n_langs, 92),
                              f"{_pfx}Writing HTML report…")
                html_acc.write(report_path)
                output_files.append(report_path)
            if options.move_duplicates_to_separate_file and has_dups:
                if dup_tmx_path.exists():
                    output_files.append(dup_tmx_path)
                if dup_xls_path.exists():
                    output_files.append(dup_xls_path)
            if options.move_untranslated_to_separate_file and has_untranslated:
                if ut_tmx_path.exists():
                    output_files.append(ut_tmx_path)
                if ut_xls_path.exists():
                    output_files.append(ut_xls_path)

            gc.collect()

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
