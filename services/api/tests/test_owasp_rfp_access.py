"""OWASP A01: pruebas de aislamiento RFP con datos sintéticos."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import rfp_intake
from security import get_current_user


TICKET_ID = "owasp-ticket-sintetico-001"


class FakeResult:
    def __init__(self, value):
        self.value = value

    def one_or_none(self):
        return self.value

    def all(self):
        return [self.value]


class FakeSession:
    def __init__(self, engine):
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, model, identifier):
        if identifier != TICKET_ID:
            return None

        if model.__name__ == "RFPTicket":
            return SimpleNamespace(
                ticket_id=TICKET_ID,
                owner_uuid="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
                status="terminado",
                created_at=datetime.now(timezone.utc),
            )

        if model.__name__ == "RFPFinalDocument":
            return SimpleNamespace(
                content="DOCUMENTO-CONFIDENCIAL-SINTETICO-A"
            )

        return None

    def exec(self, query):
        self.calls += 1

        if self.calls == 1:
            return FakeResult(
                SimpleNamespace(
                    client_name="Cliente Sintetico A",
                    client_country="Chile",
                    departments_needed=["warehouse"],
                )
            )

        return FakeResult(
            SimpleNamespace(
                department_id="warehouse",
                key_aspects=["Prueba OWASP"],
                draft_content="BORRADOR-SINTETICO-A",
                evaluation_results={},
                approval_status="approved",
            )
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        f"/rfp/tickets/{TICKET_ID}",
        f"/rfp/tickets/{TICKET_ID}/final/download",
    ],
)
def test_other_user_cannot_access_rfp(endpoint):
    app = FastAPI()
    app.include_router(rfp_intake.router)

    engine = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql")
    )

    user_a = SimpleNamespace(
        id=101,
        uuid="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
        email="a@example.invalid",
        is_active=True,
        role="user",
    )

    user_b = SimpleNamespace(
        id=202,
        uuid="bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb",
        email="b@example.invalid",
        is_active=True,
        role="user",
    )

    with (
        patch.object(rfp_intake, "get_engine", return_value=engine),
        patch.object(rfp_intake, "Session", FakeSession),
        TestClient(app) as client,
    ):
        anonymous = client.get(endpoint)
        assert anonymous.status_code == 401

        app.dependency_overrides[get_current_user] = lambda: user_a
        owner = client.get(endpoint)
        assert owner.status_code == 200

        app.dependency_overrides[get_current_user] = lambda: user_b

        try:
            other_user = client.get(endpoint)

            assert other_user.status_code in (403, 404), (
                "OWASP A01: un segundo usuario autenticado "
                f"accedio al recurso: HTTP {other_user.status_code}"
            )
        finally:
            app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "owner_uuid,user_uuid,is_active",
    [
        ("owner-a", "owner-b", True),
        (None, "owner-a", True),
        ("owner-a", None, True),
        ("owner-a", "owner-a", False),
    ],
)
def test_authorize_ticket_read_rejects_invalid_access(
    owner_uuid, user_uuid, is_active
):
    from fastapi import HTTPException
    from rfp_approval_auth import authorize_ticket_read

    user = SimpleNamespace(
        uuid=user_uuid,
        is_active=is_active,
    )
    ticket = SimpleNamespace(owner_uuid=owner_uuid)

    with pytest.raises(HTTPException) as exc:
        authorize_ticket_read(user, ticket)

    assert exc.value.status_code == 403


def test_authorize_ticket_read_allows_active_owner():
    from rfp_approval_auth import authorize_ticket_read

    user = SimpleNamespace(
        uuid="owner-a",
        is_active=True,
    )
    ticket = SimpleNamespace(owner_uuid="owner-a")

    assert authorize_ticket_read(user, ticket) is None
