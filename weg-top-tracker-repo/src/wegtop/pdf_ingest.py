from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional

from .ingest.ocr_extractor import OcrExtractor
from .ingest.pdfplumber_extractor import PdfPlumberExtractor
from .ingest.pipeline import IngestPipeline
from .models import IngestedPDF, PageText

__all__ = [
    "PageText",
    "IngestedPDF",
    "ingest_pdf",
    "save_corpus_json",
    "ingested_to_corpus",
    "load_corpus_json",
]


def ingest_pdf(
    pdf_path: Path,
    *,
    min_avg_chars_per_page: int = 250,
    enable_ocr: bool = True,
    ocr_dpi: int = 140,
    max_ocr_pages: Optional[int] = None,
) -> IngestedPDF:
    """
    Backwards-compatible wrapper for the default ingest pipeline:
      1) pdfplumber (layout=False)
      2) if weak, retry pdfplumber (layout=True)
      3) if still weak and OCR enabled, OCR fallback
    """
    primary = PdfPlumberExtractor(layout=False)
    layout_extractor = PdfPlumberExtractor(layout=True)
    ocr_extractor = OcrExtractor(dpi=ocr_dpi, max_pages=max_ocr_pages) if enable_ocr else None

    pipeline = IngestPipeline(
        primary_extractor=primary,
        layout_extractor=layout_extractor,
        ocr_extractor=ocr_extractor,
        min_avg_chars_per_page=min_avg_chars_per_page,
    )
    return pipeline.ingest(pdf_path)


def save_corpus_json(ingested: IngestedPDF, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "source_path": ingested.source_path,
        "used_layout": ingested.used_layout,
        "used_ocr": ingested.used_ocr,
        "avg_chars_per_page": ingested.avg_chars_per_page,
        "pages": [{"page_index": p.page_index, "char_count": p.char_count, "text": p.text} for p in ingested.pages],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ingested_to_corpus(ingested: IngestedPDF) -> Dict[str, Any]:
    return {
        "source_path": ingested.source_path,
        "used_layout": ingested.used_layout,
        "used_ocr": ingested.used_ocr,
        "avg_chars_per_page": ingested.avg_chars_per_page,
        "pages": [{"page_index": p.page_index, "char_count": p.char_count, "text": p.text} for p in ingested.pages],
    }


def load_corpus_json(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Corpus JSON must be an object")
    for key in ("source_path", "pages"):
        if key not in data:
            raise ValueError(f"Corpus JSON missing required key: {key}")
    if not isinstance(data["pages"], list):
        raise ValueError("Corpus JSON 'pages' must be a list")
    for idx, page in enumerate(data["pages"]):
        if not isinstance(page, dict):
            raise ValueError(f"Corpus JSON page {idx} must be an object")
        if "page_index" not in page or "text" not in page:
            raise ValueError(f"Corpus JSON page {idx} missing required fields")
    return data
