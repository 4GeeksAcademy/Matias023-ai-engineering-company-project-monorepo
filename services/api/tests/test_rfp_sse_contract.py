"""SSE framing and cursor regression tests."""

import asyncio
import json

import pytest

from rfp_sse import (
    EVENT,
    format_created_event,
    initial_cursor,
    stream_events,
    validate_cursor,
)


def test_sse_event_format():
    output = format_created_event(
        "100-0",
        {"ticket_id": "rfp-123", "status": "analizando"},
    )

    assert output.startswith("id: 100-0\n")
    assert "\nevent: rfp.created\n" in output
    assert output.endswith("\n\n")
    assert EVENT == "rfp.created"

    data_line = next(
        line for line in output.splitlines()
        if line.startswith("data: ")
    )
    payload = json.loads(data_line.removeprefix("data: "))
    assert payload == {
        "ticket_id": "rfp-123",
        "status": "analizando",
    }


def test_cursor_validation():
    assert validate_cursor(None) is None
    assert validate_cursor("100-0") == "100-0"

    with pytest.raises(ValueError):
        validate_cursor("incorrect")


def test_replay_cursor():
    class FakeRedis:
        async def xrevrange(self, *args, **kwargs):
            return [("150-0", {})]

    async def verify():
        client = FakeRedis()
        assert await initial_cursor(client, None) == "150-0"
        assert await initial_cursor(client, "100-0") == "100-0"

    asyncio.run(verify())


def test_stream_frames_and_cleanup():
    class FakeRequest:
        async def is_disconnected(self):
            return False

    class FakeRedis:
        def __init__(self):
            self.closed = False

        async def xread(self, *args, **kwargs):
            return [
                (
                    "trackflow:rfp:created",
                    [
                        (
                            "200-0",
                            {
                                "ticket_id": "rfp-200",
                                "status": "analizando",
                                "owner_uuid": "usuario-a",
                            },
                        )
                    ],
                )
            ]

        async def aclose(self):
            self.closed = True

    async def verify():
        client = FakeRedis()
        stream = stream_events(
            client, FakeRequest(), "100-0", "usuario-a"
        )

        assert "retry:" in await anext(stream)

        event = await asyncio.wait_for(anext(stream), timeout=3)
        assert "id: 200-0\n" in event
        assert "rfp-200" in event

        await stream.aclose()
        assert client.closed

    asyncio.run(verify())
