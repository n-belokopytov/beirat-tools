from __future__ import annotations

from pathlib import Path
from typing import List, Protocol

from ..models import PageText


class TextExtractor(Protocol):
    def extract(self, pdf_path: Path) -> List[PageText]:
        ...
