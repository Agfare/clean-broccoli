from __future__ import annotations

import re
from collections import Counter
from typing import List

from app.services.parsers.base import QAIssue, Segment

# Match integers, decimals with . or , as separator, percentages
_NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)*\b")


def _extract_numbers(text: str) -> List[str]:
    """Extract all number-like tokens from text."""
    return _NUMBER_PATTERN.findall(text)


def check_numbers(segment: Segment) -> List[QAIssue]:
    issues: List[QAIssue] = []

    src_nums = Counter(_extract_numbers(segment.source))
    tgt_nums = Counter(_extract_numbers(segment.target))

    all_nums = set(src_nums.keys()) | set(tgt_nums.keys())

    for num in all_nums:
        src_count = src_nums.get(num, 0)
        tgt_count = tgt_nums.get(num, 0)

        if src_count != tgt_count:
            issues.append(
                QAIssue(
                    segment_id=segment.id,
                    check="numbers",
                    severity="warning",
                    message=f"Number '{num}' appears {src_count}x in source but {tgt_count}x in target",
                    detail=None,
                )
            )

    return issues
