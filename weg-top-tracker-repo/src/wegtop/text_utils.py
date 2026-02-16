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

# OCR with low DPI or English model interference misreads ß as f and ü as ii.
# We fix only whole-word matches to avoid corrupting valid text.
_GERMAN_OCR_FIXES = {
    # ü misread as ii
    "fiir": "für",
    "fiihren": "führen",
    "iiber": "über",
    "Miill": "Müll",
    "Tiir": "Tür",
    "Riicklage": "Rücklage",
    "Priifung": "Prüfung",
    "Gebiihr": "Gebühr",
    "Beschliisse": "Beschlüsse",
    "zuriick": "zurück",
    "Eigentiimer": "Eigentümer",
    "Schliisselversicherung": "Schlüsselversicherung",
    # ß misread as f
    "daf": "daß",
    "Maf": "Maß",
    "Schlof": "Schloß",
    "Fuf": "Fuß",
    "Grof": "Groß",
    "auferdem": "außerdem",
    "Befchluf": "Beschluß",
    "gemaf": "gemäß",
    "Straf": "Straß",
}

_GERMAN_OCR_FIX_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _GERMAN_OCR_FIXES) + r")\b",
    flags=re.IGNORECASE,
)


def _apply_german_ocr_fixes(text: str) -> str:
    """Replace known OCR misreadings (ß→f, ü→ii) using a single pre-compiled regex."""

    def _replace(m: re.Match) -> str:
        word = m.group()
        if word in _GERMAN_OCR_FIXES:
            return _GERMAN_OCR_FIXES[word]
        lower = word.lower()
        for wrong, right in _GERMAN_OCR_FIXES.items():
            if wrong.lower() == lower:
                if word.isupper():
                    return right.upper()
                if word[0].isupper():
                    return right[0].upper() + right[1:]
                return right.lower()
        return word

    return _GERMAN_OCR_FIX_RE.sub(_replace, text)


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
    text = _apply_german_ocr_fixes(text)
    # Strip table-border artifacts (|, [, ], (, )) that pdfplumber or OCR
    # produce from decorative lines in PDFs, and fix LTOP → TOP.
    text = re.sub(
        r"(?m)^[|\[\]() \t]*L?((?:T\s*O\s*P|TOP|Tagesordnungspunkt)(?=[\s\d]))",
        r"\1",
        text,
    )
    # Ensure space between TOP keyword and digit (extraction sometimes merges them)
    text = re.sub(r"(?m)^(T\s*O\s*P|TOP|Tagesordnungspunkt)(\d)", r"\1 \2", text)
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


def clean_description(text: str) -> str:
    """
    Strip voting metadata, page infrastructure, signatures, and decision
    announcements from a TOP description block, keeping only substantive content.
    """
    if not text:
        return ""

    # TOP header prefix ("TOP 4\n" or "TOP 17.1 ")
    text = re.sub(
        r"^\s*(?:T\s*O\s*P|TOP|Tagesordnungspunkt)\s+" r"\d+(?:[.,/]\s*\d+)?[a-z]?\s*",
        "",
        text,
        count=1,
    )

    # Page markers: <<<PAGE:N>>>
    text = re.sub(r"<<<PAGE:\d+>>>", "", text)

    # Page numbers
    text = re.sub(r"Seite\s+\d+\s+von\s+\d+", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"Seite\s+\d+\s+zum\s+Versammlungsprotokoll\s+vom\s+\d{2}\.\d{2}\.\d{4}",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Protocol page headers (3-line block repeated on each page)
    text = re.sub(
        r"Protokollabschrift\s*\n"
        r"der\s+\d+\.\s*\([^)]*\)\s*Eigent[üu]merversammlung\s+vom\s+"
        r"\d{2}\.\d{2}\.\d{4}\s*\n"
        r"WEG\b[^\n]*",
        "",
        text,
    )

    # Signature lines ("gez. Name1 gez. Name2 ...")
    text = re.sub(r"(?m)^gez\..*$", "", text)

    # Role identifier lines
    text = re.sub(
        r"(?m)^Verwaltungsbeirat(?:svorsitzender)?\s+"
        r"Versammlungsleiter(?:/in)?\s+Wohnungseigent[üu]mer\s*$",
        "",
        text,
    )

    # Vote eligibility metadata
    text = re.sub(r"(?m)^Stimmberechtigt\s+sind:.*$", "", text)
    text = re.sub(
        r"Seit\s+Beginn\s+der\s+Versammlung\s+haben\s+sich\s+die\s+Stimmrechte\s+"
        r"wie\s+folgt\s+ge[äa]ndert:\s*\n"
        r"Zugang:\s*[\d.,]+\s*Stimmen;\s*Abgang:\s*[\d.,]+\s*Stimmen\.",
        "",
        text,
    )
    text = re.sub(
        r"(?m)^Bei\s+Anwesenheit\s+von\s+[\d.,]+\s+Stimmrechten\s+wird\s+"
        r"[üu]ber\s+folgenden\s+Antrag\s+abgestimmt:?\s*$",
        "",
        text,
    )

    # Vote results (new format: "Für diesen Antrag stimmen X (Ja - Stimmen)")
    text = re.sub(
        r"(?m)^F[üu]r\s+diesen\s+Antrag\s+stimmen\s+[\d.,]+\s+" r"\(Ja\s*-?\s*Stimmen\)\s*$",
        "",
        text,
    )
    text = re.sub(
        r"(?m)^Gegen\s+diesen\s+Antrag\s+stimmen\s+[\d.,]+\s+" r"\(Nein\s*-?\s*Stimmen\)\s*$",
        "",
        text,
    )
    text = re.sub(
        r"(?m)^Der\s+Stimme\s+enthalten\s+sich\s+[\d.,]+\s+\(Enthaltungen\)\s*$",
        "",
        text,
    )

    # Vote results (old format: "X Ja-Stimmen X Nein-Stimmen X Enthaltungen")
    text = re.sub(r"(?m)^Abstimmungsergebnis:\s*$", "", text)
    text = re.sub(
        r"(?m)^[\d.,]+\s+Ja-Stimmen\s+[\d.,]+\s+Nein-Stimmen\s+" r"[\d.,]+\s+Enthaltungen\s*$",
        "",
        text,
    )

    # Decision announcements
    text = re.sub(
        r"(?m)^Damit\s+wird\s+der\s+Antrag\s+"
        r"(?:mehrheitlich\s+)?(?:nicht\s+)?angenommen\.?\s*$",
        "",
        text,
    )
    text = re.sub(
        r"(?m)^Der\s+Beschluss\s+wird\s+(?:nicht\s+)?angenommen\b.*$",
        "",
        text,
    )
    text = re.sub(
        r"(?m)^Der\s+Versammlungsleiter\s+verk[üu]ndet\s+" r"das\s+Beschlussergebnis\.?\s*$",
        "",
        text,
    )

    # Vote circle restrictions
    text = re.sub(
        r"(?m)^nur\s+f[üu]r\s+Eigent[üu]mer\s+des\s+Abrechnungskreises.*$",
        "",
        text,
    )

    # Collapse excess blank lines and trim
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
