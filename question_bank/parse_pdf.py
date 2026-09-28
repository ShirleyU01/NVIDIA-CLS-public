from __future__ import annotations

from pathlib import Path

from question_bank.schemas import ParsedDocument, ParsedPage


def extract_pdf_pages(pdf_path: Path) -> list[ParsedPage]:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise ImportError(
            "PyMuPDF is required for PDF ingest. Install: pip install pymupdf"
        ) from e

    doc = fitz.open(pdf_path)
    pages: list[ParsedPage] = []
    try:
        for i in range(len(doc)):
            page = doc.load_page(i)
            text = page.get_text("text") or ""
            pages.append(ParsedPage(page_index=i, text=text.strip()))
    finally:
        doc.close()
    return pages


def title_guess_from_path(pdf_path: Path) -> str:
    return pdf_path.stem.replace("_", " ").strip() or pdf_path.name
