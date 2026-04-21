from __future__ import annotations

import gc
import hashlib
import json
import logging
import shutil
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

log = logging.getLogger(__name__)

import redis as redis_lib

from app.constants import MT_ERROR_LIMIT, MT_QUALITY_THRESHOLD, PROGRESS_KEY_TTL
from app.core.config import settings
from app.workers.celery_app import celery_app

redis_client = redis_lib.Redis.from_url(settings.REDIS_URL, decode_responses=True)

# ---------------------------------------------------------------------------
# File-based crash log — written synchronously, survives OOM kills
# ---------------------------------------------------------------------------

def _crash_log(tag: str, job_id: str, detail: str = "") -> None:
    """Append one timestamped line to {STORAGE_PATH}/crash_log.txt.

    Intentionally bare-bones: no imports that could fail, no formatting that
    could raise.  Called at every major checkpoint so that even a silent
    OOM-kill leaves a trace showing the last checkpoint the process reached.
    """
    try:
        log_path = Path(settings.STORAGE_PATH) / "crash_log.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        line = f"{ts}  [{tag}]  job={job_id}  {detail}\n"
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass  # never let logging crash the worker


# ---------------------------------------------------------------------------
# Cooperative cancellation
# ---------------------------------------------------------------------------
# Output path builder
# ---------------------------------------------------------------------------

def _build_output_paths(
    output_dir: Path,
    source_lang: str,
    target_lang: str,
    output_prefix: str,
) -> Dict[str, Path]:
    """Return the eight canonical output file paths for one language pair.

    *output_prefix* is prepended followed by an underscore when non-empty,
    so ``prefix="v2"`` yields ``v2_clean_en_de.tmx``, while an empty prefix
    yields ``clean_en_de.tmx`` (original behaviour).

    Extracting this into a named function lets tests import and exercise the
    real naming logic rather than an independent copy of it.
    """
    p = (output_prefix + "_") if output_prefix else ""
    return {
        "clean_tmx": output_dir / f"{p}clean_{source_lang}_{target_lang}.tmx",
        "clean_xls": output_dir / f"{p}clean_{source_lang}_{target_lang}.xlsx",
        "qa_xls":    output_dir / f"{p}qa_{source_lang}_{target_lang}.xlsx",
        "report":    output_dir / f"{p}qa_{source_lang}_{target_lang}.html",
        "dup_tmx":   output_dir / f"{p}duplicates_{source_lang}_{target_lang}.tmx",
        "dup_xls":   output_dir / f"{p}duplicates_{source_lang}_{target_lang}.xlsx",
        "ut_tmx":    output_dir / f"{p}untranslated_{source_lang}_{target_lang}.tmx",
        "ut_xls":    output_dir / f"{p}untranslated_{source_lang}_{target_lang}.xlsx",
    }


# ---------------------------------------------------------------------------

class JobCancelledError(Exception):
    """Raised cooperatively when a running job's DB status is set to 'cancelled'.

    Propagates through ExitStack so output-file writers are properly closed
    before the except block removes the partially-written output directory.
    """


def _is_cancelled(job_id: str) -> bool:
    """Open a *fresh* DB session and check whether the job has been cancelled.

    A separate session is used deliberately — the long-lived pipeline session
    may cache stale state and would miss a cancellation written by a concurrent
    API request.  Returns ``False`` on any error so the pipeline never halts
    spuriously due to a transient DB glitch.
    """
    try:
        from app.core.database import SessionLocal
        from app.models.job import Job as _Job
        _db = SessionLocal()
        try:
            _job = _db.query(_Job).filter(_Job.id == job_id).first()
            return _job is not None and _job.status == "cancelled"
        finally:
            _db.close()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

def _set_progress(job_id: str, step: str, pct: int, msg: str) -> None:
    key = f"job_progress:{job_id}"
    value = json.dumps({"step": step, "progress": pct, "message": msg})
    redis_client.set(key, value, ex=PROGRESS_KEY_TTL)


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

