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


@router.get("/tickets")
def list_rfp_tickets(
    _user=Depends(get_current_user),
):
    """List recent RFP tickets for authenticated users."""
    from sqlmodel import select
    from rfp_models import RFPMetadata

    engine = get_engine()
    if engine.dialect.name != "postgresql":
        raise HTTPException(503, "RFP database unavailable")

    with Session(engine) as session:
        tickets = session.exec(
            select(RFPTicket)
            .order_by(RFPTicket.created_at.desc())
            .limit(50)
        ).all()

        result = []
        for ticket in tickets:
            metadata = session.exec(
                select(RFPMetadata).where(
                    RFPMetadata.ticket_id == ticket.ticket_id
                )
            ).one_or_none()

            result.append({
                "ticket_id": ticket.ticket_id,
                "status": ticket.status,
                "created_at": ticket.created_at.isoformat(),
                "client_name": metadata.client_name if metadata else None,
                "departments_needed": (
                    metadata.departments_needed if metadata else []
                ),
            })

    return {"tickets": result}


@router.get("/tickets/{ticket_id}")
def get_rfp_ticket(
    ticket_id: str,
    _user=Depends(get_current_user),
):
    """Read one ticket, metadata and department drafts."""
    from sqlmodel import select
    from rfp_models import RFPMetadata, RFPDepartmentSection

    engine = get_engine()
    if engine.dialect.name != "postgresql":
        raise HTTPException(503, "RFP database unavailable")

    with Session(engine) as session:
        ticket = session.get(RFPTicket, ticket_id)
        if ticket is None:
            raise HTTPException(404, "RFP ticket not found")

        metadata = session.exec(
            select(RFPMetadata).where(
                RFPMetadata.ticket_id == ticket_id
            )
        ).one_or_none()

        sections = session.exec(
            select(RFPDepartmentSection).where(
                RFPDepartmentSection.ticket_id == ticket_id
            )
        ).all()

        return {
            "ticket_id": ticket.ticket_id,
            "status": ticket.status,
            "created_at": ticket.created_at.isoformat(),
            "client_name": metadata.client_name if metadata else None,
            "client_country": metadata.client_country if metadata else None,
            "departments_needed": (
                metadata.departments_needed if metadata else []
            ),
            "sections": [
                {
                    "department_id": section.department_id,
                    "key_aspects": section.key_aspects,
                    "draft_content": section.draft_content,
                    "evaluation_results": section.evaluation_results,
                    "approval_status": section.approval_status,
                }
                for section in sections
            ],
        }


@router.post("/tickets/{ticket_id}/generate", status_code=202)
def start_rfp_response_generation(
    ticket_id: str,
    _user=Depends(get_current_user),
):
    """Reserve a completed RFP and dispatch its active departments."""
    from celery import group
    from sqlmodel import select
    from rfp_models import (
        RFPMetadata, RFPDepartmentSection, utcnow,
    )
    from tasks.rfp_intake import generate_rfp_response
    from data.pipelines.rfp_intake.rfp_orchestrator import (
        plan_departments,
    )

    engine = get_engine()
    if engine.dialect.name != "postgresql":
        raise HTTPException(503, "RFP database unavailable")

    with Session(engine) as session:
        with session.begin():
            ticket = session.exec(
                select(RFPTicket)
                .where(RFPTicket.ticket_id == ticket_id)
                .with_for_update()
            ).one_or_none()

            if ticket is None:
                raise HTTPException(404, "RFP ticket not found")

            if ticket.status != "analisis_completo":
                raise HTTPException(
                    409,
                    "Ticket is not available for response generation",
                )

            metadata = session.exec(
                select(RFPMetadata).where(
                    RFPMetadata.ticket_id == ticket_id
                )
            ).one_or_none()

            if metadata is None:
                raise HTTPException(409, "RFP metadata missing")

            plan = plan_departments(metadata.departments_needed)
            departments = [item["department_id"] for item in plan]

            sections = session.exec(
                select(RFPDepartmentSection).where(
                    RFPDepartmentSection.ticket_id == ticket_id
                )
            ).all()

            by_department = {
                section.department_id: section
                for section in sections
            }

            if (
                len(sections) != len(departments)
                or set(by_department) != set(departments)
                or any(
                    not by_department[dept].key_aspects
                    or by_department[dept].approval_status is not None
                    or by_department[dept].evaluation_results.get(
                        "review_status"
                    )
                    for dept in departments
                )
            ):
                raise HTTPException(
                    409,
                    "Department handoff incomplete or already processed",
                )

            ticket.status = "generando_borrador"
            ticket.updated_at = utcnow()

    try:
        workflow = group(
            generate_rfp_response.s(ticket_id, department)
            for department in departments
        )
        job = workflow.apply_async()
    except Exception as exc:
        # Publication may have partially succeeded.
        # Keep the reservation: automatic retry could duplicate work.
        # Recovery requires checking broker and worker state first.
        raise HTTPException(
            503,
            "Dispatch uncertain; ticket remains reserved for recovery",
        ) from exc

    return {
        "ticket_id": ticket_id,
        "status": "generando_borrador",
        "departments": departments,
        "celery_group_id": job.id,
    }
