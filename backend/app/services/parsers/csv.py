from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import List, Optional

from app.services.parsers.base import ParseResult, Segment, detect_encoding
from app.services.parsers.xls import _detect_columns

KNOWN_LANG_CODES = {
    "en", "de", "fr", "es", "it", "pt", "nl", "ru", "pl", "cs", "sk", "hu",
    "ro", "bg", "hr", "sr", "uk", "tr", "ar", "zh", "ja", "ko", "th", "vi",
    "id", "ms", "hi", "fa", "he", "el", "sv", "da", "no", "fi", "et", "lv", "lt",
}


def detect_csv_languages(path: Path) -> list[str]:
    """Return sorted list of language codes detected from CSV column headers."""
    import csv as _csv
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            sample = f.read(4096)
        # Detect delimiter
        try:
            dialect = _csv.Sniffer().sniff(sample, delimiters=",;\t")
            delimiter = dialect.delimiter
        except _csv.Error:
            delimiter = ","
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            reader = _csv.reader(f, delimiter=delimiter)
            header = next(reader, None)
        if not header:
            return []
        langs: set[str] = set()
        for cell in header:
            val = cell.strip().lower()
            primary = val.split("-")[0].split("_")[0]
            if primary in KNOWN_LANG_CODES:
                langs.add(primary)
                continue
            for sep in ("_", "-", " ", "."):
                for part in val.split(sep):
                    if part in KNOWN_LANG_CODES:
                        langs.add(part)
                        break
        return sorted(langs)
    except Exception:
        return []


def _detect_delimiter(sample: str) -> str:
    """Auto-detect CSV delimiter by trying comma, semicolon, tab."""
    for delimiter in (",", ";", "\t"):
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=delimiter)
            if dialect.delimiter == delimiter:
                return delimiter
        except csv.Error:
            pass

    # Count occurrences as fallback
    counts = {",": sample.count(","), ";": sample.count(";"), "\t": sample.count("\t")}
    return max(counts, key=lambda k: counts[k])


def parse_csv(path: Path, source_lang: str, target_lang: str) -> ParseResult:
    warnings: List[str] = []

    encoding = detect_encoding(path)
    encoding_ok = encoding == "utf-8"

    # Try UTF-8-sig first (handles BOM), then detected encoding
    content = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue

    if content is None:
        return ParseResult(
            segments=[],
            warnings=["Could not decode CSV file"],
            encoding_ok=False,
            source_lang=source_lang,
            target_lang=target_lang,
        )

    # Detect delimiter from first 4096 chars
    sample = content[:4096]
    delimiter = _detect_delimiter(sample)

    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    all_rows = list(reader)

    if not all_rows:
        return ParseResult(
            segments=[],
            warnings=["CSV file is empty"],
            encoding_ok=encoding_ok,
            source_lang=source_lang,
            target_lang=target_lang,
        )

    # Determine if first row is a header
    first_row = all_rows[0]
    has_header = any(
        c and not c.strip().lstrip("-").replace(".", "").isdigit()
        for c in first_row
    )

    if has_header:
        header_strs: List[Optional[str]] = [c if c.strip() else None for c in first_row]
        src_col, tgt_col = _detect_columns(header_strs, source_lang, target_lang)
        data_rows = all_rows[1:]
        start_row = 2
    else:
        src_col, tgt_col = 0, 1
        data_rows = all_rows
        start_row = 1

    segments: List[Segment] = []
    for row_offset, row in enumerate(data_rows):
        row_num = start_row + row_offset

        if not any(c.strip() for c in row):
            continue

        def get_cell(col_idx: int) -> str:
            if col_idx < len(row):
                return row[col_idx].strip()
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

    return ParseResult(
        segments=segments,
        warnings=warnings,
        encoding_ok=encoding_ok,
        source_lang=source_lang,
        target_lang=target_lang,
    )
