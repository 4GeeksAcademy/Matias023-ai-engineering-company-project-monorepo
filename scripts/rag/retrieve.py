"""Recuperacion semantica con fuentes trazables."""

import math
from fastembed import TextEmbedding
from qdrant_client import QdrantClient

from index import COLLECTION, MODEL, QDRANT_URL


class Retriever:
    def __init__(self, client=None, embedder=None):
        self.client = client or QdrantClient(
            url=QDRANT_URL, timeout=30
        )
        self.embedder = embedder or TextEmbedding(
            model_name=MODEL
        )

    def retrieve(self, question, top_k=3, threshold=None):
        if not isinstance(question, str) or not question.strip():
            raise ValueError("La pregunta no puede estar vacia")

        if not 1 <= top_k <= 10:
            raise ValueError("top_k debe estar entre 1 y 10")

        if threshold is not None:
            if not math.isfinite(threshold) or not -1 <= threshold <= 1:
                raise ValueError("Umbral de similitud invalido")

        vector = next(
            iter(self.embedder.embed([question.strip()]))
        )

        result = self.client.query_points(
            collection_name=COLLECTION,
            query=vector.tolist(),
            limit=top_k,
            score_threshold=threshold,
            with_payload=True,
        )

        chunks = []

        for point in result.points:
            payload = point.payload or {}
            chunks.append({
                "id": str(point.id),
                "score": float(point.score),
                "source_document": payload.get("source_document"),
                "source_file": payload.get("source_file"),
                "section": payload.get("section"),
                "chunk_index": payload.get("chunk_index"),
                "text": payload.get("text", ""),
            })

        return chunks
