"""Comprueba que el JWT no llegue a checkpoints ni trazas."""

from pathlib import Path
from types import SimpleNamespace

from langgraph.checkpoint.sqlite import SqliteSaver

from agent_graph import build_agent
from agent_tracing import run_traced


def test_jwt_no_se_persiste_en_sqlite_ni_trazas(tmp_path):
    secret = "JWT_PRIVADO_NO_PERSISTIR_987654321"
    database = tmp_path / "checkpoints.sqlite3"
    trace_file = tmp_path / "trace.jsonl"
    received_tokens = []

    def ticket_tool(request, *, token, **kwargs):
        received_tokens.append(token)
        assert request.incident_id == 42
        assert kwargs["timeout_seconds"] == 5.0

        return SimpleNamespace(
            status="not_found",
            incident=None,
        )

    service = SimpleNamespace(threshold=0.54)

    with SqliteSaver.from_conn_string(str(database)) as saver:
        graph = build_agent(
            service=service,
            checkpointer=saver,
            ticket_tool=ticket_tool,
        )

        result = run_traced(
            graph,
            "Consulta el ticket 42",
            context={"token": secret},
            trace_file=trace_file,
        )

        assert result["reason"] == "ticket_not_found"
        assert received_tokens == [secret]

        for key in ("token", "access_token", "jwt"):
            assert key not in graph.get_state({
                "configurable": {
                    "thread_id": next(
                        __import__("json").loads(line)["thread_id"]
                        for line in trace_file.read_text().splitlines()
                    )
                }
            }).values

    assert database.is_file()
    assert trace_file.is_file()

    assert secret.encode() not in database.read_bytes()
    assert secret not in trace_file.read_text()

    assert "ticket_lookup" in trace_file.read_text()
