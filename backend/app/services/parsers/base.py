from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class Segment:
    id: str
    source: str
    target: str
    source_lang: str
    target_lang: str
    metadata: dict


@dataclass
class QAIssue:
    segment_id: str
    check: str  # "tags"|"variables"|"numbers"|"scripts"|"untranslated"|"duplicate"|"mt_quality"
    severity: str  # "error"|"warning"
    message: str
    detail: Optional[str] = None


@dataclass
class ParseResult:
    segments: List[Segment]
    warnings: List[str]
    encoding_ok: bool
    source_lang: str
    target_lang: str


def detect_encoding(path: Path) -> str:
    """Try UTF-8 then latin-1 to detect file encoding."""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        try:
            raw.decode("latin-1")
            return "latin-1"
        except UnicodeDecodeError:
            return "utf-8"  # fallback
