"""Endpoint autenticado para consultas RAG TrackFlow."""

import sys
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from security import get_current_user


router = APIRouter(
    prefix="/rag",
    tags=["RAG"],
    dependencies=[Depends(get_current_user)],
)


class RAGQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class RAGSource(BaseModel):
    citation: int
    source_document: str
    source_file: str | None = None
    section: str | None = None
    chunk_index: int | None = None
    score: float | None = None


class RAGAnswer(BaseModel):
    answer: str
    abstained: bool
    reason: str
    sources: list[RAGSource]
    threshold: float


@lru_cache(maxsize=1)
def get_rag_service():
    """Carga el pipeline una sola vez por proceso API."""
    root = Path(__file__).resolve().parents[3]
    rag_dir = root / "scripts" / "rag"

    if not rag_dir.is_dir():
        raise RuntimeError(
            "No se encontro el proyecto RAG"
        )

    if str(rag_dir) not in sys.path:
        sys.path.insert(0, str(rag_dir))

    from generate import RAGService

    return RAGService()


@router.post("/query", response_model=RAGAnswer)
def query_rag(
    payload: RAGQuestion,
    service=Depends(get_rag_service),
):
    question = payload.question.strip()

    if not question:
        raise HTTPException(
            status_code=422,
            detail="La pregunta no puede estar vacia",
        )

    try:
        return service.query(question)

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception:
        # No exponer mensajes internos ni credenciales.
        raise HTTPException(
            status_code=503,
            detail="El asistente RAG no esta disponible",
        ) from None
