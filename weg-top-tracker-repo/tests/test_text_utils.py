from wegtop.text_utils import normalize_text, clean_title_text, clean_description, safe_int, detect_title_orthography_issues


def test_normalize_text_repairs_hyphenation_and_umlauts():
    raw = "Ver-\nwalter A¨nderung"
    assert normalize_text(raw) == "Verwalter Änderung"


def test_normalize_text_fixes_german_ocr_ii_and_eszett():
    """OCR often misreads ü as ii and ß as f; we fix at word boundaries."""
    assert normalize_text("fiir die Eigentiimer") == "für die Eigentümer"
    assert normalize_text("Maf und Schlof") == "Maß und Schloß"
    assert normalize_text("FIIR") == "FÜR"  # case-insensitive
    assert normalize_text("Ministerium und Basis") == "Ministerium und Basis"  # unchanged


def test_normalize_text_strips_ocr_table_borders_from_top_headers():
    """pdfplumber/OCR reads table borders as |, [, ], (, ) before TOP headers."""
    assert "TOP 1.2 Feststellung" in normalize_text("| TOP 1.2 Feststellung")
    assert "TOP 1.5 Beschluss" in normalize_text("|LTOP 1.5 Beschluss")
    assert "TOP 1 Förmlichkeiten" in normalize_text("[TOP 1 Förmlichkeiten )")
    # Run-together TOP+digit gets a space inserted
    assert "TOP 2 Bericht" in normalize_text("|TOP2 Bericht")
    # Normal TOP lines are unchanged
    assert "TOP 4 Wirtschaftsplan" in normalize_text("TOP 4 Wirtschaftsplan")


def test_clean_title_text_removes_noise_and_repeats():
    raw = "<<<PAGE:2>>> SEEEEEDEE Beschlussfassung"
    cleaned = clean_title_text(raw)
    assert cleaned == "Beschlussfassung"


def test_safe_int_parses_numeric_strings():
    assert safe_int("1.234") == 1234
    assert safe_int("  42 ") == 42
    assert safe_int("n/a") is None


def test_clean_description_strips_metadata():
    """clean_description removes voting metadata, page noise, signatures, decisions."""
    raw = (
        "TOP 4\n"
        "Beschlussfassung über den Wirtschaftsplan\n"
        "Stimmberechtigt sind: Alle Eigentümer\n"
        "Seit Beginn der Versammlung haben sich die Stimmrechte wie folgt geändert:\n"
        "Zugang: 77 Stimmen; Abgang: 0 Stimmen.\n"
        "Bei Anwesenheit von 6.007 Stimmrechten wird über folgenden Antrag abgestimmt:\n"
        "Beschluss:\n"
        "Die Eigentümer beschließen den Wirtschaftsplan.\n"
        "Für diesen Antrag stimmen 5.403 (Ja - Stimmen)\n"
        "Gegen diesen Antrag stimmen 541 (Nein - Stimmen)\n"
        "Der Stimme enthalten sich 63 (Enthaltungen)\n"
        "Damit wird der Antrag mehrheitlich angenommen.\n"
        "Der Versammlungsleiter verkündet das Beschlussergebnis.\n"
        "gez. Klaus Pfleiderer gez. Alexandra Mersinger gez. Harry Steiert\n"
        "Verwaltungsbeiratsvorsitzender Versammlungsleiter Wohnungseigentümer\n"
        "Seite 8 von 28\n"
        "\n"
        "<<<PAGE:10>>>\n"
        "\n"
        "Protokollabschrift\n"
        'der 1. (außerordentlichen) Eigentümerversammlung vom 11.07.2023\n'
        'WEG "The Wave" Stralauer Allee 13,14, 10245 Berlin\n'
    )
    result = clean_description(raw)
    assert "Beschlussfassung über den Wirtschaftsplan" in result
    assert "Beschluss:" in result
    assert "Die Eigentümer beschließen den Wirtschaftsplan." in result
    # All metadata must be gone
    assert "TOP 4" not in result
    assert "Stimmberechtigt" not in result
    assert "Zugang:" not in result
    assert "Bei Anwesenheit" not in result
    assert "Ja - Stimmen" not in result
    assert "Nein - Stimmen" not in result
    assert "Enthaltungen" not in result
    assert "angenommen" not in result
    assert "verkündet" not in result
    assert "gez." not in result
    assert "Verwaltungsbeiratsvorsitzender" not in result
    assert "Seite 8 von 28" not in result
    assert "<<<PAGE" not in result
    assert "Protokollabschrift" not in result
    assert "WEG" not in result


def test_clean_description_old_vote_format():
    """Handles the 2021/2022 unlabeled vote format."""
    raw = (
        "TOP 16 Beschlussfassung über Versicherungsschutz\n"
        "\n"
        "Beschlussfassung:\n"
        "Die Eigentümergemeinschaft beschließt die Erweiterung.\n"
        "\n"
        "<<<PAGE:9>>>\n"
        "\n"
        "Seite 10 zum Versammlungsprotokoll vom 21.12.2022\n"
        "\n"
        "Abstimmungsergebnis:\n"
        "\n"
        "3.238,66 Ja-Stimmen 1.289,66 Nein-Stimmen 152,82 Enthaltungen\n"
        "\n"
        "Der Beschluss wird angenommen und verkündet.\n"
    )
    result = clean_description(raw)
    assert "Beschlussfassung über Versicherungsschutz" in result
    assert "Die Eigentümergemeinschaft beschließt die Erweiterung." in result
    assert "Abstimmungsergebnis" not in result
    assert "Ja-Stimmen" not in result
    assert "angenommen" not in result
    assert "<<<PAGE" not in result
    assert "Versammlungsprotokoll" not in result


def test_clean_description_vote_circle_restriction():
    """Strips 'nur für Eigentümer des Abrechnungskreises' lines."""
    raw = (
        "TOP 17 Wallbox\n"
        "Inhalt des Antrags.\n"
        "nur für Eigentümer des Abrechnungskreises 804 - Stralauer 14 TG\n"
    )
    result = clean_description(raw)
    assert "Inhalt des Antrags." in result
    assert "Abrechnungskreises" not in result


def test_clean_description_preserves_content_sections():
    """Erläuterungen, Beschluss, and Bemerkung sections stay intact."""
    raw = (
        "TOP 5\n"
        "Beschlussfassung über den Wechsel\n"
        "Erläuterungen:\n"
        "Der bestehende Vertrag wurde gekündigt.\n"
        "Bemerkung:\n"
        "Seitens der Eigentümer wird gewünscht, weitere Angebote einzuholen.\n"
    )
    result = clean_description(raw)
    assert "Erläuterungen:" in result
    assert "Der bestehende Vertrag wurde gekündigt." in result
    assert "Bemerkung:" in result
    assert "weitere Angebote einzuholen." in result


def test_clean_description_empty_and_minimal():
    """Edge cases: empty string and minimal content."""
    assert clean_description("") == ""
    assert clean_description("TOP 1 Förmlichkeiten [") == "Förmlichkeiten ["


def test_detect_title_orthography_issues():
    issues = detect_title_orthography_issues("WIRTSCHAAAFTSPLAN!!! 2025")
    assert "repeated_characters" in issues
    assert "repeated_punctuation" in issues
    assert "all_caps_long" in issues
