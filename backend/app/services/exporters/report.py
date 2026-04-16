from __future__ import annotations

import html
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.services.parsers.base import QAIssue, Segment


class HtmlStatsAccumulator:
    """Collects QA statistics segment-by-segment during streaming pass 2.

    Call :meth:`update` once per segment, then :meth:`write` to produce the
    HTML report.  Full segment text is never retained — only 100-char excerpts
    for flagged segments — so memory stays flat for any TM size.

    The duplicate / untranslated counts come from pass 1 as plain integers
    (``n_exact_groups``, ``n_same_src_groups``, ``n_untranslated``) rather than
    as lists of IDs, so no per-segment ID data needs to cross the scan boundary.
    """

    def __init__(
        self,
        total_segments: int,
        n_exact_groups: int,
        n_same_src_groups: int,
        n_untranslated: int,
        parse_warnings: List[str],
        options,
    ) -> None:
        self.total = total_segments
        self.n_exact_groups = n_exact_groups
        self.n_same_src_groups = n_same_src_groups
        self.n_untranslated = n_untranslated
        self.parse_warnings = parse_warnings
        self.options = options

        self.segs_with_errors = 0
        self.segs_with_warnings = 0
        self.source_words = 0
        self.target_words = 0
        self.check_counter: Counter = Counter()
        # Only flagged segments stored — as compact dicts, not full Segment objects
        self.flagged_data: List[dict] = []

    def update(self, seg: Segment, issues: List[QAIssue]) -> None:
        has_error = any(i.severity == "error" for i in issues)
        has_warning = any(i.severity == "warning" for i in issues)

        if has_error:
            self.segs_with_errors += 1
        elif has_warning:
            self.segs_with_warnings += 1
        else:
            self.source_words += len(seg.source.split())
            self.target_words += len(seg.target.split())

        for issue in issues:
            self.check_counter[issue.check] += 1

        if issues:
            self.flagged_data.append({
                "id": seg.id,
                "src": seg.source[:100] + ("..." if len(seg.source) > 100 else ""),
                "tgt": seg.target[:100] + ("..." if len(seg.target) > 100 else ""),
                "issues": list(issues),
            })

    def write(self, path: Path) -> None:
        """Render accumulated statistics to an HTML file at *path*."""
        _write_html_from_accumulator(self, path)


def _count_words(text: str) -> int:
    return len(text.split())


