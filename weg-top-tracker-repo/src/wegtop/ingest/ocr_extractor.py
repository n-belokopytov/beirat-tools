from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional

from ..models import PageText
from ..text_utils import normalize_text
from .base import TextExtractor

LOGGER = logging.getLogger(__name__)
DEFAULT_OCR_DPI = 200
_TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata/raw/main/{lang}.traineddata"
_checked_langs: set[str] = set()


def _find_tessdata_dir() -> Optional[Path]:
    """Locate the Tesseract tessdata directory."""
    prefix = os.environ.get("TESSDATA_PREFIX")
    if prefix:
        p = Path(prefix)
        if p.is_dir():
            return p
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stderr.splitlines():
            if "tessdata" in line and '"' in line:
                parts = line.split('"')
                if len(parts) >= 2:
                    p = Path(parts[1])
                    if p.is_dir():
                        return p
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _ensure_lang_data(lang: str) -> None:
    """Download Tesseract language data if not already present."""
    if lang in _checked_langs:
        return

    tessdata_dir = _find_tessdata_dir()
    if tessdata_dir is None:
        LOGGER.warning("Could not locate tessdata directory; skipping language download.")
        return

    traineddata = tessdata_dir / f"{lang}.traineddata"
    if traineddata.exists():
        _checked_langs.add(lang)
        return

    url = _TESSDATA_URL.format(lang=lang)
    LOGGER.info("Downloading Tesseract language data: %s -> %s", lang, traineddata)
    try:
        import urllib.request  # pylint: disable=import-outside-toplevel

        urllib.request.urlretrieve(url, str(traineddata))
        LOGGER.info("Successfully downloaded %s", traineddata.name)
        _checked_langs.add(lang)
    except Exception as exc:  # pylint: disable=broad-except
        traineddata.unlink(missing_ok=True)
        LOGGER.warning("Failed to download %s: %s", url, exc)


class OcrExtractor(TextExtractor):
    def __init__(
        self, *, dpi: int = DEFAULT_OCR_DPI, lang: str = "deu", max_pages: Optional[int] = None
    ) -> None:
        self._dpi = dpi
        self._lang = lang
        self._max_pages = max_pages

    def extract(self, pdf_path: Path) -> List[PageText]:
        # Optional dependencies kept local to allow running without OCR extras.
        from pdf2image import (
            convert_from_path,
            pdfinfo_from_path,
        )  # pylint: disable=import-outside-toplevel
        import pytesseract  # pylint: disable=import-outside-toplevel

        _ensure_lang_data(self._lang)

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
