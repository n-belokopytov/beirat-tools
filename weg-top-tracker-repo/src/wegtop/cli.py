from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .app import WEGTopApp
from .export.excel_exporter import ExcelExporter
from .ingest.ocr_extractor import OcrExtractor
from .ingest.pdfplumber_extractor import PdfPlumberExtractor
from .ingest.pipeline import IngestPipeline
from .parsing.regex_top_parser import RegexTopParser

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

    pdfs = sorted(in_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found in: {in_dir}")

    primary = PdfPlumberExtractor(layout=False)
    layout_extractor = PdfPlumberExtractor(layout=True)
    ocr_extractor = OcrExtractor(dpi=args.ocr_dpi, max_pages=args.max_ocr_pages) if args.ocr else None
    pipeline = IngestPipeline(
        primary_extractor=primary,
        layout_extractor=layout_extractor,
        ocr_extractor=ocr_extractor,
        min_avg_chars_per_page=args.min_avg_chars,
    )
    app = WEGTopApp(
        ingest_pipeline=pipeline,
        parser=RegexTopParser(),
        exporter=ExcelExporter(),
    )

    app.process_pdfs(pdfs, out_dir, fail_fast=args.fail_fast)

    print(f"Outputs written to: {out_dir}")

if __name__ == "__main__":
    main()
