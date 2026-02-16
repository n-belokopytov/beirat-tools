from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from .app import WEGTopApp
from .export.excel_exporter import ExcelExporter
from .ingest.ocr_extractor import DEFAULT_OCR_DPI, OcrExtractor
from .ingest.pdfplumber_extractor import PdfPlumberExtractor
from .ingest.pipeline import IngestPipeline
from .parsing.regex_top_parser import RegexTopParser


def _run_parse(args: argparse.Namespace) -> None:
    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)

    pdfs = sorted(in_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found in: {in_dir}")

    primary = PdfPlumberExtractor(layout=False)
    layout_extractor = PdfPlumberExtractor(layout=True)
    ocr_extractor = (
        OcrExtractor(dpi=args.ocr_dpi, max_pages=args.max_ocr_pages) if args.ocr else None
    )
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


def _run_categorize(args: argparse.Namespace) -> None:
    try:
        from openai import OpenAI  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise SystemExit(
            "The 'openai' package is required for categorization. "
            "Install it with: pip install weg-top-tracker[llm]"
        ) from exc

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set the OPENAI_API_KEY environment variable before running categorize.")

    from .categorizer import categorize_excel  # pylint: disable=import-outside-toplevel

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / "categorized_TOPs.xlsx"

    client = OpenAI()
    categorize_excel(client, input_path, output_path, model=args.model, fail_fast=args.fail_fast)


def main() -> None:
    ap = argparse.ArgumentParser(prog="wegtop")
    sub = ap.add_subparsers(dest="command")

    parse_cmd = sub.add_parser("parse", help="Parse PDFs and generate tracker Excel files")
    parse_cmd.add_argument("--in_dir", required=True, help="Directory containing PDF files")
    parse_cmd.add_argument("--out_dir", default="out", help="Output directory")
    parse_cmd.add_argument(
        "--ocr", action="store_true", help="Enable OCR fallback for low-text PDFs (optional)"
    )
    parse_cmd.add_argument(
        "--min_avg_chars", type=int, default=250, help="OCR/layout trigger threshold"
    )
    parse_cmd.add_argument(
        "--ocr_dpi",
        type=int,
        default=DEFAULT_OCR_DPI,
        help="OCR render DPI (higher improves ß/ü recognition)",
    )
    parse_cmd.add_argument(
        "--max_ocr_pages", type=int, default=None, help="Limit OCR pages for large PDFs"
    )
    parse_cmd.add_argument("--fail_fast", action="store_true", help="Stop on first PDF error")

    cat_cmd = sub.add_parser("categorize", help="Categorize approved TOPs via LLM")
    cat_cmd.add_argument("--input", required=True, help="Path to the approved TOPs Excel file")
    cat_cmd.add_argument(
        "--output", default=None, help="Output Excel path (default: categorized_TOPs.xlsx)"
    )
    cat_cmd.add_argument(
        "--model", default="gpt-5.2", help="OpenAI model to use (default: gpt-5.2)"
    )
    cat_cmd.add_argument("--fail_fast", action="store_true", help="Stop on first LLM error")

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    args = ap.parse_args()

    if args.command == "parse":
        _run_parse(args)
    elif args.command == "categorize":
        _run_categorize(args)
    else:
        ap.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
