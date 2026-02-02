from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


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


@dataclass
class ParsedTOP:
    meeting_date: Optional[str]
    source_file: str
    top_number: str
    top_title: Optional[str]
    title_issues: List[str]
    approved: Optional[bool]
    explicit_decision: Optional[bool]
    votes_yes: Optional[int]
    votes_no: Optional[int]
    votes_abstain: Optional[int]
    page_start: Optional[int]
    page_end: Optional[int]
    block_len: int
    raw_excerpt: str
