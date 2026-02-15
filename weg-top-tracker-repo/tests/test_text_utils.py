from wegtop.text_utils import normalize_text, clean_title_text, safe_int, detect_title_orthography_issues


def test_normalize_text_repairs_hyphenation_and_umlauts():
    raw = "Ver-\nwalter A¨nderung"
    assert normalize_text(raw) == "Verwalter Änderung"


def test_normalize_text_fixes_german_ocr_ii_and_eszett():
    """OCR often misreads ü as ii and ß as f; we fix at word boundaries."""
    assert normalize_text("fiir die Eigentiimer") == "für die Eigentümer"
    assert normalize_text("Maf und Schlof") == "Maß und Schloß"
    assert normalize_text("FIIR") == "FÜR"  # case-insensitive
    assert normalize_text("Ministerium und Basis") == "Ministerium und Basis"  # unchanged


def test_clean_title_text_removes_noise_and_repeats():
    raw = "<<<PAGE:2>>> SEEEEEDEE Beschlussfassung"
    cleaned = clean_title_text(raw)
    assert cleaned == "Beschlussfassung"


def test_safe_int_parses_numeric_strings():
    assert safe_int("1.234") == 1234
    assert safe_int("  42 ") == 42
    assert safe_int("n/a") is None


def test_detect_title_orthography_issues():
    issues = detect_title_orthography_issues("WIRTSCHAAAFTSPLAN!!! 2025")
    assert "repeated_characters" in issues
    assert "repeated_punctuation" in issues
    assert "all_caps_long" in issues
