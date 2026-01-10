import re
from typing import Optional

NOISE_LINE_PATTERNS = [
    r"^DSZ_[A-Z].*$",
    r"^ALTMP_.*\.PDF$",
]

NOISE_RE = re.compile("|".join(f"(?:{p})" for p in NOISE_LINE_PATTERNS), flags=re.MULTILINE)

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

def safe_int(s: str) -> Optional[int]:
    try:
        return int(s.strip().replace(".", "").replace(" ", ""))
    except Exception:
        return None
