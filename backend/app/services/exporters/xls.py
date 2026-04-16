from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import openpyxl
from openpyxl.cell.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.services.parsers.base import QAIssue, Segment

# Fill colors
_RED_FILL = PatternFill(start_color="FFCCCC", end_color="FFCCCC", fill_type="solid")
_YELLOW_FILL = PatternFill(start_color="FFFF99", end_color="FFFF99", fill_type="solid")
_GREEN_FILL = PatternFill(start_color="CCFFCC", end_color="CCFFCC", fill_type="solid")
_HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
_LEGEND_HEADER_FILL = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")

_HEADER_FONT = Font(color="FFFFFF", bold=True)
_BOLD_FONT = Font(bold=True)


def _auto_width(ws) -> None:
    """Auto-fit column widths based on content."""
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value:
                length = len(str(cell.value))
                if length > max_len:
                    max_len = length
        # Cap at 60 chars width
        ws.column_dimensions[col_letter].width = min(max_len + 2, 60)


def export_clean_xls(segments: List[Segment], path: Path) -> None:
    """Export clean segments to XLSX with auto-width columns."""
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Clean Segments"

    headers = ["ID", "Source", "Target", "Source Lang", "Target Lang"]
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(wrap_text=False)

    for row_idx, seg in enumerate(segments, start=2):
        ws.cell(row=row_idx, column=1, value=seg.id)
        ws.cell(row=row_idx, column=2, value=seg.source)
        ws.cell(row=row_idx, column=3, value=seg.target)
        ws.cell(row=row_idx, column=4, value=seg.source_lang)
        ws.cell(row=row_idx, column=5, value=seg.target_lang)

    # Add legend sheet
    _add_legend_sheet(wb)
    _auto_width(ws)
    wb.save(str(path))


def export_qa_xls(
    segments: List[Segment],
    issues_map: Dict[str, List[QAIssue]],
    path: Path,
) -> None:
    """Export QA report to XLSX with color-coded rows."""
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "QA Report"

    headers = ["ID", "Source", "Target", "Source Lang", "Target Lang", "QA Issues", "Severity", "Issue Details"]
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT

    for row_idx, seg in enumerate(segments, start=2):
        seg_issues = issues_map.get(seg.id, [])

        # Determine row severity
        has_error = any(i.severity == "error" for i in seg_issues)
        has_warning = any(i.severity == "warning" for i in seg_issues)

        if has_error:
            row_fill = _RED_FILL
            severity_label = "error"
        elif has_warning:
            row_fill = _YELLOW_FILL
            severity_label = "warning"
        else:
            row_fill = _GREEN_FILL
            severity_label = "clean"

        issue_types = ", ".join(sorted(set(i.check for i in seg_issues))) if seg_issues else ""
        issue_details = "; ".join(i.message for i in seg_issues) if seg_issues else ""

        values = [
            seg.id, seg.source, seg.target, seg.source_lang, seg.target_lang,
            issue_types, severity_label, issue_details,
        ]
        for col_idx, val in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.fill = row_fill

    _add_legend_sheet(wb)
    _auto_width(ws)
    wb.save(str(path))


class CleanXlsWriter:
    """Context-manager streaming writer for clean-segments XLSX.

    Uses openpyxl write-only mode so each row is flushed to disk immediately —
    memory stays flat regardless of how many segments are written.

    Usage::

        with CleanXlsWriter(path) as w:
            for seg in segments:
                w.write(seg)
    """

    _HEADERS = ["ID", "Source", "Target", "Source Lang", "Target Lang"]
    _COL_WIDTHS = [15, 50, 50, 14, 14]

    def __init__(self, path: Path) -> None:
        self._path = path
        self._wb = None
        self._ws = None

    def __enter__(self) -> "CleanXlsWriter":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._wb = openpyxl.Workbook(write_only=True)
        self._ws = self._wb.create_sheet("Clean Segments")
        for i, w in enumerate(self._COL_WIDTHS, start=1):
            self._ws.column_dimensions[get_column_letter(i)].width = w
        header_cells = []
        for h in self._HEADERS:
            c = WriteOnlyCell(self._ws, value=h)
            c.fill = _HEADER_FILL
            c.font = _HEADER_FONT
            header_cells.append(c)
        self._ws.append(header_cells)
        return self

    def write(self, seg: Segment) -> None:
        self._ws.append([seg.id, seg.source, seg.target, seg.source_lang, seg.target_lang])

    def __exit__(self, *args) -> None:
        _add_legend_sheet_writeonly(self._wb)
        self._wb.save(str(self._path))
        return False


