from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional

import pdfplumber

from .text_utils import normalize_text

LOGGER = logging.getLogger(__name__)

@dataclass
class PageText:
    page_index: int
    text: str
    char_count: int

@dataclass
class IngestedPDF:
    source_path: str
    pages: List[PageText]
    used_layout: bool
    used_ocr: bool
    avg_chars_per_page: float

def _extract_pages_pdfplumber(pdf_path: Path, layout: bool) -> List[PageText]:
    pages: List[PageText] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                raw = page.extract_text(layout=layout) or ""
            except TypeError:
                raw = page.extract_text() or ""
            txt = normalize_text(raw)
            pages.append(PageText(i, txt, len(txt)))
    return pages

def _avg_chars(pages: List[PageText]) -> float:
    return (sum(p.char_count for p in pages) / len(pages)) if pages else 0.0

def _ocr_pages(
    pdf_path: Path,
    dpi: int = 140,
    lang: str = "deu+eng",
    max_pages: Optional[int] = None,
) -> List[PageText]:
    """
    OCR an entire PDF. Requires:
      - poppler (pdftoppm)
      - tesseract + language packs
      - pdf2image + pytesseract Python deps
    """
    # Optional dependencies kept local to allow running without OCR extras.
    from pdf2image import convert_from_path, pdfinfo_from_path  # pylint: disable=import-outside-toplevel
    import pytesseract  # pylint: disable=import-outside-toplevel

    info = pdfinfo_from_path(str(pdf_path))
    total_pages = int(info.get("Pages") or 0)
    if total_pages <= 0:
        return []
    if max_pages is not None:
        total_pages = min(total_pages, max_pages)

    pages: List[PageText] = []
    for page_num in range(1, total_pages + 1):
        images = convert_from_path(str(pdf_path), dpi=dpi, first_page=page_num, last_page=page_num)
        if not images:
            continue
        img = images[0]
        raw = pytesseract.image_to_string(img, lang=lang)
        txt = normalize_text(raw)
        pages.append(PageText(page_num - 1, txt, len(txt)))
    return pages

def ingest_pdf(
    pdf_path: Path,
    *,
    min_avg_chars_per_page: int = 250,
    enable_ocr: bool = True,
    ocr_dpi: int = 140,
    max_ocr_pages: Optional[int] = None,
) -> IngestedPDF:
    """
    Ingest PDF with:
      1) pdfplumber (layout=False)
      2) if weak, retry pdfplumber (layout=True)
      3) if still weak and OCR enabled, OCR fallback
    """
    pages = _extract_pages_pdfplumber(pdf_path, layout=False)
    a0 = _avg_chars(pages)
    used_layout = False
    used_ocr = False

    if a0 < min_avg_chars_per_page:
        pages_layout = _extract_pages_pdfplumber(pdf_path, layout=True)
        a1 = _avg_chars(pages_layout)
        if a1 > a0 * 1.2:
            pages = pages_layout
            used_layout = True

    if enable_ocr and _avg_chars(pages) < min_avg_chars_per_page:
        try:
            pages_ocr = _ocr_pages(pdf_path, dpi=ocr_dpi, max_pages=max_ocr_pages)
            a2 = _avg_chars(pages_ocr)
            if a2 > _avg_chars(pages) * 1.5 and a2 > 200:
                pages = pages_ocr
                used_ocr = True
        except Exception as exc:  # pylint: disable=broad-except
            # OCR optional; keep non-OCR extraction.
            LOGGER.warning(
                "OCR failed for %s (dpi=%s). Using non-OCR text. Error: %s",
                pdf_path,
                ocr_dpi,
                exc,
            )

    return IngestedPDF(
        source_path=str(pdf_path),
        pages=pages,
        used_layout=used_layout,
        used_ocr=used_ocr,
        avg_chars_per_page=_avg_chars(pages),
    )

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
