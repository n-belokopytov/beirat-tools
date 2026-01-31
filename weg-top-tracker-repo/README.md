# weg-top-tracker

Parse German WEG Eigentümerversammlung meeting minutes PDFs, extract **detail TOP** sections,
infer which TOPs were **approved**, and export an Excel tracker for monitoring execution by the Verwalter/Beirat.

Key hardening:
- Deduplicates agenda-list TOP entries vs detailed minutes (common in German Protokolle)
- Supports inline titles (`TOP 4 Beschlussfassung über ...`)
- OCR fallback for scanned minutes (optional)

## Install

Python 3.10+.

```bash
pip install -e .
```

Optional OCR (for scanned PDFs like older minutes):

```bash
pip install -e ".[ocr]"
```

System deps for OCR:
- poppler (pdftoppm)
- tesseract-ocr + German language data (deu)

## Run

```bash
wegtop --in_dir ./pdfs --out_dir ./out --ocr
```

## Architecture

The codebase is split into layered modules to keep concerns isolated and testable:

- `wegtop/ingest/`: Extractors and ingestion pipeline (pdfplumber/OCR strategies).
- `wegtop/parsing/`: TOP parsing logic (default regex-based parser).
- `wegtop/export/`: Output writers (Excel exports).
- `wegtop/app.py`: Application service wiring ingestion → parsing → export.
- `wegtop/models.py`: Shared dataclasses for domain entities.

Legacy entrypoints (`wegtop/pdf_ingest.py`, `wegtop/top_parser.py`, `wegtop/tracker.py`) remain as thin wrappers to preserve existing imports.

## Dependency management

`pyproject.toml` is the source of truth. The `requirements*.txt` files are convenience wrappers that install the project and extras:

```bash
pip install -r requirements.txt
pip install -r requirements-ocr.txt
```
