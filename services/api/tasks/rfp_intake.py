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

    if not result["readability_metrics"].get("readable"):
        return {
            "ticket_id": ticket_id,
            "markdown_path": str(markdown_path),
            "readability_metrics": result["readability_metrics"],
            "conversion_status": "manual_review_required",
            "classification_task_id": None,
        }

    classification_job = classify_rfp_document.apply_async(
        kwargs={
            "ticket_id": ticket_id,
            "markdown_path": str(markdown_path),
            "readability_metrics": result["readability_metrics"],
        },
        retry=True,
        retry_policy={
            "max_retries": 3,
            "interval_start": 1,
            "interval_step": 2,
            "interval_max": 5,
        },
    )

    return {
        "ticket_id": ticket_id,
        "markdown_path": str(markdown_path),
        "readability_metrics": result["readability_metrics"],
        "conversion_status": "converted",
        "classification_task_id": classification_job.id,
    }


@celery_app.task(name="tasks.rfp_intake.classify_rfp_document")
def classify_rfp_document(
    ticket_id: str,
    markdown_path: str,
    readability_metrics: dict,
) -> dict:
    """Classify converted Markdown and persist validated results."""
    import os

    api_dir = PROJECT_ROOT / "services" / "api"
    if str(api_dir) not in sys.path:
        sys.path.insert(0, str(api_dir))

    from sqlmodel import Session

    from database import get_engine
    from rfp_models import RFPTicket
    from rfp_classification_service import persist_rfp_classification
    from data.pipelines.rfp_intake.rfp_classifier import classify_rfp

    raw_dir = (PROJECT_ROOT / "data/raw").resolve()
    path = Path(markdown_path).resolve()

    if not path.is_relative_to(raw_dir) or path.suffix != ".md":
        raise ValueError("Markdown path outside permitted storage")

    engine = get_engine()
    if engine.dialect.name != "postgresql":
        raise RuntimeError("RFP classification requires PostgreSQL")

    with Session(engine) as session:
        ticket = session.get(RFPTicket, ticket_id)
        if ticket is None:
            raise ValueError("RFP ticket not found")
        if ticket.status != "analizando":
            raise ValueError("RFP ticket is not analyzing")
        if Path(ticket.raw_pdf_path).resolve() != path.with_suffix(".pdf"):
            raise ValueError("Markdown does not belong to RFP ticket")

    if not readability_metrics.get("readable"):
        raise ValueError("PDF is not readable; manual review required")

    model = os.getenv("GEMINI_MODEL")
    if not model:
        raise RuntimeError("GEMINI_MODEL is not configured")

    markdown = path.read_text(encoding="utf-8")

    try:
        classification = classify_rfp(
            markdown,
            model=model,
        )
    except ValueError as exc:
        reason = str(exc)
        review_reasons = (
            "Unsupported extracted metadata:",
            "Unsupported department:",
            "Negated service requires review:",
            "Classification has no textual evidence",
            "Classification evidence not found in document",
        )
        if not reason.startswith(review_reasons):
            raise
        return {
            "ticket_id": ticket_id,
            "classification_status": "manual_review_required",
            "review_reason": reason,
            "document_type": None,
        }

    persisted = persist_rfp_classification(
        ticket_id,
        classification,
        readability_metrics,
    )

    return {
        **persisted,
        "document_type": classification.document_type,
        "classification_status": "classified",
    }
