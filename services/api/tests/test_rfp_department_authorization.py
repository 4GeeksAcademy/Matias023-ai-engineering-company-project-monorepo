"""Department authorization tests using synthetic identities."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from rfp_approval_auth import (
    APPROVER_EMAIL_ENV,
    authorize_department_approval,
)
from data.pipelines.rfp_intake.rfp_approval_graph import APPROVERS


@pytest.mark.parametrize("department", ["warehouse", "reverse"])
def test_department_accepts_only_its_own_approver(
    monkeypatch,
    department,
):
    emails = {
        "warehouse": "warehouse@test.invalid",
        "reverse": "reverse@test.invalid",
    }

    for name, email in emails.items():
        monkeypatch.setenv(APPROVER_EMAIL_ENV[name], email)

    user = SimpleNamespace(
        email=emails[department],
        is_active=True,
    )

    assert authorize_department_approval(
        user, department
    ) == APPROVERS[department]

    other = (
        "reverse"
        if department == "warehouse"
        else "warehouse"
    )

    with pytest.raises(HTTPException) as error:
        authorize_department_approval(
            SimpleNamespace(
                email=emails[other],
                is_active=True,
            ),
            department,
        )

    assert error.value.status_code == 403


def test_inactive_approver_is_rejected(monkeypatch):
    monkeypatch.setenv(
        APPROVER_EMAIL_ENV["warehouse"],
        "warehouse@test.invalid",
    )

    with pytest.raises(HTTPException) as error:
        authorize_department_approval(
            SimpleNamespace(
                email="warehouse@test.invalid",
                is_active=False,
            ),
            "warehouse",
        )

    assert error.value.status_code == 403


def test_unconfigured_approver_is_rejected(monkeypatch):
    monkeypatch.delenv(
        APPROVER_EMAIL_ENV["warehouse"],
        raising=False,
    )

    with pytest.raises(HTTPException) as error:
        authorize_department_approval(
            SimpleNamespace(
                email="warehouse@test.invalid",
                is_active=True,
            ),
            "warehouse",
        )

    assert error.value.status_code == 503


def test_unknown_department_is_rejected():
    with pytest.raises(HTTPException) as error:
        authorize_department_approval(
            SimpleNamespace(
                email="anyone@test.invalid",
                is_active=True,
            ),
            "unknown_department",
        )

    assert error.value.status_code == 404
