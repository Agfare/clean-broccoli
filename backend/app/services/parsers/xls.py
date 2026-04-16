from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import openpyxl

from app.services.parsers.base import ParseResult, Segment


def _detect_columns(headers: List[Optional[str]], source_lang: str, target_lang: str) -> Tuple[int, int]:
    """
    Detect source and target column indices from header row.
    Returns (source_col_idx, target_col_idx) (0-based).
    Falls back to (0, 1) if no match found.
    """
    src_lang_lower = source_lang.lower().split("-")[0]
    tgt_lang_lower = target_lang.lower().split("-")[0]

    source_idx: Optional[int] = None
    target_idx: Optional[int] = None

    for i, h in enumerate(headers):
        if h is None:
            continue
        hl = h.lower()
        if source_idx is None and ("source" in hl or src_lang_lower in hl):
            source_idx = i
        if target_idx is None and ("target" in hl or tgt_lang_lower in hl):
            target_idx = i

    if source_idx is None or target_idx is None:
        return 0, 1

    return source_idx, target_idx


def parse_xls(path: Path, source_lang: str, target_lang: str) -> ParseResult:
    warnings: List[str] = []
    encoding_ok = True  # XLS/XLSX are binary formats

    try:
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as e:
        return ParseResult(
            segments=[],
            warnings=[f"Failed to open XLS file: {e}"],
            encoding_ok=encoding_ok,
            source_lang=source_lang,
            target_lang=target_lang,
        )

    ws = wb.active
    if ws is None:
        return ParseResult(
            segments=[],
            warnings=["No active sheet found"],
            encoding_ok=encoding_ok,
            source_lang=source_lang,
            target_lang=target_lang,
        )

    all_rows = list(ws.iter_rows(values_only=True))
    if not all_rows:
        return ParseResult(
            segments=[],
            warnings=["Sheet is empty"],
            encoding_ok=encoding_ok,
            source_lang=source_lang,
            target_lang=target_lang,
        )

    # Determine if first row is a header
    first_row = [str(c) if c is not None else None for c in all_rows[0]]
    has_header = any(
        c and isinstance(c, str) and not c.strip().lstrip("-").replace(".", "").isdigit()
        for c in first_row
    )

    if has_header:
        src_col, tgt_col = _detect_columns(first_row, source_lang, target_lang)
        data_rows = all_rows[1:]
        start_row = 2
    else:
        src_col, tgt_col = 0, 1
        data_rows = all_rows
        start_row = 1

    segments: List[Segment] = []
    for row_offset, row in enumerate(data_rows):
        row_num = start_row + row_offset

        if all(c is None or str(c).strip() == "" for c in row):
            continue

        def get_cell(col_idx: int) -> str:
            if col_idx < len(row) and row[col_idx] is not None:
                return str(row[col_idx]).strip()
            return ""

        source_text = get_cell(src_col)
        target_text = get_cell(tgt_col)

        if not source_text and not target_text:
            continue

        segments.append(
            Segment(
                id=str(row_num),
                source=source_text,
                target=target_text,
                source_lang=source_lang,
                target_lang=target_lang,
                metadata={"row": row_num},
            )
        )

    wb.close()

    return ParseResult(
        segments=segments,
        warnings=warnings,
        encoding_ok=encoding_ok,
        source_lang=source_lang,
        target_lang=target_lang,
    )
