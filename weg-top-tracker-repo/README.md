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
