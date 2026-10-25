"""Asynchronous PDF conversion for RFP intake."""

from pathlib import Path
import sys

from celery_app import celery_app

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from data.pipelines.rfp_intake.pdf_converter import convert_pdf_to_markdown


@celery_app.task(name="tasks.rfp_intake.convert_rfp_pdf")
def convert_rfp_pdf(ticket_id: str, pdf_path: str) -> dict:
    """Convert a previously stored PDF without changing ticket state."""
    raw_dir = (PROJECT_ROOT / "data/raw").resolve()
    path = Path(pdf_path).resolve()

    if not path.is_relative_to(raw_dir):
        raise ValueError("PDF path outside permitted storage")

    if path.suffix.lower() != ".pdf":
        raise ValueError("Only PDF files are supported")

    result = convert_pdf_to_markdown(path)

    markdown_path = path.with_suffix(".md")
    temporary_path = path.with_suffix(".md.tmp")

    try:
        temporary_path.write_text(
            result["markdown"],
            encoding="utf-8",
        )
        temporary_path.replace(markdown_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return {
        "ticket_id": ticket_id,
        "markdown_path": str(markdown_path),
        "readability_metrics": result["readability_metrics"],
        "conversion_status": "converted",
    }
