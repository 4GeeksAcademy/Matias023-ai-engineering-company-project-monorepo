"""Fragmentacion de documentos oficiales TrackFlow."""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import hashlib
import re

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "docs/company-knowledge-base"

DOCUMENTS = {
    "trackflow-sla-delivery.es.md": "sla-delivery",
    "trackflow-returns-policy.es.md": "returns-policy",
    "trackflow-carrier-coverage.es.md": "carrier-coverage",
    "trackflow-storage-pricing.es.md": "storage-pricing",
}


@dataclass(frozen=True)
class Chunk:
    source_document: str
    source_file: str
    section: str
    chunk_index: int
    body: str
    text: str
    source_sha256: str


def normalize(text: str) -> str:
    return " ".join(text.split())


def chunk_document(path: Path, source: str) -> list[Chunk]:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()

    if not lines or not lines[0].startswith("# "):
        raise ValueError(f"Documento sin titulo: {path}")

    section = lines[0].removeprefix("# ").strip()
    body = normalize("\n".join(lines[1:]))

    if not body:
        raise ValueError(f"Documento vacio: {path}")

    # Dividir en unidades delimitadas por frases,
    # listas y encabezados de informacion.
    units = [
        unit.strip()
        for unit in re.split(
            r"(?<=[.!?:])\s+(?=(?:[-*]|\d+[.)]|[A-ZÁÉÍÓÚÑ¿]))",
            body,
        )
        if unit.strip()
    ]

    groups = []
    current = []

    for unit in units:
        candidate = " ".join(current + [unit])

        if current and len(candidate) > 350:
            groups.append(" ".join(current))
            current = [unit]
        else:
            current.append(unit)

    if current:
        groups.append(" ".join(current))

    if len(groups) < 3:
        raise ValueError(
            f"Menos de tres chunks en {path.name}: {len(groups)}"
        )

    # Comprobar que no se perdio contenido.
    assert normalize(" ".join(groups)) == body

    checksum = hashlib.sha256(
        original.encode("utf-8")
    ).hexdigest()

    return [
        Chunk(
            source_document=source,
            source_file=path.name,
            section=section,
            chunk_index=index,
            body=group,
            text=f"{section}\n{group}",
            source_sha256=checksum,
        )
        for index, group in enumerate(groups)
    ]


def build_corpus() -> list[Chunk]:
    chunks = []

    for filename, source in DOCUMENTS.items():
        path = CORPUS / filename

        if not path.is_file():
            raise FileNotFoundError(path)

        chunks.extend(chunk_document(path, source))

    counts = Counter(
        chunk.source_document for chunk in chunks
    )

    assert len(counts) == 4
    assert all(count >= 3 for count in counts.values())

    return chunks
