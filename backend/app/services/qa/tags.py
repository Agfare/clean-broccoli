from __future__ import annotations

import re
from collections import Counter
from typing import List

from app.services.parsers.base import QAIssue, Segment

# Patterns for inline tags
_TMX_INLINE = re.compile(
    r"<(ph|bpt|ept|it|hi|ut)(?:\s[^>]*)?>|</(ph|bpt|ept|it|hi|ut)>",
    re.IGNORECASE,
)
_XLIFF_TAGS = re.compile(
    r"<(g|x|bx|ex|ph|it|mrk)(?:\s[^>]*)?>|</(g|mrk)>|<(x|bx|ex|ph|it)\s*/?>",
    re.IGNORECASE,
)
_HTML_LIKE = re.compile(
    r"<(b|i|u|strong|em|span|a)(?:\s[^>]*)?>|</(b|i|u|strong|em|span|a)>|<br\s*/?>",
    re.IGNORECASE,
)

# Combined pattern to extract all tag names
_ALL_TAGS = re.compile(
    r"</?(?:ph|bpt|ept|it|hi|ut|g|x|bx|ex|mrk|b|i|u|strong|em|span|a|br)(?:\s[^>]*)?>",
    re.IGNORECASE,
)


def _extract_tag_names(text: str) -> List[str]:
    """Extract tag names (lowercased) from text, including opening/closing."""
    tags = []
    for match in _ALL_TAGS.finditer(text):
        raw = match.group(0)
        # Extract tag name
        name_match = re.match(r"</?([a-zA-Z]+)", raw)
        if name_match:
            tags.append(name_match.group(1).lower())
    return tags


def check_tags(segment: Segment) -> List[QAIssue]:
    issues: List[QAIssue] = []

    src_tags = Counter(_extract_tag_names(segment.source))
    tgt_tags = Counter(_extract_tag_names(segment.target))

    all_tag_names = set(src_tags.keys()) | set(tgt_tags.keys())

    for tag in all_tag_names:
        src_count = src_tags.get(tag, 0)
        tgt_count = tgt_tags.get(tag, 0)

        if src_count > tgt_count:
            issues.append(
                QAIssue(
                    segment_id=segment.id,
                    check="tags",
                    severity="error",
                    message=f"Tag <{tag}> appears {src_count}x in source but {tgt_count}x in target",
                    detail=f"Missing {src_count - tgt_count} occurrence(s) of <{tag}>",
                )
            )
        elif tgt_count > src_count:
            issues.append(
                QAIssue(
                    segment_id=segment.id,
                    check="tags",
                    severity="error",
                    message=f"Tag <{tag}> appears {tgt_count}x in target but {src_count}x in source",
                    detail=f"Extra {tgt_count - src_count} occurrence(s) of <{tag}>",
                )
            )

    return issues
