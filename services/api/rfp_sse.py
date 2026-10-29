"""RFP notifications backed by Redis Streams."""

import importlib
import json
import os
import re

from redis import asyncio as aioredis

STREAM = "trackflow:rfp:created"
EVENT = "rfp.created"
CURSOR_PATTERN = re.compile(r"^[0-9]+-[0-9]+$")


def validate_cursor(value):
    if not value:
        return None
    if not CURSOR_PATTERN.fullmatch(value):
        raise ValueError("Invalid SSE cursor")
    return value


def redis_url():
    for name in (
        "RFP_SSE_REDIS_URL",
        "CELERY_BROKER_URL",
        "REDIS_URL",
    ):
        value = os.getenv(name)
        if value:
            if not value.startswith(("redis://", "rediss://")):
                raise RuntimeError("SSE requires a Redis URL")
            return value

    for module_name in ("celery_app", "tasks.celery_app"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue

        for attribute in ("celery_app", "app"):
            app = getattr(module, attribute, None)
            config = getattr(app, "conf", None)
            value = getattr(config, "broker_url", None)

            if isinstance(value, str) and value.startswith(
                ("redis://", "rediss://")
            ):
                return value

    raise RuntimeError("SSE Redis configuration not found")


def make_client():
    return aioredis.from_url(
        redis_url(),
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=20,
    )


def format_created_event(event_id, fields):
    payload = {
        "ticket_id": fields["ticket_id"],
        "status": fields["status"],
    }

    return (
        f"id: {event_id}\n"
        f"event: {EVENT}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


async def publish_rfp_created(ticket_id, status, owner_uuid=None):
    client = make_client()
    try:
        return await client.xadd(
            STREAM,
            {
                "ticket_id": str(ticket_id),
                "status": str(status),
                "owner_uuid": str(owner_uuid or ""),
            },
            maxlen=10000,
            approximate=True,
        )
    finally:
        await client.aclose()


async def initial_cursor(client, requested):
    cursor = validate_cursor(requested)

    if cursor is not None:
        return cursor

    latest = await client.xrevrange(STREAM, count=1)
    return latest[0][0] if latest else "0-0"


async def stream_events(client, request, cursor, owner_uuid=None):
    try:
        yield "retry: 3000\n\n"

        while not await request.is_disconnected():
            result = await client.xread(
                {STREAM: cursor},
                count=100,
                block=15000,
            )

            if not result:
                yield ": keep-alive\n\n"
                continue

            for _, entries in result:
                for event_id, fields in entries:
                    cursor = event_id
                    event_owner = fields.get('owner_uuid')
                    if not owner_uuid or not event_owner:
                        continue
                    if event_owner != owner_uuid:
                        continue
                    yield format_created_event(event_id, fields)
    finally:
        await client.aclose()