def export_html_report(
    segments: List[Segment],
    issues_map: Dict[str, List[QAIssue]],
    duplicates: Dict,
    untranslated_ids: List[str],
    job_options,
    stats: Dict,
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total = len(segments)

    segs_with_errors = sum(
        1 for sid, issues in issues_map.items() if any(i.severity == "error" for i in issues)
    )
    segs_with_warnings = sum(
        1 for sid, issues in issues_map.items()
        if any(i.severity == "warning" for i in issues)
        and not any(i.severity == "error" for i in issues)
    )
    clean_segs = total - segs_with_errors - segs_with_warnings
    error_rate = (segs_with_errors / total * 100) if total else 0
    warning_rate = (segs_with_warnings / total * 100) if total else 0

    # Word counts from clean segments
    clean_seg_ids = set(
        seg.id for seg in segments
        if not issues_map.get(seg.id)
    )
    source_words = sum(_count_words(seg.source) for seg in segments if seg.id in clean_seg_ids)
    target_words = sum(_count_words(seg.target) for seg in segments if seg.id in clean_seg_ids)

    # Issue type counts
    check_counter: Counter = Counter()
    for issues in issues_map.values():
        for issue in issues:
            check_counter[issue.check] += 1

    # Build flagged segment list
    flagged_segs = [
        seg for seg in segments
        if issues_map.get(seg.id)
    ]

    # HTML generation
    parts = ["""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TMClean QA Report</title>
<style>
  body { font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; background: #f9f9f9; }
  h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
  h2 { color: #2c3e50; margin-top: 30px; border-left: 4px solid #3498db; padding-left: 10px; }
  h3 { color: #555; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 20px; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  th { background-color: #3498db; color: white; padding: 10px 12px; text-align: left; font-weight: bold; }
  td { padding: 8px 12px; border-bottom: 1px solid #ddd; vertical-align: top; max-width: 400px; word-wrap: break-word; }
  tr:hover { background-color: #f5f5f5; }
  .row-error { background-color: #ffe6e6; }
  .row-warning { background-color: #fffde6; }
  .row-clean { background-color: #e8f8e8; }
  .badge-error { background: #e74c3c; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; }
  .badge-warning { background: #f39c12; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; }
  .badge-clean { background: #27ae60; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; }
  .stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 15px; margin-bottom: 20px; }
  .stat-card { background: white; border-radius: 8px; padding: 15px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .stat-card .value { font-size: 32px; font-weight: bold; color: #3498db; }
  .stat-card .label { font-size: 12px; color: #888; margin-top: 4px; }
  .excerpt { font-size: 12px; color: #555; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .issue-list { font-size: 12px; }
  .timestamp { color: #888; font-size: 13px; margin-top: 5px; }
  .section { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  pre { background: #f4f4f4; padding: 10px; border-radius: 4px; font-size: 12px; overflow-x: auto; }
</style>
</head>
<body>
"""]

    parts.append(f"""<h1>TMClean QA Report</h1>
<p class="timestamp">Generated: {timestamp}</p>

<div class="section">
<h2>Summary</h2>
<div class="stat-grid">
  <div class="stat-card"><div class="value">{total}</div><div class="label">Total Segments</div></div>
  <div class="stat-card"><div class="value" style="color:#e74c3c">{segs_with_errors}</div><div class="label">Segments with Errors</div></div>
  <div class="stat-card"><div class="value" style="color:#f39c12">{segs_with_warnings}</div><div class="label">Segments with Warnings</div></div>
  <div class="stat-card"><div class="value" style="color:#27ae60">{clean_segs}</div><div class="label">Clean Segments</div></div>
  <div class="stat-card"><div class="value" style="color:#e74c3c">{error_rate:.1f}%</div><div class="label">Error Rate</div></div>
  <div class="stat-card"><div class="value" style="color:#f39c12">{warning_rate:.1f}%</div><div class="label">Warning Rate</div></div>
</div>
</div>

<div class="section">
<h2>Word Count (Clean Segments)</h2>
<table>
  <tr><th>Metric</th><th>Count</th></tr>
  <tr><td>Source words (clean segments)</td><td>{source_words:,}</td></tr>
  <tr><td>Target words (clean segments)</td><td>{target_words:,}</td></tr>
</table>
</div>
""")

    if check_counter:
        parts.append("""<div class="section">
<h2>Issues Breakdown</h2>
<table>
  <tr><th>Issue Type</th><th>Count</th></tr>
""")
        for check, count in sorted(check_counter.items(), key=lambda x: -x[1]):
            parts.append(f"  <tr><td>{html.escape(check)}</td><td>{count}</td></tr>\n")
        parts.append("</table>\n</div>\n")

    # Duplicates section
    exact_dups = duplicates.get("exact", [])
    same_src_dups = duplicates.get("same_source_diff_target", [])
    parts.append("""<div class="section">
<h2>Duplicates</h2>
""")
    parts.append(f"<p><strong>Exact duplicates (same source + target):</strong> {len(exact_dups)} group(s)</p>\n")
    parts.append(f"<p><strong>Same source, different targets:</strong> {len(same_src_dups)} group(s)</p>\n")
    if exact_dups:
        parts.append("<h3>Exact Duplicate Groups</h3>\n<ul>\n")
        for group in exact_dups[:50]:  # Limit display
            parts.append(f"  <li>Segments: {html.escape(', '.join(str(g) for g in group))}</li>\n")
        if len(exact_dups) > 50:
            parts.append(f"  <li>...and {len(exact_dups) - 50} more groups</li>\n")
        parts.append("</ul>\n")
    parts.append("</div>\n")

    # Untranslated section
    parts.append(f"""<div class="section">
<h2>Untranslated Segments</h2>
<p><strong>{len(untranslated_ids)}</strong> segment(s) are untranslated (empty or same as source).</p>
""")
    if untranslated_ids:
        parts.append("<ul>\n")
        for sid in untranslated_ids[:50]:
            parts.append(f"  <li>Segment ID: {html.escape(str(sid))}</li>\n")
        if len(untranslated_ids) > 50:
            parts.append(f"  <li>...and {len(untranslated_ids) - 50} more</li>\n")
        parts.append("</ul>\n")
    parts.append("</div>\n")

    # Flagged segments table
    if flagged_segs:
        parts.append("""<div class="section">
<h2>Flagged Segments</h2>
<table>
  <tr>
    <th>ID</th>
    <th>Source (excerpt)</th>
    <th>Target (excerpt)</th>
    <th>Issues</th>
    <th>Severity</th>
  </tr>
""")
        for seg in flagged_segs:
            seg_issues = issues_map.get(seg.id, [])
            has_error = any(i.severity == "error" for i in seg_issues)
            has_warning = any(i.severity == "warning" for i in seg_issues)

            if has_error:
                row_class = "row-error"
                severity_badge = '<span class="badge-error">error</span>'
            elif has_warning:
                row_class = "row-warning"
                severity_badge = '<span class="badge-warning">warning</span>'
            else:
                row_class = "row-clean"
                severity_badge = '<span class="badge-clean">clean</span>'

            src_exc = html.escape(seg.source[:100] + ("..." if len(seg.source) > 100 else ""))
            tgt_exc = html.escape(seg.target[:100] + ("..." if len(seg.target) > 100 else ""))
            issue_msgs = "<br>".join(
                html.escape(i.message) for i in seg_issues
            )

            parts.append(f"""  <tr class="{row_class}">
    <td>{html.escape(str(seg.id))}</td>
    <td class="excerpt">{src_exc}</td>
    <td class="excerpt">{tgt_exc}</td>
    <td class="issue-list">{issue_msgs}</td>
    <td>{severity_badge}</td>
  </tr>
""")
        parts.append("</table>\n</div>\n")

    parts.append("</body>\n</html>")

    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))


