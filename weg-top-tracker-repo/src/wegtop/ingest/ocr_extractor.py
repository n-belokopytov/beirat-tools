from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..models import PageText
from ..text_utils import normalize_text
from .base import TextExtractor


class OcrExtractor(TextExtractor):
    def __init__(self, *, dpi: int = 140, lang: str = "deu+eng", max_pages: Optional[int] = None) -> None:
        self._dpi = dpi
        self._lang = lang
        self._max_pages = max_pages

    def extract(self, pdf_path: Path) -> List[PageText]:
        # Optional dependencies kept local to allow running without OCR extras.
        from pdf2image import convert_from_path, pdfinfo_from_path  # pylint: disable=import-outside-toplevel
        import pytesseract  # pylint: disable=import-outside-toplevel

        info = pdfinfo_from_path(str(pdf_path))
        total_pages = int(info.get("Pages") or 0)
        if total_pages <= 0:
            return []
        if self._max_pages is not None:
            total_pages = min(total_pages, self._max_pages)

        pages: List[PageText] = []
        for page_num in range(1, total_pages + 1):
            images = convert_from_path(
                str(pdf_path),
                dpi=self._dpi,
                first_page=page_num,
                last_page=page_num,
            )
            if not images:
                continue
            img = images[0]
            raw = pytesseract.image_to_string(img, lang=self._lang)
            txt = normalize_text(raw)
            pages.append(PageText(page_num - 1, txt, len(txt)))
        return pages
