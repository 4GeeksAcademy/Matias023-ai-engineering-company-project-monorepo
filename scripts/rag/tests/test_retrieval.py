import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/rag"))

from retrieve import Retriever
from diagnose_retrieval import validate_ground_truth
import json


class FakeEmbedder:
    def embed(self, texts):
        return iter([np.ones(384, dtype=np.float32)])


class FakeClient:
    def __init__(self):
        self.calls = []

    def query_points(self, **kwargs):
        self.calls.append(kwargs)

        return SimpleNamespace(points=[
            SimpleNamespace(
                id="example",
                score=0.85,
                payload={
                    "source_document": "sla-delivery",
                    "source_file": "trackflow-sla-delivery.es.md",
                    "section": "SLA de Entrega",
                    "chunk_index": 0,
                    "text": "Texto de prueba",
                },
            )
        ])


def test_recuperacion_y_trazabilidad():
    client = FakeClient()
    retriever = Retriever(client=client, embedder=FakeEmbedder())

    hits = retriever.retrieve(
        "¿Cuál es el plazo de entrega?",
        top_k=3,
        threshold=0.5,
    )

    assert len(hits) == 1
    assert hits[0]["score"] == 0.85
    assert hits[0]["source_document"] == "sla-delivery"
    assert hits[0]["chunk_index"] == 0

    call = client.calls[0]
    assert call["collection_name"] == "trackflow_knowledge"
    assert call["limit"] == 3
    assert call["score_threshold"] == 0.5
    assert len(call["query"]) == 384


def test_preguntas_invalidas():
    retriever = Retriever(
        client=FakeClient(), embedder=FakeEmbedder()
    )

    with pytest.raises(ValueError):
        retriever.retrieve(" ")

    with pytest.raises(ValueError):
        retriever.retrieve("Pregunta", top_k=0)

    with pytest.raises(ValueError):
        retriever.retrieve("Pregunta", threshold=float("nan"))


def test_preguntas_documentadas():
    cases = json.loads(
        (ROOT / "data/eval/test-queries.json").read_text()
    )
    validate_ground_truth(cases)
