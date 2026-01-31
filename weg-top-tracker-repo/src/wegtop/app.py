from __future__ import annotations

import json
from dataclasses import asdict
import sys
from pathlib import Path
from typing import Dict, Any, List, Iterable

from .ingest.pipeline import IngestPipeline
from .parsing.regex_top_parser import RegexTopParser
from .tracker import build_tracker_rows
from .export.excel_exporter import ExcelExporter
from .pdf_ingest import save_corpus_json, ingested_to_corpus


class WEGTopApp:
    def __init__(
        self,
        *,
        ingest_pipeline: IngestPipeline,
        parser: RegexTopParser,
        exporter: ExcelExporter,
    ) -> None:
        self._pipeline = ingest_pipeline
        self._parser = parser
        self._exporter = exporter

    def process_pdfs(
        self,
        pdfs: Iterable[Path],
        out_dir: Path,
        *,
        fail_fast: bool = False,
    ) -> None:
        corpus_dir = out_dir / "corpus"
        corpus_dir.mkdir(parents=True, exist_ok=True)

        all_rows: List[Dict[str, Any]] = []
        qa_rows: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        for pdf in pdfs:
            try:
                ing = self._pipeline.ingest(pdf)
                corpus_path = corpus_dir / f"{pdf.stem}.json"
                save_corpus_json(ing, corpus_path)

                corpus = ingested_to_corpus(ing)
                parsed = self._parser.parse(corpus)
                parsed_dicts = [asdict(p) for p in parsed]
                all_rows.extend(parsed_dicts)

                qa_rows.append({
                    "file": pdf.name,
                    "meeting_date": parsed[0].meeting_date if parsed else None,
                    "tops_detail": len(parsed_dicts),
                    "approved": sum(1 for r in parsed_dicts if r.get("approved") is True),
                    "rejected": sum(1 for r in parsed_dicts if r.get("approved") is False),
                    "unknown": sum(1 for r in parsed_dicts if r.get("approved") is None),
                    "used_ocr": ing.used_ocr,
                    "used_layout": ing.used_layout,
                    "avg_chars_per_page": round(ing.avg_chars_per_page, 1),
                })

                print(
                    f"[OK] {pdf.name}: detail_TOPs={len(parsed_dicts)} "
                    f"approved={qa_rows[-1]['approved']} ocr={ing.used_ocr} avg_chars={ing.avg_chars_per_page:.1f}"
                )
            except Exception as exc:  # pylint: disable=broad-except
                errors.append({"file": pdf.name, "error": str(exc)})
                print(f"[ERROR] {pdf.name}: {exc}", file=sys.stderr)
                if fail_fast:
                    raise SystemExit(1) from exc

        parsed_jsonl = out_dir / "parsed_tops_detail.jsonl"
        parsed_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with parsed_jsonl.open("w", encoding="utf-8") as f:
            for rec in all_rows:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        if errors:
            errors_path = out_dir / "errors.jsonl"
            with errors_path.open("w", encoding="utf-8") as f:
                for err in errors:
                    f.write(json.dumps(err, ensure_ascii=False) + "\n")
            print(f"[WARN] {len(errors)} file(s) failed. See: {errors_path}", file=sys.stderr)

        tracker_rows = build_tracker_rows(all_rows)
        self._exporter.export(
            tracker_rows=tracker_rows,
            all_tops_rows=all_rows,
            qa_rows=qa_rows,
            out_path=out_dir / "approved_TOPs_tracker.xlsx",
        )
        self._exporter.export_by_year(
            all_tops_rows=all_rows,
            qa_rows=qa_rows,
            out_path=out_dir / "approved_TOPs_tracker_by_year.xlsx",
        )
