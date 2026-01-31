from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any

from .pdf_ingest import ingest_pdf, save_corpus_json, ingested_to_corpus
from .top_parser import parse_tops_from_corpus, parsed_to_dicts
from .tracker import build_tracker_rows, export_excel, export_by_year

def main() -> None:
    ap = argparse.ArgumentParser(prog="wegtop")
    ap.add_argument("--in_dir", required=True, help="Directory containing PDF files")
    ap.add_argument("--out_dir", default="out", help="Output directory")
    ap.add_argument("--ocr", action="store_true", help="Enable OCR fallback for low-text PDFs (optional)")
    ap.add_argument("--min_avg_chars", type=int, default=250, help="OCR/layout trigger threshold")
    ap.add_argument("--ocr_dpi", type=int, default=140, help="OCR render DPI")
    ap.add_argument("--max_ocr_pages", type=int, default=None, help="Limit OCR pages for large PDFs")
    ap.add_argument("--fail_fast", action="store_true", help="Stop on first PDF error")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    corpus_dir = out_dir / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(in_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found in: {in_dir}")

    all_rows: List[Dict[str, Any]] = []
    qa_rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for pdf in pdfs:
        try:
            ing = ingest_pdf(
                pdf,
                min_avg_chars_per_page=args.min_avg_chars,
                enable_ocr=args.ocr,
                ocr_dpi=args.ocr_dpi,
                max_ocr_pages=args.max_ocr_pages,
            )
            corpus_path = corpus_dir / f"{pdf.stem}.json"
            save_corpus_json(ing, corpus_path)

            corpus = ingested_to_corpus(ing)
            parsed = parse_tops_from_corpus(corpus)
            parsed_dicts = parsed_to_dicts(parsed)
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
            if args.fail_fast:
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
    export_excel(
        tracker_rows=tracker_rows,
        all_tops_rows=all_rows,
        qa_rows=qa_rows,
        out_path=out_dir / "approved_TOPs_tracker.xlsx",
    )
    export_by_year(
        all_tops_rows=all_rows,
        qa_rows=qa_rows,
        out_path=out_dir / "approved_TOPs_tracker_by_year.xlsx",
    )

    print(f"Outputs written to: {out_dir}")

if __name__ == "__main__":
    main()
