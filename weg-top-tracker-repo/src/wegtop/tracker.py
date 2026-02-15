from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any, Iterable

from .export.excel_exporter import ExcelExporter

def build_tracker_rows(parsed_tops: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rec in parsed_tops:
        if rec.get("approved") is not True:
            continue
        rows.append({
            "meeting_date": rec.get("meeting_date"),
            "top_number": rec.get("top_number"),
            "top_title": rec.get("top_title"),
            "description": rec.get("description", rec.get("raw_excerpt", "")),
        })
    return rows

def export_excel(
    *,
    tracker_rows: List[Dict[str, Any]],
    all_tops_rows: List[Dict[str, Any]],
    qa_rows: List[Dict[str, Any]],
    out_path: Path,
) -> None:
    ExcelExporter().export(
        tracker_rows=tracker_rows,
        all_tops_rows=all_tops_rows,
        qa_rows=qa_rows,
        out_path=out_path,
    )

def export_by_year(
    *,
    all_tops_rows: List[Dict[str, Any]],
    qa_rows: List[Dict[str, Any]],
    out_path: Path,
) -> None:
    ExcelExporter().export_by_year(
        all_tops_rows=all_tops_rows,
        qa_rows=qa_rows,
        out_path=out_path,
    )
