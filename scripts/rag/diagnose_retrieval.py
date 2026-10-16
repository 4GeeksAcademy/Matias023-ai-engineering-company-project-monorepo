"""Evaluacion real de recuperacion, sin LLM."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from chunking import DOCUMENTS, CORPUS, normalize
from retrieve import Retriever

TEST_FILE = ROOT / "data/eval/test-queries.json"
OUTPUT = ROOT / "data/eval/rag_retrieval_diagnostics.json"


def validate_ground_truth(cases):
    assert len(cases) >= 8
    assert len({c["id"] for c in cases}) == len(cases)

    sources = set()

    for case in cases:
        source = case["source"]
        sources.add(source)

        filenames = [
            name for name, value in DOCUMENTS.items()
            if value == source
        ]
        assert len(filenames) == 1

        content = normalize(
            (CORPUS / filenames[0]).read_text(encoding="utf-8")
        )

        assert (
            case["anchor"].casefold() in content.casefold()
        ), f"Dato no encontrado en documento: {case['id']}"

    assert len(sources) == 4
    assert any("Black Friday" in c["question"] for c in cases)


def is_relevant(hit, case):
    return (
        hit["source_document"] == case["source"]
        and case["anchor"].casefold()
        in hit["text"].casefold()
    )


def main():
    cases = json.loads(TEST_FILE.read_text(encoding="utf-8"))
    validate_ground_truth(cases)

    retriever = Retriever()
    results = []

    print("=== PREGUNTAS CON RESPUESTA DOCUMENTADA ===")

    for case in cases:
        hits = retriever.retrieve(case["question"], top_k=3)

        correct_ranks = [
            index + 1
            for index, hit in enumerate(hits)
            if is_relevant(hit, case)
        ]

        success = bool(correct_ranks)
        rank = min(correct_ranks) if success else None

        results.append({
            "id": case["id"],
            "question": case["question"],
            "expected_source": case["source"],
            "expected_anchor": case["anchor"],
            "correct_rank": rank,
            "hit_at_3": success,
            "top3": hits,
        })

        status = "PASS" if success else "MISS"
        print(f"\n{status} | {case['id']} | rank={rank}")

        for position, hit in enumerate(hits, start=1):
            print(
                f"  #{position} "
                f"score={hit['score']:.4f} "
                f"source={hit['source_document']} "
                f"chunk={hit['chunk_index']}"
            )

    hits_count = sum(r["hit_at_3"] for r in results)
    recall = hits_count / len(cases)

    print("\n=== CONSULTAS FUERA DEL CORPUS ===")

    unsupported_questions = [
        "¿Cuál es el horario de atención telefónica del call center?",
        "¿Aceptan pagos de devoluciones en criptomonedas?",
        "¿Garantizan entregas en dos horas dentro de Chile?",
    ]

    unsupported = []

    for question in unsupported_questions:
        hits = retriever.retrieve(question, top_k=3)
        max_score = hits[0]["score"] if hits else None

        unsupported.append({
            "question": question,
            "top_score": max_score,
            "top3": hits,
        })

        print(
            f"Sin respuesta documentada | "
            f"score maximo={max_score}"
        )

    report = {
        "collection": "trackflow_knowledge",
        "metric": "fact-level Recall@3",
        "minimum_required": 0.80,
        "question_count": len(cases),
        "success_count": hits_count,
        "recall_at_3": recall,
        "passes_target": recall >= 0.80,
        "threshold_applied": None,
        "test_results": results,
        "unsupported_diagnostics": unsupported,
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("\n========== RESULTADO ==========")
    print(f"Preguntas: {len(cases)}")
    print(f"Correctas en top 3: {hits_count}")
    print(f"Recall@3: {recall:.2%}")
    print("Objetivo: >= 80%")
    print(
        "RESULTADO:",
        "PASS" if recall >= 0.80 else "REQUIERE AJUSTE"
    )
    print("Diagnostico guardado:", OUTPUT)
    print(
        "NOTA: aun falta definir el umbral "
        "y probar la abstencion del asistente."
    )


if __name__ == "__main__":
    main()
