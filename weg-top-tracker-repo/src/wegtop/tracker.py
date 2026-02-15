from __future__ import annotations

from typing import Dict, List, Any, Iterable


def build_tracker_rows(parsed_tops: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rec in parsed_tops:
        if rec.get("approved") is not True:
            continue
        rows.append({
            "meeting_date": rec.get("meeting_date"),
            "top_number": rec.get("top_number"),
            "top_title": rec.get("top_title"),
            "description": rec.get("description", ""),
        })
    return rows
