from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from .text_utils import normalize_text, safe_int, clean_title_text, detect_title_orthography_issues

TOP_HEADER_RE = re.compile(
    r"(?mi)^\s*(?:(?:seite|s\.)\s*\d+[\s\).:-]+|\d+[\s\).:-]+)?"
    r"(?:T\s*O\s*P|TOP|Tagesordnungspunkt|Tagesordnungs(?:punkt|p\.)?)\s+"
    r"(\d+(?:(?:\s*[.,/]\s*|\s+)\d+)?[a-z]?)\b"
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

def normalize_top_number(raw: str) -> str:
    """
    Normalize common TOP number variants, especially OCR artifacts:
      - `17,1` / `17/1` -> `17.1`
      - `17 1` -> `17.1`
      - trim whitespace
    Note: run-together cases like `21` (meaning `2.1`) are handled by `repair_run_together_subtops`.
    """
    s = (raw or "").strip()
    if not s:
        return s

    # Keep optional letter suffix (e.g., "4a")
    m = re.match(r"^\s*(\d+)(.*)\s*$", s)
    if not m:
        return s
    lead, rest = m.group(1), m.group(2).strip()

    # Most common OCR forms for subpoints: comma, slash, dot, or a space.
    # Examples: "17,1", "17/1", "17 1", "17 . 1"
    m2 = re.match(r"^([.,/])\s*(\d+)([a-z]?)$", rest, flags=re.I)
    if m2:
        return f"{lead}.{m2.group(2)}{m2.group(3) or ''}".lower()

    m3 = re.match(r"^(\d+)([a-z]?)$", rest, flags=re.I)
    if m3:
        # "17 1" captured as "17" + rest "1"
        return f"{lead}.{m3.group(1)}{m3.group(2) or ''}".lower()

    # Already normal or weird; just normalize comma/slash to dot and remove spaces.
    s = re.sub(r"\s+", "", s)
    s = s.replace(",", ".").replace("/", ".")
    return s.lower()

def repair_run_together_subtops(blocks: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Heuristic to repair OCR "run-together" TOPs where a subpoint loses its separator:
      - `21` should be `2.1`
      - `62` should be `6.2`

    We only rewrite when it looks like an out-of-range jump compared to the other detected majors
    and the base TOP appears adjacent in the parsed sequence.
    Returns mapping old->new for items that should be rewritten.
    """
    top_numbers = [b.get("top_number") for b in blocks]
    majors: List[int] = []
    for t in top_numbers:
        m = re.match(r"^(\d+)", str(t))
        if m:
            majors.append(int(m.group(1)))
    majors_set = set(majors)
    have = set(top_numbers)
    rewrites: Dict[str, str] = {}

    for i, t in enumerate(top_numbers):
        if not re.fullmatch(r"\d{2,3}", str(t)):
            continue
        n = int(t)
        # Only consider suspiciously large majors (typical meetings rarely have 20+ TOPs)
        if n < 20:
            continue
        base = int(t[:-1])
        sub = t[-1]
        candidate = f"{base}.{sub}"
        if candidate in have:
            continue
        if base not in majors_set:
            continue
        # Only rewrite when the base TOP appears adjacent in the parsed sequence.
        base_nearby = False
        for j, t2 in enumerate(top_numbers):
            if j == i:
                continue
            m2 = re.match(r"^(\d+)", str(t2))
            if m2 and int(m2.group(1)) == base and abs(j - i) <= 1:
                base_nearby = True
                break
        if not base_nearby:
            continue
        # If this looks like a jump relative to the other majors, prefer the split form.
        other_majors = [m for m in majors_set if m != n]
        max_other = max(other_majors) if other_majors else None
        if max_other is not None and n >= max_other + 2:
            rewrites[t] = candidate

    return rewrites

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
            "top_number": normalize_top_number(m.group(1)),
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
        r"(?i)^\s*(?:(?:seite|s\.)\s*\d+[\s\).:-]+|\d+[\s\).:-]+)?"
        r"(?:T\s*O\s*P|TOP|Tagesordnungspunkt|Tagesordnungs(?:punkt|p\.)?)\s+"
        r"\d+(?:(?:\s*[.,/]\s*|\s+)\d+)?[a-z]?\s*(.*)$",
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
    if t:
        t = clean_title_text(t)
    if t and not is_garbage_title(t):
        return t[:240]

    # Drop pure header line
    if re.match(
        r"(?i)^\s*(?:(?:seite|s\.)\s*\d+[\s\).:-]+|\d+[\s\).:-]+)?"
        r"(?:T\s*O\s*P|TOP|Tagesordnungspunkt)\s+\d",
        lines[0],
    ):
        lines = lines[1:]
    if not lines:
        return None

    stop_markers = ("abstimmungsergebnis", "ergebnis", "bemerkung", "sachverhalt", "begründung", "stimmberechtigt")
    title_lines: List[str] = []
    for ln in lines[:12]:
        if ln.lower().startswith(stop_markers):
            break
        ln = clean_title_text(ln)
        if not ln:
            continue
        if is_garbage_title(ln):
            continue
        title_lines.append(ln)
        if len(" ".join(title_lines)) > 200:
            break
    title = clean_title_text(" ".join(title_lines).strip())
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
                            "vertagt", "ohne beschluss", "keine beschlussfassung", "keine beschluss", "beschlussfassung entfällt"]):
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

def parse_tops_from_corpus(corpus: Dict[str, Any]) -> List[ParsedTOP]:
    pages = corpus["pages"]
    for p in pages:
        p["text"] = normalize_text(p.get("text", "") or "")

    full_text = join_pages_with_markers(pages)
    meeting_date = extract_meeting_date(full_text, Path(corpus["source_path"]).name)
    blocks = split_top_blocks(full_text)
    # Repair run-together OCR numbers (e.g., "21" instead of "2.1") based on the set of detected TOPs.
    rewrites = repair_run_together_subtops(blocks)
    if rewrites:
        for b in blocks:
            b["top_number"] = rewrites.get(b["top_number"], b["top_number"])

    # Agenda title map (early list pages)
    agenda_titles: Dict[str, str] = {}
    for b in blocks:
        if classify_block_kind(b["text"], b["len"]) == "agenda_or_header":
            t = extract_title(b["text"])
            if t and not is_garbage_title(t):
                agenda_titles.setdefault(b["top_number"], t)

    # Deduplicate: keep the best block per TOP, strongly preferring "detail".
    best: Dict[str, Dict[str, Any]] = {}
    for b in blocks:
        kind = classify_block_kind(b["text"], b["len"])
        y, n, _ = parse_votes_strict(b["text"])
        explicit = detect_explicit_decision(b["text"])
        score = (
            1 if kind == "detail" else 0,
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

        title_issues = detect_title_orthography_issues(title or "")

        out.append(ParsedTOP(
            meeting_date=meeting_date,
            source_file=Path(corpus["source_path"]).name,
            top_number=top_no,
            top_title=title,
            title_issues=title_issues,
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