def _seg_hashes(source: str, target: str):
    """Return (src_h, tgt_h, exact_key) as 64/64/128-bit Python ints.

    Shared by _scan_pass and the pass-2 loop so both passes use identical hash
    logic and therefore produce identical keys for the same segment text.
    """
    def _h(text: str) -> int:
        return int.from_bytes(
            hashlib.sha256(
                text.strip().lower().encode("utf-8", errors="replace")
            ).digest()[:8],
            "big",
        )
    src_h = _h(source)
    tgt_h = _h(target)
    return src_h, tgt_h, (src_h << 64) | tgt_h


def _scan_pass(
    db_files,
    source_lang: str,
    target_lang: str,
    job_id: str,
    lang_idx: int,
    n_langs: int,
    pfx: str,
) -> tuple:
    """Stream every segment storing ONLY hash integers — no text, no IDs.

    Memory model
    ------------
    * ``seen_once``  — set of 128-bit ints for exact_keys seen exactly once.
                       Discarded entry-by-entry as duplicates are found, then
                       deleted wholesale after the loop.
    * ``dup_exact_keys`` — set of 128-bit ints for keys that appear 2+ times.
                           Typically tiny (only actual duplicates).
    * ``src_tgt_map`` — dict mapping 64-bit src_hash → first target hash (int)
                        OR set of target hashes if multiple targets seen.
                        Uses the cheapest representation per key.

    Peak cost ≈ 147 B/segment (vs ~615 B with UUID strings in value lists).
    For a 1 M-segment TM: ~147 MB peak, then falls to ~a few MB after the loop.

    scan_data keys
    --------------
    dup_exact_keys        — set[int]: 128-bit keys appearing 2+ times
    conflicting_src_hashes — set[int]: 64-bit src hashes with multiple targets
    n_exact_groups        — int: duplicate group count (for HTML report)
    n_same_src_groups     — int: conflicting-source group count (for HTML)
    n_untranslated        — int: untranslated segment count (for HTML)
    total                 — int: total segment count
    """

    # --- exact-dup tracking (no IDs stored) ---
    seen_once: set = set()       # exact_keys seen exactly once so far
    dup_exact_keys: set = set()  # exact_keys seen 2+ times

    # --- same-src-diff-tgt tracking ---
    # src_h → first tgt_h (int)  OR  set[int] when multiple targets seen.
    # Storing a plain int avoids the ~220 B overhead of a single-element set.
    src_tgt_map: dict = {}

    n_untranslated = 0
    parse_warnings: List[str] = []
    total = 0

    def _progress_cb(n: int) -> None:
        pct = _lang_progress(lang_idx, n_langs, 5 + min(13, n // 5_000))
        _set_progress(job_id, "scanning", pct,
                      f"{pfx}Scanning… {n:,} segments read")

    for seg in _iter_all_files(db_files, source_lang, target_lang,
                               parse_warnings, progress_callback=_progress_cb):
        total += 1
        if total % 1_000 == 0:
            _crash_log("SCAN_HEARTBEAT", job_id,
                       f"n={total} seen_once={len(seen_once)} "
                       f"dups={len(dup_exact_keys)} "
                       f"src_map={len(src_tgt_map)}")
        src_h, tgt_h, exact_key = _seg_hashes(seg.source, seg.target)

        # Exact-dup tracking — no IDs, just the hash
        if exact_key in dup_exact_keys:
            pass  # already confirmed duplicate; nothing to do
        elif exact_key in seen_once:
            dup_exact_keys.add(exact_key)
            seen_once.discard(exact_key)  # reclaim memory immediately
        else:
            seen_once.add(exact_key)

        # Same-source-different-target tracking
        existing = src_tgt_map.get(src_h)
        if existing is None:
            src_tgt_map[src_h] = tgt_h          # cheapest: plain int
        elif isinstance(existing, int):
            if existing != tgt_h:
                src_tgt_map[src_h] = {existing, tgt_h}  # upgrade to set
        else:
            existing.add(tgt_h)                  # already a set

        # Untranslated count (no ID needed — recomputed in pass 2)
        if not seg.target.strip() or src_h == tgt_h:
            n_untranslated += 1

    # Free the scan-time structures that are no longer needed
    del seen_once
    gc.collect()

    # Derive conflicting-source set (only sources with 2+ distinct targets)
    conflicting_src_hashes: set = {
        sh for sh, v in src_tgt_map.items() if isinstance(v, set)
    }
    del src_tgt_map
    gc.collect()

    scan_data = {
        "dup_exact_keys": dup_exact_keys,
        "conflicting_src_hashes": conflicting_src_hashes,
        "n_exact_groups": len(dup_exact_keys),
        "n_same_src_groups": len(conflicting_src_hashes),
        "n_untranslated": n_untranslated,
        "total": total,
    }
    return scan_data, parse_warnings


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(bind=True)
def run_pipeline(self, job_id: str) -> None:  # noqa: C901
    # This is the absolute first line executed — file log survives OOM kills
    _crash_log("TASK_START", job_id)

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

    _crash_log("IMPORTS_DONE", job_id)

    db = SessionLocal()

    try:
        # ------------------------------------------------------------------ #
        # 1. Load job
        # ------------------------------------------------------------------ #
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            _crash_log("JOB_NOT_FOUND", job_id)
            return

        # Guard: if the startup hook already reset this job to "failed" (because
        # a previous worker crashed mid-run), don't re-process it — the file may
        # be the very file that caused the crash.  The user must re-submit.
        if job.status in ("complete", "failed"):
            _crash_log("JOB_SKIP_STALE", job_id, f"status={job.status}")
            return

        job.status = "running"
        db.commit()

        _crash_log("STATUS_RUNNING", job_id)
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
            # PASS 1 — lightweight scan (hashes only, ~28 B/segment int keys)
            # -------------------------------------------------------------- #
            _set_progress(job_id, "scanning",
                          _lang_progress(lang_idx, n_langs, 3),
                          f"{_pfx}Scanning for duplicates…")

            _crash_log("SCAN_START", job_id,
                       f"lang={target_lang} n_files={len(db_files)} "
                       + " ".join(
                           f"{Path(f.stored_path).name}({Path(f.stored_path).stat().st_size // 1024}KB)"
                           if Path(f.stored_path).exists() else
                           f"{Path(f.stored_path).name}(MISSING)"
                           for f in db_files
                       ))
            scan_data, parse_warnings = _scan_pass(
                db_files, source_lang, target_lang,
                job_id, lang_idx, n_langs, _pfx,
            )
            _crash_log("SCAN_DONE", job_id,
                       f"total={scan_data['total']} "
                       f"dup_groups={scan_data['n_exact_groups']} "
                       f"ut={scan_data['n_untranslated']}")

            total_segments = scan_data["total"]
            if total_segments == 0:
                raise ValueError("No segments were parsed from the input files")

            _set_progress(job_id, "scanning",
                          _lang_progress(lang_idx, n_langs, 20),
                          f"{_pfx}Scanned {total_segments:,} segments — "
                          f"{scan_data['n_exact_groups']} duplicate groups, "
                          f"{scan_data['n_untranslated']} untranslated")

            # Cooperative cancellation check — between scan and pass-2
            if _is_cancelled(job_id):
                log.info("pipeline: job %s cancelled between scan and pass-2", job_id)
                raise JobCancelledError(f"Job {job_id} cancelled between scan and pass-2")

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

            # Output paths — built via the named helper so tests can import it
            _paths = _build_output_paths(
                output_dir, source_lang, target_lang, job.output_prefix or ""
            )
            clean_tmx_path = _paths["clean_tmx"]
            clean_xls_path = _paths["clean_xls"]
            qa_xls_path    = _paths["qa_xls"]
            report_path    = _paths["report"]
            dup_tmx_path   = _paths["dup_tmx"]
            dup_xls_path   = _paths["dup_xls"]
            ut_tmx_path    = _paths["ut_tmx"]
            ut_xls_path    = _paths["ut_xls"]

            # Decide which separate-file writers to open
            has_dups = bool(scan_data["dup_exact_keys"])
            has_untranslated = scan_data["n_untranslated"] > 0

            html_acc: Optional[HtmlStatsAccumulator] = None
            if options.outputs_html_report:
                html_acc = HtmlStatsAccumulator(
                    total_segments=total_segments,
                    n_exact_groups=scan_data["n_exact_groups"],
                    n_same_src_groups=scan_data["n_same_src_groups"],
                    n_untranslated=scan_data["n_untranslated"],
                    parse_warnings=parse_warnings,
                    options=options,
                )

            _set_progress(job_id, "processing",
                          _lang_progress(lang_idx, n_langs, 25),
                          f"{_pfx}Running QA checks and writing outputs…")

            _crash_log("PASS2_START", job_id, f"lang={target_lang} total={total_segments}")
            mt_consecutive_errors = 0
            mt_aborted = False
            seg_count = 0

            # Pass-2 exact-dup tracking: we see each segment fresh and mark the
            # SECOND (and later) occurrence as a duplicate, keeping the first.
            # Only duplicate groups need tracking here, so this set stays small.
            seen_exact_p2: set = set()

            with ExitStack() as stack:
                _crash_log("WRITERS_OPEN", job_id,
                           f"tmx={options.outputs_tmx} "
                           f"xls={options.outputs_clean_xls} "
                           f"qa={options.outputs_qa_xls} "
                           f"dup_sep={options.move_duplicates_to_separate_file} "
                           f"ut_sep={options.move_untranslated_to_separate_file} "
                           f"has_dups={has_dups} has_ut={has_untranslated}")
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

                    # Cooperative cancellation — checked every 5 000 segments
                    if seg_count % 5_000 == 0 and _is_cancelled(job_id):
                        log.info(
                            "pipeline: job %s cancelled at pass-2 segment %d",
                            job_id, seg_count,
                        )
                        raise JobCancelledError(
                            f"Job {job_id} cancelled at pass-2 segment {seg_count}"
                        )

                    # Re-derive hashes — identical logic to _scan_pass so keys match
                    src_h, tgt_h, exact_key = _seg_hashes(seg.source, seg.target)

                    # Exact-dup: keep first occurrence, mark subsequent as dup
                    if exact_key in scan_data["dup_exact_keys"]:
                        if exact_key in seen_exact_p2:
                            is_dup = True     # 2nd+ occurrence
                        else:
                            seen_exact_p2.add(exact_key)
                            is_dup = False    # 1st occurrence — keep it
                    else:
                        is_dup = False

                    is_same_src_diff_tgt = src_h in scan_data["conflicting_src_hashes"]
                    is_untranslated = (not seg.target.strip()) or (src_h == tgt_h)

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
                            if score < MT_QUALITY_THRESHOLD:
                                issues.append(QAIssue(
                                    segment_id=seg.id, check="mt_quality",
                                    severity="warning",
                                    message=f"MT quality score {score:.2f} is below threshold {MT_QUALITY_THRESHOLD:.2f}",
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
            _crash_log("PASS2_DONE", job_id, f"lang={target_lang} wrote={seg_count}")

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
        # 8. Merge per-language clean TMXs into one multi-language file
        # ------------------------------------------------------------------ #
        if options.merge_to_tmx and options.outputs_tmx:
            _set_progress(job_id, "merging", 96, "Merging language pairs into single TMX…")
            _crash_log("MERGE_START", job_id, f"n_langs={n_langs}")

            # Collect the per-language clean TMX paths that were written
            clean_tmx_paths = [
                _build_output_paths(
                    output_dir, source_lang, tl, job.output_prefix or ""
                )["clean_tmx"]
                for tl in target_langs
            ]
            existing_clean_tmxs = [p for p in clean_tmx_paths if p.exists()]

            if existing_clean_tmxs:
                pfx = (job.output_prefix + "_") if job.output_prefix else ""
                if len(target_langs) == 1:
                    merged_name = f"{pfx}merged_{source_lang}_{target_langs[0]}.tmx"
                else:
                    merged_name = f"{pfx}merged_{source_lang}.tmx"
                merged_path = output_dir / merged_name

                from app.services.exporters.tmx import merge_bilingual_tmxs
                merge_bilingual_tmxs(source_lang, existing_clean_tmxs, merged_path)
                _crash_log("MERGE_DONE", job_id,
                           f"output={merged_name} src_files={len(existing_clean_tmxs)}")

                # Replace per-language clean TMXs with the single merged file
                output_files = [f for f in output_files if f not in existing_clean_tmxs]
                if merged_path.exists():
                    output_files.insert(0, merged_path)

                # Remove the intermediate bilingual clean TMX files from disk
                for p_tmx in existing_clean_tmxs:
                    try:
                        p_tmx.unlink(missing_ok=True)
                    except OSError:
                        pass

        # ------------------------------------------------------------------ #
        # 9. Save output file records to DB
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
        _crash_log("TASK_COMPLETE", job_id)

    except JobCancelledError:
        # Job was cancelled by the user — status is already 'cancelled' in the
        # DB (set by the cancel endpoint).  Clean up any output files that were
        # partially written during this run, then return cleanly so Celery does
        # not mark the task as failed.
        _crash_log("CANCELLED", job_id)
        log.info("pipeline: job %s cancelled — cleaning up output files", job_id)
        try:
            # user_id is always set before any JobCancelledError can be raised
            output_dir = Path(settings.STORAGE_PATH) / str(user_id) / job_id / "output"
            if output_dir.exists():
                shutil.rmtree(output_dir, ignore_errors=True)
                _crash_log("CANCELLED_CLEANUP", job_id, "removed output dir")
                log.info("pipeline: removed output dir for cancelled job %s", job_id)
        except Exception as _ce:
            log.warning("pipeline: cleanup error for cancelled job %s: %s", job_id, _ce)
        # Clean up input-file DB records and physical files
        try:
            _db_inputs = db.query(UploadedFile).filter(UploadedFile.job_id == job_id).all()
            for _f in _db_inputs:
                try:
                    _p = Path(_f.stored_path)
                    if _p.exists():
                        _p.unlink(missing_ok=True)
                except OSError:
                    pass
                db.delete(_f)
            if _db_inputs:
                db.commit()
                log.info(
                    "pipeline: removed %d input file record(s) for cancelled job %s",
                    len(_db_inputs), job_id,
                )
        except Exception as _fe:
            log.warning("pipeline: file-record cleanup error for cancelled job %s: %s", job_id, _fe)
        # Delete the Redis progress key (cancel endpoint already set 'cancelled' event)
        try:
            redis_client.delete(f"job_progress:{job_id}")
        except Exception:
            pass
        return  # Celery sees SUCCESS — correct, the cancellation was intentional

    except BaseException as exc:
        # BaseException catches MemoryError, SystemExit, KeyboardInterrupt —
        # all of which are silently swallowed by Celery's solo pool on Windows
        # when using plain "except Exception".
        error_msg = f"{type(exc).__name__}: {exc}"
        _crash_log("EXCEPTION", job_id, error_msg[:300])
        log.exception("pipeline: job %s failed: %s", job_id, error_msg[:300])
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = error_msg[:1000]
                db.commit()
        except Exception:
            pass
        try:
            _set_progress(job_id, "error", 0, error_msg[:300])
        except Exception:
            pass
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
