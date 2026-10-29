"""Pruebas de contrato, sesiones y pub/sub."""

import asyncio

import pytest

from chat_realtime import (
    ChatPubSub,
    ChatSessionStore,
    envelope,
)


def test_contract():
    event = envelope(
        "token_chunk",
        {
            "session_id": "chat_1",
            "token": "Tu",
            "sequence": 7,
        }
    )

    assert event["event"] == "token_chunk"

    with pytest.raises(ValueError):
        envelope(
            "rfp.created",
            {"session_id": "chat_1"}
        )

    with pytest.raises(ValueError):
        envelope(
            "token_chunk",
            {
                "session_id": "chat_1",
                "token": "Tu",
            }
        )


def test_session_fields_and_authorization(tmp_path):
    db = ChatSessionStore(
        tmp_path / "chat.sqlite"
    )

    session = db.create(
        user_id=7,
        client_id="cliente_a"
    )

    assert session.agent_id == "first_line_cx"
    assert session.status == "active"
    assert session.created_at

    assert db.get(
        session.session_id,
        user_id=7,
        client_id="cliente_a"
    ) == session

    with pytest.raises(PermissionError):
        db.get(
            session.session_id,
            user_id=8,
            client_id="cliente_a"
        )

    with pytest.raises(PermissionError):
        db.get(
            session.session_id,
            user_id=7,
            client_id="cliente_b"
        )

    with pytest.raises(ValueError):
        db.create(
            user_id=7,
            client_id=""
        )


def test_resume_from_disk_and_partial_message(
    tmp_path
):
    path = tmp_path / "chat.sqlite"

    db = ChatSessionStore(path)

    session = db.create(
        user_id=7,
        client_id="cliente_a"
    )

    db.add_message(
        session.session_id,
        user_id=7,
        client_id="cliente_a",
        role="user",
        content="Hola"
    )

    message_id = db.add_message(
        session.session_id,
        user_id=7,
        client_id="cliente_a",
        role="assistant"
    )

    sequence = db.append_token(
        message_id,
        session_id=session.session_id,
        user_id=7,
        client_id="cliente_a",
        token="Tu"
    )

    assert sequence == 1

    sequence = db.append_token(
        message_id,
        session_id=session.session_id,
        user_id=7,
        client_id="cliente_a",
        token=" pedido"
    )

    assert sequence == 2

    db.finish_message(
        message_id,
        session_id=session.session_id,
        user_id=7,
        client_id="cliente_a",
        status="interrupted"
    )

    db.set_status(
        session.session_id,
        user_id=7,
        client_id="cliente_a",
        status="interrupted"
    )

    restarted = ChatSessionStore(path)

    snapshot = restarted.snapshot(
        session.session_id,
        user_id=7,
        client_id="cliente_a"
    )

    messages = snapshot["data"]["messages"]

    assert [
        item["role"]
        for item in messages
    ] == ["user", "assistant"]

    assert messages[1]["content"] == "Tu pedido"
    assert messages[1]["status"] == "interrupted"

    with pytest.raises(ValueError):
        restarted.append_token(
            message_id,
            session_id=session.session_id,
            user_id=7,
            client_id="cliente_a",
            token=" tardío"
        )


def test_close_is_terminal(tmp_path):
    db = ChatSessionStore(
        tmp_path / "chat.sqlite"
    )

    session = db.create(
        user_id=1,
        client_id="cliente"
    )

    db.set_status(
        session.session_id,
        user_id=1,
        client_id="cliente",
        status="closed"
    )

    with pytest.raises(ValueError):
        db.set_status(
            session.session_id,
            user_id=1,
            client_id="cliente",
            status="active"
        )


def test_pubsub_fanout_and_isolation():
    async def check():
        bus = ChatPubSub()

        q1 = await bus.subscribe("chat_1")
        q2 = await bus.subscribe("chat_1")

        other = await bus.subscribe("chat_2")

        event = envelope(
            "token_chunk",
            {
                "session_id": "chat_1",
                "token": "Hola",
                "sequence": 1,
            }
        )

        await bus.publish(
            "chat_1",
            event
        )

        assert await q1.get() == event
        assert await q2.get() == event
        assert other.empty()

        await bus.unsubscribe("chat_1", q1)
        await bus.unsubscribe("chat_1", q2)
        await bus.unsubscribe("chat_2", other)

    asyncio.run(check())
