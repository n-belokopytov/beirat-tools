import json
from pathlib import Path

import pytest

from wegtop.app import WEGTopApp
from wegtop.export.excel_exporter import ExcelExporter
from wegtop.models import IngestedPDF, PageText, ParsedTOP
from wegtop.tracker import build_tracker_rows, export_excel, export_by_year


class DummyPipeline:
    def __init__(self, *, ingested):
        self._ingested = ingested

    def ingest(self, pdf_path):
        return self._ingested


class DummyParser:
    def __init__(self, parsed):
        self._parsed = parsed

    def parse(self, corpus):
        return self._parsed


class DummyExporter:
    def __init__(self):
        self.calls = []

    def export(self, **kwargs):
        self.calls.append(("export", kwargs))

    def export_by_year(self, **kwargs):
        self.calls.append(("export_by_year", kwargs))


def test_build_tracker_rows_filters_unapproved():
    rows = [
        {"approved": True, "top_number": "1"},
        {"approved": False, "top_number": "2"},
        {"approved": None, "top_number": "3"},
    ]
    out = build_tracker_rows(rows)
    assert len(out) == 1
    assert out[0]["top_number"] == "1"


def test_excel_exporter_writes_files(tmp_path):
    exporter = ExcelExporter()
    out_path = tmp_path / "tracker.xlsx"
    by_year = tmp_path / "tracker_by_year.xlsx"

    tracker_rows = [{"meeting_date": "2024-01-01", "top_number": "1", "top_title": "Test"}]
    all_rows = [{
        "meeting_date": "2024-01-01",
        "top_number": "1",
        "top_title": "Test",
        "approved": True,
        "votes_yes": 1,
        "votes_no": 0,
        "votes_abstain": 0,
        "source_file": "a.pdf",
        "page_start": 1,
        "page_end": 1,
    }]
    qa_rows = [{"file": "a.pdf", "meeting_date": "2024-01-01"}]

    exporter.export(
        tracker_rows=tracker_rows,
        all_tops_rows=all_rows,
        qa_rows=qa_rows,
        out_path=out_path,
    )
    exporter.export_by_year(
        all_tops_rows=all_rows,
        qa_rows=qa_rows,
        out_path=by_year,
    )

    assert out_path.exists()
    assert by_year.exists()

    alt_out = tmp_path / "tracker_alt.xlsx"
    alt_by_year = tmp_path / "tracker_alt_by_year.xlsx"
    export_excel(
        tracker_rows=tracker_rows,
        all_tops_rows=all_rows,
        qa_rows=qa_rows,
        out_path=alt_out,
    )
    export_by_year(
        all_tops_rows=all_rows,
        qa_rows=qa_rows,
        out_path=alt_by_year,
    )

    assert alt_out.exists()
    assert alt_by_year.exists()

    import pandas as pd

    sheets = pd.ExcelFile(by_year).sheet_names
    assert "2024" in sheets
    assert "QA_Summary" in sheets


def test_app_process_pdfs_success(tmp_path):
    ingested = IngestedPDF(
        source_path="sample.pdf",
        pages=[PageText(0, "hello", 5)],
        used_layout=False,
        used_ocr=False,
        avg_chars_per_page=5.0,
    )
    parsed = [
        ParsedTOP(
            meeting_date="2024-01-01",
            source_file="sample.pdf",
            top_number="1",
            top_title="Test",
            title_issues=[],
            approved=True,
            explicit_decision=True,
            votes_yes=1,
            votes_no=0,
            votes_abstain=0,
            page_start=0,
            page_end=0,
            block_len=10,
            raw_excerpt="x",
        )
    ]
    exporter = DummyExporter()
    app = WEGTopApp(
        ingest_pipeline=DummyPipeline(ingested=ingested),
        parser=DummyParser(parsed),
        exporter=exporter,
    )

    out_dir = tmp_path / "out"
    app.process_pdfs([Path("sample.pdf")], out_dir)

    parsed_jsonl = out_dir / "parsed_tops_detail.jsonl"
    assert parsed_jsonl.exists()
    line = json.loads(parsed_jsonl.read_text(encoding="utf-8").splitlines()[0])
    assert line["top_number"] == "1"
    assert exporter.calls[0][0] == "export"
    assert exporter.calls[1][0] == "export_by_year"


def test_app_process_pdfs_records_errors(tmp_path):
    class FailingPipeline:
        def ingest(self, pdf_path):
            raise RuntimeError("bad pdf")

    exporter = DummyExporter()
    app = WEGTopApp(
        ingest_pipeline=FailingPipeline(),
        parser=DummyParser([]),
        exporter=exporter,
    )

    out_dir = tmp_path / "out"
    app.process_pdfs([Path("bad.pdf")], out_dir)

    errors = out_dir / "errors.jsonl"
    assert errors.exists()
    content = errors.read_text(encoding="utf-8")
    assert "bad pdf" in content

    with pytest.raises(SystemExit):
        app.process_pdfs([Path("bad.pdf")], out_dir, fail_fast=True)
