from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/rag"))

from chunking import (
    DOCUMENTS,
    CORPUS,
    build_corpus,
    chunk_document,
    normalize,
)


def test_cuatro_documentos_tres_chunks_minimo():
    chunks = build_corpus()
    counts = Counter(
        chunk.source_document for chunk in chunks
    )

    assert len(counts) == 4
    assert min(counts.values()) >= 3


def test_contenido_original_sin_perdidas():
    for filename, source in DOCUMENTS.items():
        path = CORPUS / filename
        content = path.read_text(encoding="utf-8")
        body = normalize(
            "\n".join(content.splitlines()[1:])
        )

        chunks = chunk_document(path, source)

        reconstructed = normalize(
            " ".join(chunk.body for chunk in chunks)
        )

        assert reconstructed == body


def test_metadatos_y_reglas_comerciales():
    chunks = build_corpus()

    for chunk in chunks:
        assert chunk.source_document in DOCUMENTS.values()
        assert chunk.section
        assert chunk.text
        assert len(chunk.source_sha256) == 64

    complete_text = " ".join(
        chunk.body for chunk in chunks
    )

    for term in [
        "Black Friday",
        "Sofía Ramos",
        "SEUR",
        "Miguel Torres",
    ]:
        assert term in complete_text
