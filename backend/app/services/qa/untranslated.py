from __future__ import annotations

from typing import List

from app.services.parsers.base import Segment


def find_untranslated(segments: List[Segment]) -> List[str]:
    """
    Returns segment ids where:
    - target is empty (after stripping whitespace), OR
    - target equals source (after stripping whitespace)
    """
    untranslated_ids: List[str] = []

    for seg in segments:
        src_stripped = seg.source.strip()
        tgt_stripped = seg.target.strip()

        if not tgt_stripped:
            untranslated_ids.append(seg.id)
        elif tgt_stripped == src_stripped:
            untranslated_ids.append(seg.id)

    return untranslated_ids
