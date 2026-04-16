from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Generator, List, Optional

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


def _open_csv(path: Path):
    """Return (file_handle, delimiter, has_header, src_col, tgt_col, start_row, opened_enc).

    Detects encoding by probing, then peeks at the first row for header detection.
    Called by both iter_csv and parse_csv.
    """
    opened_enc = "utf-8-sig"
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                f.read(1024)
            opened_enc = enc
            break
        except (UnicodeDecodeError, ValueError):
            continue

    with open(path, "r", encoding=opened_enc, newline="", errors="replace") as f:
        sample = f.read(4096)
    delimiter = _detect_delimiter(sample)

    return opened_enc, delimiter


def iter_csv(
    path: Path,
    source_lang: str,
    target_lang: str,
    warnings: Optional[List[str]] = None,
    progress_callback=None,
) -> Generator[Segment, None, None]:
    """Yield Segment objects one at a time from a CSV file.

    Streams the file row-by-row without loading it fully into memory — safe for
    very large CSV files.  Appends parse warnings to *warnings*.
    """
    if warnings is None:
        warnings = []

    opened_enc, delimiter = _open_csv(path)

    try:
        with open(path, "r", encoding=opened_enc, newline="", errors="replace") as f:
            reader = csv.reader(f, delimiter=delimiter)
            first_row = next(reader, None)
            if first_row is None:
                return

            has_header = any(
                c and not c.strip().lstrip("-").replace(".", "").isdigit()
                for c in first_row
            )

            if has_header:
                header_strs: List[Optional[str]] = [c if c.strip() else None for c in first_row]
                src_col, tgt_col = _detect_columns(header_strs, source_lang, target_lang)
                start_row = 2
            else:
                src_col, tgt_col = 0, 1
                start_row = 1
                src = first_row[src_col].strip() if src_col < len(first_row) else ""
                tgt = first_row[tgt_col].strip() if tgt_col < len(first_row) else ""
                if src or tgt:
                    yield Segment(id="1", source=src, target=tgt,
                                  source_lang=source_lang, target_lang=target_lang)

            count = 0
            for row_offset, row in enumerate(reader):
                row_num = start_row + row_offset
                if not any(c.strip() for c in row):
                    continue
                src = row[src_col].strip() if src_col < len(row) else ""
                tgt = row[tgt_col].strip() if tgt_col < len(row) else ""
                if src or tgt:
                    count += 1
                    if progress_callback is not None and count % 5_000 == 0:
                        progress_callback(count)
                    yield Segment(
                        id=str(row_num),
                        source=src,
                        target=tgt,
                        source_lang=source_lang,
                        target_lang=target_lang,
                    )
    except Exception as e:
        warnings.append(f"CSV parse error: {e}")


def parse_csv(path: Path, source_lang: str, target_lang: str, progress_callback=None) -> ParseResult:
    """Parse a CSV file and return all segments as a list.

    For large files prefer *iter_csv* which yields one Segment at a time.
    """
    encoding = detect_encoding(path)
    encoding_ok = encoding == "utf-8"
    warnings: List[str] = []
    segments = list(
        iter_csv(path, source_lang, target_lang, warnings=warnings, progress_callback=progress_callback)
    )
    return ParseResult(
        segments=segments,
        warnings=warnings,
        encoding_ok=encoding_ok,
        source_lang=source_lang,
        target_lang=target_lang,
    )