class QaXlsWriter:
    """Context-manager streaming writer for QA-report XLSX.

    Each segment+issues pair is written row-by-row with colour-coding, so
    memory stays flat no matter how many segments there are.

    Usage::

        with QaXlsWriter(path) as w:
            for seg, issues in seg_issue_pairs:
                w.write(seg, issues)
    """

    _HEADERS = ["ID", "Source", "Target", "Source Lang", "Target Lang",
                "QA Issues", "Severity", "Issue Details"]
    _COL_WIDTHS = [15, 40, 40, 14, 14, 22, 12, 55]

    def __init__(self, path: Path) -> None:
        self._path = path
        self._wb = None
        self._ws = None

    def __enter__(self) -> "QaXlsWriter":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._wb = openpyxl.Workbook(write_only=True)
        self._ws = self._wb.create_sheet("QA Report")
        for i, w in enumerate(self._COL_WIDTHS, start=1):
            self._ws.column_dimensions[get_column_letter(i)].width = w
        header_cells = []
        for h in self._HEADERS:
            c = WriteOnlyCell(self._ws, value=h)
            c.fill = _HEADER_FILL
            c.font = _HEADER_FONT
            header_cells.append(c)
        self._ws.append(header_cells)
        return self

    def write(self, seg: Segment, issues: List[QAIssue]) -> None:
        has_error = any(i.severity == "error" for i in issues)
        has_warning = any(i.severity == "warning" for i in issues)
        if has_error:
            row_fill = _RED_FILL
            severity_label = "error"
        elif has_warning:
            row_fill = _YELLOW_FILL
            severity_label = "warning"
        else:
            row_fill = _GREEN_FILL
            severity_label = "clean"

        issue_types = ", ".join(sorted({i.check for i in issues})) if issues else ""
        issue_details = "; ".join(i.message for i in issues) if issues else ""

        values = [seg.id, seg.source, seg.target, seg.source_lang, seg.target_lang,
                  issue_types, severity_label, issue_details]
        row_cells = []
        for v in values:
            c = WriteOnlyCell(self._ws, value=v)
            c.fill = row_fill
            row_cells.append(c)
        self._ws.append(row_cells)

    def __exit__(self, *args) -> None:
        _add_legend_sheet_writeonly(self._wb)
        self._wb.save(str(self._path))
        return False


def _add_legend_sheet_writeonly(wb: openpyxl.Workbook) -> None:
    """Add a colour-legend sheet to a *write-only* workbook."""
    ls = wb.create_sheet(title="Legend")

    hc = WriteOnlyCell(ls, value="Color Legend")
    hc.font = _BOLD_FONT
    hc.fill = _LEGEND_HEADER_FILL
    ls.append([hc])

    for fill, name, desc in [
        (_RED_FILL,    "Red",    "Segment has one or more ERROR-level QA issues"),
        (_YELLOW_FILL, "Yellow", "Segment has one or more WARNING-level QA issues"),
        (_GREEN_FILL,  "Green",  "Segment passed all QA checks"),
    ]:
        nc = WriteOnlyCell(ls, value=name)
        nc.fill = fill
        ls.append([nc, desc])

    ls.append([])

    tc = WriteOnlyCell(ls, value="QA Check Types")
    tc.font = _BOLD_FONT
    ls.append([tc])

    for check, desc in [
        ("tags",         "Inline tag count mismatch between source and target"),
        ("variables",    "Variable/placeholder mismatch"),
        ("numbers",      "Numeric value mismatch"),
        ("scripts",      "Unexpected character script for target language"),
        ("untranslated", "Target is empty or identical to source"),
        ("duplicate",    "Duplicate segment found"),
        ("mt_quality",   "MT quality score below threshold"),
    ]:
        ls.append([check, desc])


def _add_legend_sheet(wb: openpyxl.Workbook) -> None:
    """Add a legend sheet explaining color coding."""
    ls = wb.create_sheet(title="Legend")

    ls.cell(row=1, column=1, value="Color Legend").font = _BOLD_FONT
    ls.cell(row=1, column=1).fill = _LEGEND_HEADER_FILL

    legend_rows = [
        (_RED_FILL, "Red", "Segment has one or more ERROR-level QA issues"),
        (_YELLOW_FILL, "Yellow", "Segment has one or more WARNING-level QA issues"),
        (_GREEN_FILL, "Green", "Segment passed all QA checks"),
    ]
    for i, (fill, color_name, description) in enumerate(legend_rows, start=2):
        cell_color = ls.cell(row=i, column=1, value=color_name)
        cell_color.fill = fill
        ls.cell(row=i, column=2, value=description)

    ls.cell(row=6, column=1, value="QA Check Types").font = _BOLD_FONT
    check_types = [
        ("tags", "Inline tag count mismatch between source and target"),
        ("variables", "Variable/placeholder mismatch"),
        ("numbers", "Numeric value mismatch"),
        ("scripts", "Unexpected character script for target language"),
        ("untranslated", "Target is empty or identical to source"),
        ("duplicate", "Duplicate segment found"),
        ("mt_quality", "MT quality score below threshold"),
    ]
    for i, (check, desc) in enumerate(check_types, start=7):
        ls.cell(row=i, column=1, value=check)
        ls.cell(row=i, column=2, value=desc)

    ls.column_dimensions["A"].width = 18
    ls.column_dimensions["B"].width = 55
