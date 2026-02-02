from __future__ import annotations

from pathlib import Path
from typing import List

import pdfplumber

from ..models import PageText
from ..text_utils import normalize_text
from .base import TextExtractor


class PdfPlumberExtractor(TextExtractor):
    def __init__(self, *, layout: bool) -> None:
        self._layout = layout

    def extract(self, pdf_path: Path) -> List[PageText]:
        pages: List[PageText] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages):
                try:
                    raw = page.extract_text(layout=self._layout) or ""
                except TypeError:
                    raw = page.extract_text() or ""
                txt = normalize_text(raw)
                pages.append(PageText(i, txt, len(txt)))
        return pages
