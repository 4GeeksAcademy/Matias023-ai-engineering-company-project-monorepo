"""Authenticated RFP PDF upload and asynchronous intake."""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from database import get_engine
from rfp_models import RFPTicket
from security import get_current_user
from tasks.rfp_intake import convert_rfp_pdf

router = APIRouter(prefix="/rfp", tags=["rfp"])

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"
MAX_BYTES = 15 * 1024 * 1024


@router.post("/intake", status_code=202)
async def upload_rfp(
    file: UploadFile = File(...),
    _user=Depends(get_current_user),
):
    """Store a PDF, persist its ticket and enqueue conversion."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(415, "A PDF file is required")

    engine = get_engine()
    if engine.dialect.name != "postgresql":
        raise HTTPException(503, "RFP intake requires PostgreSQL")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{uuid4()}.pdf"
    total = 0

    try:
        with path.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise HTTPException(413, "PDF exceeds 15 MB")
                if total == len(chunk) and not chunk.startswith(b"%PDF-"):
                    raise HTTPException(415, "Invalid PDF signature")
                output.write(chunk)

        if total == 0:
            raise HTTPException(415, "Empty PDF")

        import pymupdf

        try:
            with pymupdf.open(str(path)) as document:
                if not document.is_pdf or document.page_count == 0:
                    raise ValueError("Invalid PDF")
        except (pymupdf.FileDataError, pymupdf.EmptyFileError, ValueError):
            raise HTTPException(415, "Invalid PDF structure")

        worker_pdf_path = str(Path("/app/data/raw") / path.name)
        ticket = RFPTicket(raw_pdf_path=worker_pdf_path)
        with Session(engine) as session:
            session.add(ticket)
            session.commit()
            ticket_id = ticket.ticket_id

        try:
            job = convert_rfp_pdf.apply_async(
                kwargs={
                    "ticket_id": ticket_id,
                    "pdf_path": worker_pdf_path,
                }
            )
        except Exception:
            try:
                with Session(engine) as session:
                    persisted = session.get(RFPTicket, ticket_id)
                    if persisted is not None:
                        session.delete(persisted)
                        session.commit()
            finally:
                path.unlink(missing_ok=True)
            raise HTTPException(503, "Unable to enqueue RFP")

        return {
            "ticket_id": ticket_id,
            "status": "analizando",
            "task_id": job.id,
        }

    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except (OSError, SQLAlchemyError):
        path.unlink(missing_ok=True)
        raise HTTPException(503, "RFP intake unavailable")
    finally:
        await file.close()
