"""PDF-to-Markdown conversion for TrackFlow RFP intake."""

from pathlib import Path

import pymupdf
import pymupdf4llm


def convert_pdf_to_markdown(pdf_path: str | Path) -> dict:
    """Extract PDF content and report basic readability metrics."""
    path = Path(pdf_path)

    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path.name}")

    if path.suffix.lower() != ".pdf":
        raise ValueError("Only PDF files are supported")

    with pymupdf.open(str(path)) as document:
        if document.page_count == 0:
            raise ValueError("PDF contains no pages")

        page_count = document.page_count
        pages_with_text = sum(
            bool(page.get_text("text").strip())
            for page in document
        )

    markdown = pymupdf4llm.to_markdown(str(path))
    if not isinstance(markdown, str):
        raise ValueError("PDF converter returned an invalid result")

    readable = bool(markdown.strip()) and pages_with_text > 0

    return {
        "markdown": markdown,
        "readability_metrics": {
            "page_count": page_count,
            "pages_with_text": pages_with_text,
            "pages_without_text": page_count - pages_with_text,
            "extracted_characters": len(markdown.strip()),
            "readable": readable,
        },
    }
