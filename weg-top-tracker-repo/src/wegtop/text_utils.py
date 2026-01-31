import re
import unicodedata
from typing import Optional, List

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
    - fix common umlaut OCR artifacts
    - remove common transport markers
    - collapse whitespace
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # Ver-\nwalter -> Verwalter
    text = text.replace("a¨", "ä").replace("o¨", "ö").replace("u¨", "ü")
    text = text.replace("A¨", "Ä").replace("O¨", "Ö").replace("U¨", "Ü")
    text = text.replace("¨a", "ä").replace("¨o", "ö").replace("¨u", "ü")
    text = text.replace("¨A", "Ä").replace("¨O", "Ö").replace("¨U", "Ü")
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
    # Drop tokens that are mostly repeated characters (e.g., "SEEEEEDEE")
    tokens = [tok for tok in re.split(r"\s+", t) if tok]
    cleaned_tokens: List[str] = []
    for tok in tokens:
        if len(tok) >= 6 and re.search(r"(.)\1{3,}", tok):
            continue
        cleaned_tokens.append(tok)
    t = " ".join(cleaned_tokens)
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

def detect_title_orthography_issues(text: str) -> List[str]:
    """
    Heuristic checks for OCR/copy-editing problems in short titles.
    Returns a list of issue codes (empty if clean/unknown).
    """
    if not text:
        return []
    t = text.strip()
    if not t:
        return []

    issues: List[str] = []

    if re.search(r"[!?.,]{3,}", t):
        issues.append("repeated_punctuation")
    if re.search(r"(.)\1{2,}", t):  # 3+ same char (e.g. WIRTSCHAAAFTSPLAN)
        issues.append("repeated_characters")

    tokens = re.split(r"\s+", t)
    for tok in tokens:
        if len(tok) >= 8 and tok.isupper():
            issues.append("all_caps_long")
            break

    vowels = set("aeiouyäöüAEIOUYÄÖÜ")
    for tok in tokens:
        if len(tok) >= 6 and tok.isalpha() and not any(ch in vowels for ch in tok):
            issues.append("no_vowel_token")
            break

    for tok in tokens:
        if len(tok) >= 6 and re.search(r"[A-Za-zÄÖÜäöüß]", tok) and re.search(r"\d", tok):
            issues.append("mixed_alnum_token")
            break

    return sorted(set(issues))
