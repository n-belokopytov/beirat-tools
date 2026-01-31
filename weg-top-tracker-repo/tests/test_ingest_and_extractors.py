from pathlib import Path
import types
import sys

import pytest

from wegtop.ingest.pipeline import IngestPipeline
from wegtop.ingest.pdfplumber_extractor import PdfPlumberExtractor
from wegtop.ingest.ocr_extractor import OcrExtractor
from wegtop.models import PageText, IngestedPDF
from wegtop.pdf_ingest import load_corpus_json, save_corpus_json, ingested_to_corpus


class DummyExtractor:
    def __init__(self, pages):
        self._pages = pages
        self.calls = 0

    def extract(self, pdf_path):
        self.calls += 1
        return self._pages


class RaisingExtractor:
    def extract(self, pdf_path):
        raise RuntimeError("boom")


def _pages(char_counts):
    return [PageText(i, "x" * n, n) for i, n in enumerate(char_counts)]


def test_ingest_pipeline_prefers_layout_when_better():
    primary = DummyExtractor(_pages([50, 50]))
    layout = DummyExtractor(_pages([120, 120]))
    pipeline = IngestPipeline(
        primary_extractor=primary,
        layout_extractor=layout,
        ocr_extractor=None,
        min_avg_chars_per_page=60,
    )

    out = pipeline.ingest(Path("dummy.pdf"))
    assert out.used_layout is True
    assert out.used_ocr is False
    assert out.avg_chars_per_page == 120


def test_ingest_pipeline_uses_ocr_when_it_improves():
    primary = DummyExtractor(_pages([50]))
    ocr = DummyExtractor(_pages([200]))
    pipeline = IngestPipeline(
        primary_extractor=primary,
        layout_extractor=None,
        ocr_extractor=ocr,
        min_avg_chars_per_page=60,
        ocr_gain_ratio=1.2,
        ocr_min_chars=100,
    )

    out = pipeline.ingest(Path("dummy.pdf"))
    assert out.used_ocr is True
    assert out.avg_chars_per_page == 200


def test_ingest_pipeline_ignores_ocr_errors():
    primary = DummyExtractor(_pages([80]))
    pipeline = IngestPipeline(
        primary_extractor=primary,
        layout_extractor=None,
        ocr_extractor=RaisingExtractor(),
        min_avg_chars_per_page=60,
    )

    out = pipeline.ingest(Path("dummy.pdf"))
    assert out.used_ocr is False
    assert out.avg_chars_per_page == 80


def test_pdfplumber_extractor_handles_layout_typeerror(monkeypatch):
    import pdfplumber

    class FakePage:
        def __init__(self, text, raise_type_error=False):
            self._text = text
            self._raise_type_error = raise_type_error

        def extract_text(self, layout=None):
            if self._raise_type_error and layout is not None:
                raise TypeError("layout not supported")
            return self._text

    class FakePDF:
        def __init__(self, pages):
            self.pages = pages

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(_):
        return FakePDF([FakePage("A-\nB", raise_type_error=True), FakePage("C")])

    monkeypatch.setattr(pdfplumber, "open", fake_open)
    extractor = PdfPlumberExtractor(layout=True)
    pages = extractor.extract(Path("dummy.pdf"))

    assert pages[0].text == "AB"
    assert pages[0].char_count == 2
    assert pages[1].text == "C"


def test_ocr_extractor_limits_pages(monkeypatch):
    def pdfinfo_from_path(_):
        return {"Pages": 2}

    def convert_from_path(_, dpi, first_page, last_page):
        return [f"img{first_page}"]

    pdf2image = types.SimpleNamespace(
        convert_from_path=convert_from_path,
        pdfinfo_from_path=pdfinfo_from_path,
    )
    pytesseract = types.SimpleNamespace(
        image_to_string=lambda img, lang: f"text-{img}",
    )

    monkeypatch.setitem(sys.modules, "pdf2image", pdf2image)
    monkeypatch.setitem(sys.modules, "pytesseract", pytesseract)

    extractor = OcrExtractor(dpi=100, lang="deu", max_pages=1)
    pages = extractor.extract(Path("dummy.pdf"))

    assert len(pages) == 1
    assert pages[0].text == "text-img1"


def test_corpus_roundtrip(tmp_path):
    ingested = IngestedPDF(
        source_path="sample.pdf",
        pages=[PageText(0, "hello", 5)],
        used_layout=False,
        used_ocr=False,
        avg_chars_per_page=5.0,
    )
    out_path = tmp_path / "corpus.json"
    save_corpus_json(ingested, out_path)

    data = load_corpus_json(out_path)
    assert data["source_path"] == "sample.pdf"
    assert data["pages"][0]["text"] == "hello"
    assert ingested_to_corpus(ingested)["pages"][0]["char_count"] == 5


def test_load_corpus_json_validation(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_corpus_json(bad)
