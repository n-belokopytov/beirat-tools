import re
from typing import Optional

NOISE_LINE_PATTERNS = [
    r"^DSZ_[A-Z].*$",
    r"^ALTMP_.*\.PDF$",
]

NOISE_RE = re.compile("|".join(f"(?:{p})" for p in NOISE_LINE_PATTERNS), flags=re.MULTILINE)

TITLE_NOISE_PATTERNS = [
    r"<<<page:\d+>>>",
    r"\bdsz_[a-z0-9_]+\b",
    r"\baltmp_[a-z0-9_]+\b",
    r"\bp\d{2,}\|\|",
    r"\bclwti\b",
    r"\bbmp\b",
]

TITLE_NOISE_RE = re.compile("|".join(f"(?:{p})" for p in TITLE_NOISE_PATTERNS), flags=re.IGNORECASE)

def normalize_text(text: str) -> str:
    """
    Normalize extracted PDF text:
    - normalize newlines
    - de-hyphenate line breaks
    - remove common transport markers
    - collapse whitespace
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # Ver-\nwalter -> Verwalter
    text = NOISE_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()

def clean_title_text(text: str) -> str:
    """
    Light cleanup for TOP titles: remove common OCR/scan artifacts.
    """
    if not text:
        return ""
    t = text.strip()
    t = TITLE_NOISE_RE.sub(" ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    t = re.sub(r"^[\W_]+", "", t)
    t = re.sub(r"[\W_]+$", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t

def safe_int(s: str) -> Optional[int]:
    try:
        return int(s.strip().replace(".", "").replace(" ", ""))
    except Exception:
        return None
