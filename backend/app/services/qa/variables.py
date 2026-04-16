from __future__ import annotations

import re
from collections import Counter
from typing import List

from app.services.parsers.base import QAIssue, Segment

# Variable patterns in priority order
_PATTERNS = [
    # {{variable}}
    re.compile(r"\{\{[a-zA-Z_]\w*\}\}"),
    # {name} - named placeholders
    re.compile(r"\{[a-zA-Z_]\w*\}"),
    # {0} - positional index placeholders
    re.compile(r"\{[0-9]+\}"),
    # %1$s - positional printf
    re.compile(r"%[0-9]+\$[sdifgxXeE]"),
    # %s %d %.2f etc (non-% variants only, avoid %% which is literal percent)
    re.compile(r"(?<!%)%[-+0-9*.]*[sdifgxXeEo]"),
    # ${variable}
    re.compile(r"\$\{[a-zA-Z_]\w*\}"),
    # $variable
    re.compile(r"\$[a-zA-Z_][a-zA-Z0-9_]*"),
]


def _extract_variables(text: str) -> List[str]:
    """Extract all variable placeholders from text, applying patterns in priority order."""
    matched_spans: set[tuple[int, int]] = set()
    variables = []

    for pattern in _PATTERNS:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            # Check if this span overlaps with any already-matched span
            overlaps = any(
                not (span[1] <= s[0] or span[0] >= s[1]) for s in matched_spans
            )
            if not overlaps:
                matched_spans.add(span)
                variables.append(m.group(0))

    return variables


def check_variables(segment: Segment) -> List[QAIssue]:
    issues: List[QAIssue] = []

    src_vars = Counter(_extract_variables(segment.source))
    tgt_vars = Counter(_extract_variables(segment.target))

    all_vars = set(src_vars.keys()) | set(tgt_vars.keys())

    for var in all_vars:
        src_count = src_vars.get(var, 0)
        tgt_count = tgt_vars.get(var, 0)

        if src_count > tgt_count:
            missing = src_count - tgt_count
            issues.append(
                QAIssue(
                    segment_id=segment.id,
                    check="variables",
                    severity="error",
                    message=f"Variable '{var}' appears {src_count}x in source but {tgt_count}x in target",
                    detail=f"Missing {missing} occurrence(s) of '{var}'",
                )
            )
        elif tgt_count > src_count:
            extra = tgt_count - src_count
            issues.append(
                QAIssue(
                    segment_id=segment.id,
                    check="variables",
                    severity="warning",
                    message=f"Variable '{var}' appears {tgt_count}x in target but {src_count}x in source",
                    detail=f"Extra {extra} occurrence(s) of '{var}' in target",
                )
            )

    return issues
