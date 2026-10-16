"""Endpoint autenticado del agente LangGraph TrackFlow."""

from fastapi import APIRouter, Depends, HTTPException

from routers.rag import RAGAnswer, RAGQuestion
from security import get_current_user

router = APIRouter(
    prefix="/agent",
    tags=["Agent"],
    dependencies=[Depends(get_current_user)],
)


def get_agent_runner():
    """Proporciona el ejecutor; reemplazable en tests."""
    from agent_persistence import persistent_agent
    from agent_tracing import run_traced

    def execute(question: str):
        with persistent_agent() as graph:
            return run_traced(graph, question)

    return execute


@router.post("/query", response_model=RAGAnswer)
def query_agent(
    payload: RAGQuestion,
    runner=Depends(get_agent_runner),
):
    question = payload.question.strip()

    if not question:
        raise HTTPException(
            status_code=422,
            detail="La pregunta no puede estar vacía",
        )

    try:
        return runner(question)
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="El agente no está disponible",
        ) from None
