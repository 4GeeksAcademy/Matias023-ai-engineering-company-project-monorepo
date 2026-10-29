"""OWASP A01: aislamiento de eventos RFP SSE."""

import asyncio

import pytest

from rfp_sse import STREAM, stream_events


class FakeRequest:
    def __init__(self):
        self.calls = 0

    async def is_disconnected(self):
        self.calls += 1
        return self.calls > 1


class FakeRedis:
    def __init__(self):
        self.closed = False

    async def xread(self, streams, count, block):
        return [
            (
                STREAM,
                [
                    (
                        "100-0",
                        {
                            "ticket_id": "ticket-privado-usuario-a",
                            "status": "analizando",
                            "owner_uuid": "usuario-a",
                        },
                    )
                ],
            )
        ]

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize(
    "recipient_uuid,expected_visible",
    [("usuario-a", True), ("usuario-b", False)],
)
def test_sse_isolates_events_by_owner(recipient_uuid, expected_visible):
    """Un stream sin identidad de destinatario no debe emitir tickets ajenos."""

    async def collect():
        redis = FakeRedis()
        request = FakeRequest()

        output = []
        async for chunk in stream_events(
            redis, request, "0-0", recipient_uuid
        ):
            output.append(chunk)

        return "".join(output), redis.closed

    output, closed = asyncio.run(collect())

    assert closed is True

    # ANTES: falla porque el stream entrega el ticket sin comprobar
    # el destinatario. DESPUES: sustituiremos esta comprobacion
    # por escenarios explicitos de usuario A y usuario B.
    visible = "ticket-privado-usuario-a" in output
    assert visible is expected_visible, (
        "OWASP A01: SSE entrego un evento al destinatario incorrecto"
    )
