from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from ..models import IngestedPDF, PageText
from .base import TextExtractor

LOGGER = logging.getLogger(__name__)


def _avg_chars(pages: List[PageText]) -> float:
    return (sum(p.char_count for p in pages) / len(pages)) if pages else 0.0


class IngestPipeline:
    def __init__(
        self,
        *,
        primary_extractor: TextExtractor,
        layout_extractor: Optional[TextExtractor] = None,
        ocr_extractor: Optional[TextExtractor] = None,
        min_avg_chars_per_page: int = 250,
        layout_gain_ratio: float = 1.2,
        ocr_gain_ratio: float = 1.5,
        ocr_min_chars: int = 200,
    ) -> None:
        self._primary = primary_extractor
        self._layout = layout_extractor
        self._ocr = ocr_extractor
        self._min_avg = min_avg_chars_per_page
        self._layout_gain = layout_gain_ratio
        self._ocr_gain = ocr_gain_ratio
        self._ocr_min = ocr_min_chars

    def ingest(self, pdf_path: Path) -> IngestedPDF:
        pages = self._primary.extract(pdf_path)
        a0 = _avg_chars(pages)
        used_layout = False
        used_ocr = False

        if self._layout is not None and a0 < self._min_avg:
            pages_layout = self._layout.extract(pdf_path)
            a1 = _avg_chars(pages_layout)
            if a1 > a0 * self._layout_gain:
                pages = pages_layout
                used_layout = True

        if self._ocr is not None and _avg_chars(pages) < self._min_avg:
            try:
                pages_ocr = self._ocr.extract(pdf_path)
                a2 = _avg_chars(pages_ocr)
                if a2 > _avg_chars(pages) * self._ocr_gain and a2 > self._ocr_min:
                    pages = pages_ocr
                    used_ocr = True
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.warning(
                    "OCR failed for %s. Using non-OCR text. Error: %s",
                    pdf_path,
                    exc,
                )

        return IngestedPDF(
            source_path=str(pdf_path),
            pages=pages,
            used_layout=used_layout,
            used_ocr=used_ocr,
            avg_chars_per_page=_avg_chars(pages),
        )
