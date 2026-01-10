from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from .text_utils import normalize_text, safe_int

TOP_HEADER_RE = re.compile(
    r"(?mi)^\s*(?:T\s*O\s*P|TOP|Tagesordnungspunkt|Tagesordnungs(?:punkt|p\.)?)\s+(\d+(?:\.\d+)?[a-z]?)\b"
)
PAGE_MARKER_RE = re.compile(r"<<<PAGE:(\d+)>>>")

GARBAGE_TITLE_TOKENS = [
    "gez.", "seite ", "dsz_", "versammlungsleiter", "wohnungseigentümer",
    "verwaltungsbeiratsvorsitzender", "p60||", "clwti", "bmp", "altmp",
    "<<<page", "protokollabschrift der",
]

def is_garbage_title(title: Optional[str]) -> bool:
    if not title:
        return True
    t = title.strip().lower()
    if not t:
        return True
    return any(tok in t for tok in GARBAGE_TITLE_TOKENS)

def join_pages_with_markers(pages: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for p in pages:
        parts.append(f"\n<<<PAGE:{p['page_index']}>>>\n")
        parts.append(p.get("text", "") or "")
    return normalize_text("\n".join(parts))

def _compute_markers(full_text: str) -> List[Tuple[int, int]]:
    return [(m.start(), int(m.group(1))) for m in PAGE_MARKER_RE.finditer(full_text)]

def _page_at(markers: List[Tuple[int, int]], pos: int) -> Optional[int]:
    pg: Optional[int] = None
    for s, p in markers:
        if s <= pos:
            pg = p
        else:
            break
    return pg

def split_top_blocks(full_text: str) -> List[Dict[str, Any]]:
    ms = list(TOP_HEADER_RE.finditer(full_text))
    markers = _compute_markers(full_text)
    blocks: List[Dict[str, Any]] = []
    for i, m in enumerate(ms):
        start = m.start()
        end = ms[i + 1].start() if i + 1 < len(ms) else len(full_text)
        block = full_text[start:end].strip()
        blocks.append({
            "top_number": m.group(1),
            "start": start,
            "end": end,
            "page_start": _page_at(markers, start),
            "page_end": _page_at(markers, end - 1),
            "len": len(block),
            "text": block,
        })
    return blocks

def header_inline_title(line: str) -> Optional[str]:
    m = re.match(
        r"(?i)^(?:T\s*O\s*P|TOP|Tagesordnungspunkt|Tagesordnungs(?:punkt|p\.)?)\s+\d+(?:\.\d+)?[a-z]?\s*(.*)$",
        line.strip(),
    )
    if not m:
        return None
    rest = m.group(1).strip()
    return rest if rest else None

def extract_title(block_text: str) -> Optional[str]:
    lines = [ln.strip() for ln in block_text.splitlines() if ln.strip()]
    if not lines:
        return None

    # Inline title: "TOP 4 Beschlussfassung über ..."
    t = header_inline_title(lines[0])
    if t and not is_garbage_title(t):
        return t[:240]

    # Drop pure header line
    if re.match(r"(?i)^(?:T\s*O\s*P|TOP|Tagesordnungspunkt)\s+\d", lines[0]):
        lines = lines[1:]
    if not lines:
        return None

    stop_markers = ("abstimmungsergebnis", "ergebnis", "bemerkung", "sachverhalt", "begründung", "stimmberechtigt")
    title_lines: List[str] = []
    for ln in lines[:12]:
        if ln.lower().startswith(stop_markers):
            break
        if is_garbage_title(ln):
            continue
        title_lines.append(ln)
        if len(" ".join(title_lines)) > 200:
            break
    title = " ".join(title_lines).strip()
    return title[:240] if title else None

def parse_votes_strict(block: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    # Labeled form
    m = re.search(
        r"(?is)(?:Ja(?:-Stimmen)?|Jastimmen)\s*[:=]?\s*([\d\.]+).*?"
        r"(?:Nein(?:-Stimmen)?|Neinstimmen)\s*[:=]?\s*([\d\.]+).*?"
        r"(?:Enthaltung(?:en)?|Enthaltungen?)\s*[:=]?\s*([\d\.]+)",
        block,
    )
    if m:
        return safe_int(m.group(1)), safe_int(m.group(2)), safe_int(m.group(3))

    # Unlabeled x / y / z ONLY if line hints vote context
    for ln in block.splitlines():
        if "/" in ln and re.search(r"(?i)\b(stimmen|ja|nein|enth)\b", ln):
            m2 = re.search(r"\b([\d\.]{1,10})\s*/\s*([\d\.]{1,10})\s*/\s*([\d\.]{1,10})\b", ln)
            if m2:
                return safe_int(m2.group(1)), safe_int(m2.group(2)), safe_int(m2.group(3))

    return None, None, None

def detect_explicit_decision(block: str) -> Optional[bool]:
    b = block.lower()
    if any(x in b for x in ["abgelehnt", "nicht angenommen", "nicht beschlossen", "kein beschluss", "zurückgestellt",
                            "vertagt", "ohne beschluss", "beschlussfassung entfällt"]):
        return False
    if any(x in b for x in ["wird angenommen", "angenommen", "beschließt", "wird beschlossen",
                            "mehrheitlich beschlossen", "beschluss gefasst"]):
        return True
    return None

def mentions_special_quorum(block: str) -> bool:
    b = block.lower()
    return any(k in b for k in ["einstimmigkeit", "quorum", "2/3", "zwei drittel", "3/4", "drei viertel", "qualifizierte mehrheit"])

def infer_approved(explicit: Optional[bool], yes: Optional[int], no: Optional[int], block: str) -> Optional[bool]:
    if explicit is not None:
        return explicit
    if mentions_special_quorum(block):
        return None
    if yes is not None and no is not None:
        return yes > no
    return None

def classify_block_kind(block_text: str, length: int) -> str:
    y, n, _ = parse_votes_strict(block_text)
    explicit = detect_explicit_decision(block_text)
    if (y is not None and n is not None) or explicit is not None or length >= 500 or ("verkündet das beschlussergebnis" in block_text.lower()):
        return "detail"
    return "agenda_or_header"

def extract_meeting_date(full_text: str, filename: str) -> Optional[str]:
    m = re.search(r"(?i)\b(?:vom|am)\s+(\d{1,2})\.(\d{1,2})\.(\d{4})\b", full_text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    m2 = re.search(r"\b([0-3]\d)(0[1-9]|1[0-2])(20\d{2})\b", filename)
    if m2:
        d, mo, y = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return None

def sort_key_top(x: str) -> Tuple[int, str]:
    m = re.match(r"(\d+)(.*)", str(x))
    return (int(m.group(1)), m.group(2))

@dataclass
class ParsedTOP:
    meeting_date: Optional[str]
    source_file: str
    top_number: str
    top_title: Optional[str]
    approved: Optional[bool]
    explicit_decision: Optional[bool]
    votes_yes: Optional[int]
    votes_no: Optional[int]
    votes_abstain: Optional[int]
    page_start: Optional[int]
    page_end: Optional[int]
    block_len: int
    raw_excerpt: str

def parse_tops_from_corpus(corpus: Dict[str, Any]) -> List[ParsedTOP]:
    pages = corpus["pages"]
    for p in pages:
        p["text"] = normalize_text(p.get("text", "") or "")

    full_text = join_pages_with_markers(pages)
    meeting_date = extract_meeting_date(full_text, Path(corpus["source_path"]).name)
    blocks = split_top_blocks(full_text)

    # Agenda title map (early list pages)
    agenda_titles: Dict[str, str] = {}
    for b in blocks:
        if classify_block_kind(b["text"], b["len"]) == "agenda_or_header":
            t = extract_title(b["text"])
            if t and not is_garbage_title(t):
                agenda_titles.setdefault(b["top_number"], t)

    # Deduplicate: keep the best *detail* block per TOP
    best: Dict[str, Dict[str, Any]] = {}
    for b in blocks:
        if classify_block_kind(b["text"], b["len"]) != "detail":
            continue
        y, n, _ = parse_votes_strict(b["text"])
        explicit = detect_explicit_decision(b["text"])
        score = (
            1 if (y is not None and n is not None) else 0,
            1 if explicit is not None else 0,
            b["len"],
        )
        if b["top_number"] not in best or score > best[b["top_number"]]["score"]:
            best[b["top_number"]] = {"score": score, **b}

    out: List[ParsedTOP] = []
    for top_no, b in best.items():
        text = b["text"]
        y, n, a = parse_votes_strict(text)
        explicit = detect_explicit_decision(text)
        approved = infer_approved(explicit, y, n, text)

        title = extract_title(text)
        if is_garbage_title(title):
            title = agenda_titles.get(top_no) or title
        if is_garbage_title(title):
            title = agenda_titles.get(top_no) or None

        out.append(ParsedTOP(
            meeting_date=meeting_date,
            source_file=Path(corpus["source_path"]).name,
            top_number=top_no,
            top_title=title,
            approved=approved,
            explicit_decision=explicit,
            votes_yes=y,
            votes_no=n,
            votes_abstain=a,
            page_start=b.get("page_start"),
            page_end=b.get("page_end"),
            block_len=int(b.get("len") or 0),
            raw_excerpt=text[:2000],
        ))

    out.sort(key=lambda r: (r.meeting_date or "9999-99-99", sort_key_top(r.top_number)))
    return out

def parsed_to_dicts(rows: List[ParsedTOP]) -> List[Dict[str, Any]]:
    return [asdict(r) for r in rows]
