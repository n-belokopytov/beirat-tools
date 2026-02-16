# weg-top-tracker

Parse German WEG Eigentümerversammlung meeting minutes PDFs, extract **detail TOP** sections,
infer which TOPs were **approved**, and export an Excel tracker for monitoring execution by the Verwalter/Beirat.

Key hardening:
- Deduplicates agenda-list TOP entries vs detailed minutes (common in German Protokolle)
- Supports inline titles (`TOP 4 Beschlussfassung über ...`)
- OCR fallback for scanned minutes (optional)

## Install

Python 3.11+.

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e ".[ocr]"   # OCR fallback for scanned PDFs
pip install -e ".[llm]"   # LLM-based TOP categorization
```

System deps for OCR:
- poppler (pdftoppm)
- tesseract-ocr + German language data (deu)

## Run

Activate the virtual environment first, then run:

### Parse meeting minutes

```bash
source .venv/bin/activate
wegtop parse --in_dir ./inputs --out_dir ./out
```

To enable OCR fallback for scanned PDFs:

```bash
wegtop parse --in_dir ./inputs --out_dir ./out --ocr
```

OCR defaults to German-only Tesseract (`deu`) for reliable ß/ü/ä/ö recognition. Default render DPI is 200; use `--ocr_dpi 300` for best quality on poor scans. Common misreadings (ß→f, ü→ii) are corrected in post-processing where safe.

### Categorize approved TOPs

Classify each approved TOP by owner, cost, and complexity using an LLM, then calculate a multiplicative importance score (range 1–180):

```bash
export OPENAI_API_KEY="sk-..."
wegtop categorize --input out/approved_TOPs_tracker.xlsx
```

Output is written to `out/categorized_TOPs.xlsx` with a `Categorized_TOPs` sheet sorted by importance score descending. Options:

- `--output <path>` — custom output file path
- `--model <name>` — OpenAI model (default: `gpt-5.2`)
- `--fail_fast` — stop on first LLM error instead of skipping

## Architecture

The codebase is split into layered modules to keep concerns isolated and testable:

- `wegtop/ingest/`: Extractors and ingestion pipeline (pdfplumber/OCR strategies).
- `wegtop/parsing/`: TOP parsing logic (default regex-based parser).
- `wegtop/export/`: Output writers (Excel exports).
- `wegtop/categorizer.py`: LLM-based TOP categorization and scoring.
- `wegtop/app.py`: Application service wiring ingestion → parsing → export.
- `wegtop/models.py`: Shared dataclasses for domain entities.

## Dependency management

`pyproject.toml` is the source of truth. The `requirements*.txt` files are convenience wrappers that install the project and extras:

```bash
pip install -r requirements.txt
pip install -r requirements-ocr.txt
```
