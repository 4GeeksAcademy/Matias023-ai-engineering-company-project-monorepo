"""Regression tests for RFP human-feedback preservation."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PIPELINE = ROOT / "data/pipelines/rfp_intake"


def test_human_feedback_remains_in_generation_arguments():
    path = PIPELINE / "rfp_response_cycle.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    candidates = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        for keyword in node.keywords:
            if keyword.arg != "feedback":
                continue

            names = {
                item.id
                for item in ast.walk(keyword.value)
                if isinstance(item, ast.Name)
            }

            if "initial_feedback" in names:
                candidates.append(keyword.value)

    assert len(candidates) == 1, (
        "Expected one generation feedback argument "
        "that preserves initial_feedback"
    )

    expression = compile(
        ast.Expression(body=candidates[0]),
        str(path),
        "eval",
    )

    human = "Eliminar plazo de 48 horas sin evidencia documental."
    evaluation = "Aclarar condiciones comerciales."

    result = eval(
        expression,
        {"__builtins__": {"dict": dict}},
        {
            "initial_feedback": human,
            "feedback": evaluation,
        },
    )

    assert human in result
    assert evaluation in result
    assert result.index(human) < result.index(evaluation)

    later_result = eval(
        expression,
        {"__builtins__": {"dict": dict}},
        {
            "initial_feedback": human,
            "feedback": "Revisar coherencia del documento.",
        },
    )

    assert human in later_result


def test_generator_requires_documentary_evidence():
    source = (
        PIPELINE / "rfp_response_generator.py"
    ).read_text(encoding="utf-8")

    assert "verified documentary evidence" in source
    assert "pending confirmation" in source


def test_evaluator_rejects_unsupported_time_commitments():
    source = (
        PIPELINE / "rfp_response_evaluators.py"
    ).read_text(encoding="utf-8")

    assert "unsupported time commitments are violations" in source
