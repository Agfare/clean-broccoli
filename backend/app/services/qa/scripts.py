from __future__ import annotations

import unicodedata
from typing import List

from app.services.parsers.base import QAIssue, Segment

# Mapping from language primary subtag to expected Unicode script name fragments
_LANG_SCRIPT_MAP = {
    "ar": "ARABIC",
    "fa": "ARABIC",
    "ur": "ARABIC",
    "zh": "CJK",
    "ja": "CJK",
    "ko": "HANGUL",
    "ru": "CYRILLIC",
    "uk": "CYRILLIC",
    "bg": "CYRILLIC",
    "sr": "CYRILLIC",
    "el": "GREEK",
    "he": "HEBREW",
    "th": "THAI",
    "hi": "DEVANAGARI",
    "mr": "DEVANAGARI",
    "ne": "DEVANAGARI",
}

_PROPORTION_THRESHOLD = 0.20  # 20% of alphabetic characters


def _get_primary_lang(lang_code: str) -> str:
    return lang_code.lower().split("-")[0]


def _char_in_script(char: str, script_fragment: str) -> bool:
    """Check if a character belongs to the given script using unicodedata."""
    try:
        name = unicodedata.name(char, "")
        return script_fragment in name.upper()
    except (ValueError, TypeError):
        return False


def _is_alpha_like(char: str) -> bool:
    """Return True if character is alphabetic/ideographic (not space/punct/digit)."""
    cat = unicodedata.category(char)
    # L* = letter, M* = mark (combining), N* = number would be excluded
    return cat.startswith("L") or cat.startswith("M")


def check_scripts(segment: Segment) -> List[QAIssue]:
    issues: List[QAIssue] = []

    primary_lang = _get_primary_lang(segment.target_lang)
    expected_script = _LANG_SCRIPT_MAP.get(primary_lang)

    if not expected_script:
        return issues

    target = segment.target
    if not target.strip():
        return issues

    alpha_chars = [c for c in target if _is_alpha_like(c)]
    if not alpha_chars:
        return issues

    script_chars = [c for c in alpha_chars if _char_in_script(c, expected_script)]
    proportion = len(script_chars) / len(alpha_chars)

    if proportion < _PROPORTION_THRESHOLD:
        issues.append(
            QAIssue(
                segment_id=segment.id,
                check="scripts",
                severity="warning",
                message=(
                    f"Target language '{segment.target_lang}' expects {expected_script} script, "
                    f"but only {proportion:.1%} of characters match"
                ),
                detail=f"Expected >{_PROPORTION_THRESHOLD:.0%} {expected_script} characters, got {proportion:.1%}",
            )
        )

    return issues
