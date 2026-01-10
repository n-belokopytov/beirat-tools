from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, List, Any, Iterable

import pandas as pd

GERMAN_STATUSES = [
    "Neu / offen",
    "In Prüfung",
    "Beauftragt",
    "In Umsetzung",
    "Wartet auf Verwalter",
    "Wartet auf Dienstleister",
    "Erledigt",
    "Blockiert",
]

def build_tracker_rows(parsed_tops: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rec in parsed_tops:
        if rec.get("approved") is not True:
            continue
        rows.append({
            "meeting_date": rec.get("meeting_date"),
            "top_number": rec.get("top_number"),
            "top_title": rec.get("top_title"),
            "votes_yes": rec.get("votes_yes"),
            "votes_no": rec.get("votes_no"),
            "votes_abstain": rec.get("votes_abstain"),
            "source_file": rec.get("source_file"),
            "page_start": rec.get("page_start"),
            "page_end": rec.get("page_end"),
            "owner": "Verwalter",
            "status": "Neu / offen",
            "last_beirat_action": "",
            "next_steps": "",
            "due_date": "",
            "risk_flag": "",
            "notes": "",
        })
    return rows

def export_excel(
    *,
    tracker_rows: List[Dict[str, Any]],
    all_tops_rows: List[Dict[str, Any]],
    qa_rows: List[Dict[str, Any]],
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_tracker = pd.DataFrame(tracker_rows)
    df_all = pd.DataFrame(all_tops_rows)
    df_qa = pd.DataFrame(qa_rows)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df_tracker.to_excel(writer, sheet_name="Approved_TOPs", index=False)
        df_qa.to_excel(writer, sheet_name="QA_Summary", index=False)
        df_all.to_excel(writer, sheet_name="All_TOPs_Detail", index=False)

def export_by_year(
    *,
    all_tops_rows: List[Dict[str, Any]],
    qa_rows: List[Dict[str, Any]],
    out_path: Path,
) -> None:
    def year_from_date(d):
        if not isinstance(d, str) or "-" not in d:
            return None
        try:
            return int(d.split("-")[0])
        except ValueError:
            return None

    def sort_key_top(x: str):
        m = re.match(r"(\d+)(.*)", str(x))
        return (int(m.group(1)), m.group(2))

    df_all = pd.DataFrame(all_tops_rows)
    df_qa = pd.DataFrame(qa_rows)

    df_all["year"] = df_all["meeting_date"].apply(year_from_date)
    years = sorted([int(y) for y in df_all["year"].dropna().unique()])

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for y in years:
            dfa = df_all[(df_all["year"] == y) & (df_all["approved"] == True)].copy()
            if not dfa.empty:
                dfa = dfa.sort_values(
                    ["meeting_date", "top_number"],
                    key=lambda s: s.map(sort_key_top),
                    na_position="last",
                )
            cols = [
                "meeting_date","top_number","top_title",
                "votes_yes","votes_no","votes_abstain",
                "source_file","page_start","page_end",
            ]
            dfa[cols].to_excel(writer, sheet_name=str(y), index=False)
        df_qa.to_excel(writer, sheet_name="QA_Summary", index=False)
