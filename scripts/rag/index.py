"""Indexacion reproducible de los cuatro documentos."""

import json
import os
import sys
import uuid
from collections import Counter
from pathlib import Path

from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from chunking import build_corpus

COLLECTION = "trackflow_knowledge"
MODEL = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)
DIMENSIONS = 384
QDRANT_URL = os.getenv(
    "QDRANT_URL",
    "http://127.0.0.1:6333",
)


def setup(client: QdrantClient) -> None:
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=models.VectorParams(
                size=DIMENSIONS,
                distance=models.Distance.COSINE,
            ),
        )
        print("PASS: coleccion creada")
    else:
        config = client.get_collection(
            COLLECTION
        ).config.params.vectors

        assert config.size == DIMENSIONS
        assert config.distance == models.Distance.COSINE

        print("PASS: coleccion existente compatible")


def embed(chunks):
    model = TextEmbedding(model_name=MODEL)

    vectors = list(model.embed(
        [chunk.text for chunk in chunks],
        batch_size=8,
    ))

    assert len(vectors) == len(chunks)
    assert all(len(vector) == DIMENSIONS for vector in vectors)

    return vectors


def index_chunks(client, chunks, vectors):
    points = []

    for chunk, vector in zip(chunks, vectors):
        point_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"trackflow-rag-v1:"
            f"{chunk.source_document}:"
            f"{chunk.chunk_index}",
        ))

        payload = {
            "company": "trackflow",
            "source_document": chunk.source_document,
            "source_file": chunk.source_file,
            "section": chunk.section,
            "language": "es",
            "chunk_index": chunk.chunk_index,
            "text": chunk.text,
            "source_sha256": chunk.source_sha256,
        }

        points.append(models.PointStruct(
            id=point_id,
            vector=vector.tolist(),
            payload=payload,
        ))

    client.upsert(
        collection_name=COLLECTION,
        points=points,
        wait=True,
    )


def main():
    print("=== CHUNKING ===")
    chunks = build_corpus()

    counts = Counter(
        chunk.source_document for chunk in chunks
    )

    for source, count in sorted(counts.items()):
        print(f"{source}: {count} chunks")

    print("Total:", len(chunks))

    client = QdrantClient(
        url=QDRANT_URL,
        timeout=30,
    )

    print("=== QDRANT SETUP ===")
    setup(client)

    # Evitar mezclar corpus nuevos con indexaciones
    # anteriores de distinto tamaño.
    existing = client.count(
        collection_name=COLLECTION,
        exact=True,
    ).count

    if existing not in (0, len(chunks)):
        raise RuntimeError(
            f"Coleccion contiene {existing} puntos; "
            f"se esperaban 0 o {len(chunks)}. "
            "Revisar antes de reindexar."
        )

    print("=== GENERAR EMBEDDINGS ===")
    print("Modelo:", MODEL)

    vectors = embed(chunks)

    print("PASS: embeddings generados")
    print("Dimension:", DIMENSIONS)

    print("=== INDEXAR DOCUMENTOS ===")
    index_chunks(client, chunks, vectors)

    total = client.count(
        collection_name=COLLECTION,
        exact=True,
    ).count

    assert total == len(chunks)

    points, offset = client.scroll(
        collection_name=COLLECTION,
        limit=100,
        with_payload=True,
        with_vectors=False,
    )

    assert offset is None
    assert len(points) == total

    actual = Counter(
        point.payload["source_document"]
        for point in points
    )

    assert actual == counts

    required = {
        "company",
        "source_document",
        "section",
        "language",
        "chunk_index",
        "text",
    }

    for point in points:
        assert required.issubset(point.payload)
        assert point.payload["company"] == "trackflow"
        assert point.payload["language"] == "es"

    print("=== RESULTADO ===")
    print("Coleccion:", COLLECTION)
    print("Puntos:", total)
    print("Fuentes:", len(actual))
    print("Distribucion:", json.dumps(dict(actual)))
    print("PASS: indexacion y metadatos verificados")


if __name__ == "__main__":
    main()
