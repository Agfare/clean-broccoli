from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from app.services.parsers.base import Segment


def _normalize(text: str) -> str:
    return text.strip().lower()


def find_duplicates(segments: List[Segment]) -> Dict:
    """
    Find duplicate segments.

    Returns:
        {
            "exact": list of groups (lists of segment ids) with identical source+target,
            "same_source_diff_target": list of groups with same source but different targets
        }
    """
    # Group by normalized source+target (exact duplicates)
    exact_groups: Dict[str, List[str]] = defaultdict(list)
    # Group by normalized source only
    source_groups: Dict[str, List[str]] = defaultdict(list)
    # Track target per segment for same_source_diff_target detection
    source_to_targets: Dict[str, List[str]] = defaultdict(list)

    for seg in segments:
        norm_src = _normalize(seg.source)
        norm_tgt = _normalize(seg.target)
        key_exact = f"{norm_src}\x00{norm_tgt}"

        exact_groups[key_exact].append(seg.id)
        source_groups[norm_src].append(seg.id)
        source_to_targets[norm_src].append(norm_tgt)

    # Exact duplicate groups (more than one segment with same src+tgt)
    exact: List[List[str]] = [
        ids for ids in exact_groups.values() if len(ids) > 1
    ]

    # Same source, different targets: groups where source appears multiple times
    # but not all targets are the same
    same_source_diff_target: List[List[str]] = []
    for norm_src, ids in source_groups.items():
        if len(ids) > 1:
            targets = source_to_targets[norm_src]
            unique_targets = set(targets)
            if len(unique_targets) > 1:
                same_source_diff_target.append(ids)

    return {
        "exact": exact,
        "same_source_diff_target": same_source_diff_target,
    }