# ---------------------------------------------------------------------------
# Streaming variant — used by the two-pass pipeline
# ---------------------------------------------------------------------------

def _write_html_from_accumulator(acc: HtmlStatsAccumulator, path: Path) -> None:
    """Render an HTML report from an :class:`HtmlStatsAccumulator`.

    Identical output to :func:`export_html_report` but operates on pre-computed
    stats collected during streaming pass 2 — no full segment list required.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total = acc.total
    segs_with_errors = acc.segs_with_errors
    segs_with_warnings = acc.segs_with_warnings
    clean_segs = total - segs_with_errors - segs_with_warnings
    error_rate = (segs_with_errors / total * 100) if total else 0
    warning_rate = (segs_with_warnings / total * 100) if total else 0
    source_words = acc.source_words
    target_words = acc.target_words
    check_counter = acc.check_counter
    n_exact_groups = acc.n_exact_groups
    n_same_src_groups = acc.n_same_src_groups
    n_untranslated = acc.n_untranslated

    # Re-use the same HTML template as export_html_report
    parts = ["""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TMClean QA Report</title>
<style>
  body { font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; background: #f9f9f9; }
  h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
  h2 { color: #2c3e50; margin-top: 30px; border-left: 4px solid #3498db; padding-left: 10px; }
  h3 { color: #555; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 20px; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  th { background-color: #3498db; color: white; padding: 10px 12px; text-align: left; font-weight: bold; }
  td { padding: 8px 12px; border-bottom: 1px solid #ddd; vertical-align: top; max-width: 400px; word-wrap: break-word; }
  tr:hover { background-color: #f5f5f5; }
  .row-error { background-color: #ffe6e6; }
  .row-warning { background-color: #fffde6; }
  .row-clean { background-color: #e8f8e8; }
  .badge-error { background: #e74c3c; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; }
  .badge-warning { background: #f39c12; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; }
  .badge-clean { background: #27ae60; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; }
  .stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 15px; margin-bottom: 20px; }
  .stat-card { background: white; border-radius: 8px; padding: 15px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .stat-card .value { font-size: 32px; font-weight: bold; color: #3498db; }
  .stat-card .label { font-size: 12px; color: #888; margin-top: 4px; }
  .excerpt { font-size: 12px; color: #555; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .issue-list { font-size: 12px; }
  .timestamp { color: #888; font-size: 13px; margin-top: 5px; }
  .section { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  pre { background: #f4f4f4; padding: 10px; border-radius: 4px; font-size: 12px; overflow-x: auto; }
</style>
</head>
<body>
"""]

    parts.append(f"""<h1>TMClean QA Report</h1>
<p class="timestamp">Generated: {timestamp}</p>

<div class="section">
<h2>Summary</h2>
<div class="stat-grid">
  <div class="stat-card"><div class="value">{total}</div><div class="label">Total Segments</div></div>
  <div class="stat-card"><div class="value" style="color:#e74c3c">{segs_with_errors}</div><div class="label">Segments with Errors</div></div>
  <div class="stat-card"><div class="value" style="color:#f39c12">{segs_with_warnings}</div><div class="label">Segments with Warnings</div></div>
  <div class="stat-card"><div class="value" style="color:#27ae60">{clean_segs}</div><div class="label">Clean Segments</div></div>
  <div class="stat-card"><div class="value" style="color:#e74c3c">{error_rate:.1f}%</div><div class="label">Error Rate</div></div>
  <div class="stat-card"><div class="value" style="color:#f39c12">{warning_rate:.1f}%</div><div class="label">Warning Rate</div></div>
</div>
</div>

<div class="section">
<h2>Word Count (Clean Segments)</h2>
<table>
  <tr><th>Metric</th><th>Count</th></tr>
  <tr><td>Source words (clean segments)</td><td>{source_words:,}</td></tr>
  <tr><td>Target words (clean segments)</td><td>{target_words:,}</td></tr>
</table>
</div>
""")

    if check_counter:
        parts.append("""<div class="section">
<h2>Issues Breakdown</h2>
<table>
  <tr><th>Issue Type</th><th>Count</th></tr>
""")
        for check, count in sorted(check_counter.items(), key=lambda x: -x[1]):
            parts.append(f"  <tr><td>{html.escape(check)}</td><td>{count}</td></tr>\n")
        parts.append("</table>\n</div>\n")

    # Duplicates
    parts.append("""<div class="section">
<h2>Duplicates</h2>
""")
    parts.append(f"<p><strong>Exact duplicates (same source + target):</strong> {n_exact_groups} group(s)</p>\n")
    parts.append(f"<p><strong>Same source, different targets:</strong> {n_same_src_groups} group(s)</p>\n")
    if n_exact_groups or n_same_src_groups:
        parts.append("<p>See the duplicate output file(s) for full details.</p>\n")
    parts.append("</div>\n")

    # Untranslated
    parts.append(f"""<div class="section">
<h2>Untranslated Segments</h2>
<p><strong>{n_untranslated}</strong> segment(s) are untranslated (empty or same as source).</p>
""")
    if n_untranslated:
        parts.append("<p>See the untranslated output file for full details.</p>\n")
    parts.append("</div>\n")

    # Flagged segments table
    if acc.flagged_data:
        parts.append("""<div class="section">
<h2>Flagged Segments</h2>
<table>
  <tr>
    <th>ID</th>
    <th>Source (excerpt)</th>
    <th>Target (excerpt)</th>
    <th>Issues</th>
    <th>Severity</th>
  </tr>
""")
        for item in acc.flagged_data:
            seg_issues = item["issues"]
            has_error = any(i.severity == "error" for i in seg_issues)
            has_warning = any(i.severity == "warning" for i in seg_issues)
            if has_error:
                row_class = "row-error"
                severity_badge = '<span class="badge-error">error</span>'
            elif has_warning:
                row_class = "row-warning"
                severity_badge = '<span class="badge-warning">warning</span>'
            else:
                row_class = "row-clean"
                severity_badge = '<span class="badge-clean">clean</span>'

            src_exc = html.escape(item["src"])
            tgt_exc = html.escape(item["tgt"])
            issue_msgs = "<br>".join(html.escape(i.message) for i in seg_issues)

            parts.append(f"""  <tr class="{row_class}">
    <td>{html.escape(str(item["id"]))}</td>
    <td class="excerpt">{src_exc}</td>
    <td class="excerpt">{tgt_exc}</td>
    <td class="issue-list">{issue_msgs}</td>
    <td>{severity_badge}</td>
  </tr>
""")
        parts.append("</table>\n</div>\n")

    parts.append("</body>\n</html>")

    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))
