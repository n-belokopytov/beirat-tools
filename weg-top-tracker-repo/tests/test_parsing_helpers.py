import pytest

from wegtop import top_parser
from wegtop.parsing.regex_top_parser import (
    normalize_top_number,
    repair_run_together_subtops,
    parse_votes_strict,
    detect_explicit_decision,
    mentions_special_quorum,
    infer_approved,
    classify_block_kind,
    extract_meeting_date,
    extract_title,
    parse_tops_from_corpus,
    is_garbage_title,
    header_inline_title,
)


def test_normalize_top_number_variants():
    assert normalize_top_number("17,1") == "17.1"
    assert normalize_top_number("17/1") == "17.1"
    assert normalize_top_number("17 1") == "17.1"
    assert normalize_top_number("4a") == "4a"


def test_repair_run_together_subtops():
    blocks = [
        {"top_number": "2"},
        {"top_number": "21"},
        {"top_number": "3"},
    ]
    rewrites = repair_run_together_subtops(blocks)
    assert rewrites["21"] == "2.1"


def test_parse_votes_strict_labeled_and_unlabeled():
    block = "Ja-Stimmen: 10 Nein-Stimmen: 1 Enthaltungen: 2"
    assert parse_votes_strict(block) == (10, 1, 2)

    block2 = "Stimmen 5/2/1"
    assert parse_votes_strict(block2) == (5, 2, 1)

    assert parse_votes_strict("ohne stimmen") == (None, None, None)


def test_decision_inference_and_quorum():
    assert detect_explicit_decision("Beschluss wird beschlossen") is True
    assert detect_explicit_decision("Beschluss abgelehnt") is False
    assert detect_explicit_decision("ohne beschlussfassung") is False
    assert mentions_special_quorum("2/3 Mehrheit erforderlich") is True

    assert infer_approved(None, 5, 1, "text") is True
    assert infer_approved(None, 5, 1, "2/3 mehrheit") is None


def test_classify_block_kind():
    assert classify_block_kind("wird beschlossen", 10) == "detail"
    assert classify_block_kind("ohne beschluss", 10) == "detail"
    assert classify_block_kind("nur agenda", 10) == "agenda_or_header"
    assert classify_block_kind("kurz", 600) == "detail"


def test_extract_meeting_date_text_and_filename():
    text = "Protokoll vom 12.12.2024"
    assert extract_meeting_date(text, "foo.pdf") == "2024-12-12"
    assert extract_meeting_date("no date", "12022024.pdf") == "2024-02-12"


def test_extract_title_inline_and_multiline():
    inline = "TOP 4 Beschlussfassung über den Wirtschaftsplan\nJa-Stimmen: 10"
    assert extract_title(inline) == "Beschlussfassung über den Wirtschaftsplan"

    multi = "TOP 5\nBeschlussfassung über den Wirtschaftsplan\nAbstimmungsergebnis: ..."
    assert extract_title(multi) == "Beschlussfassung über den Wirtschaftsplan"

    assert header_inline_title("TOP 7 Testtitel") == "Testtitel"
    assert is_garbage_title("gez. unterschrift") is True


def test_parse_tops_from_corpus_end_to_end():
    corpus = {
        "source_path": "Protokoll Eigentümerversammlung vom 12.12.2024.pdf",
        "pages": [
            {
                "page_index": 0,
                "text": (
                    "TOP 1 Wirtschaftsplan\n"
                    "Ja-Stimmen: 10 Nein-Stimmen: 1 Enthaltungen: 0\n"
                    "wird beschlossen\n"
                ),
            }
        ],
    }
    parsed = parse_tops_from_corpus(corpus)
    assert len(parsed) == 1
    assert parsed[0].top_number == "1"
    assert parsed[0].approved is True

    parsed2 = top_parser.parse_tops_from_corpus(corpus)
    assert parsed2[0].top_number == "1"
