"""Deterministic arbitration of structured RFP conflicts."""

from typing import Any


TRIGGERS = (
    "volume-vs-capacity",
    "returns-sla-breach",
    "currency-mismatch",
)

CURRENCY_BY_COUNTRY = {
    "us": "USD",
    "usa": "USD",
    "united states": "USD",
    "estados unidos": "USD",
    "spain": "EUR",
    "españa": "EUR",
}


def arbitrate(
    client_country: str,
    sections: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return conflict decisions; never silently invent or rewrite values."""

    conflicts = []

    country = (client_country or "").strip().casefold()
    expected_currency = CURRENCY_BY_COUNTRY.get(country)

    if expected_currency:
        offenders = [
            department
            for department, section in sections.items()
            if section.get("currency") is not None
            and section["currency"] != expected_currency
        ]

        if offenders:
            conflicts.append({
                "trigger_id": "currency-mismatch",
                "arbiter": "Miguel Torres",
                "departments": sorted(offenders),
                "decision": "request_changes",
                "expected_currency": expected_currency,
            })

    warehouse = sections.get("warehouse", {})
    lastmile = sections.get("lastmile", {})

    capacity = warehouse.get("monthly_capacity")
    volume = lastmile.get("monthly_volume")

    if (
        type(capacity) in (int, float)
        and type(volume) in (int, float)
        and capacity >= 0
        and volume > capacity
    ):
        conflicts.append({
            "trigger_id": "volume-vs-capacity",
            "arbiter": "Miguel Torres",
            "departments": ["warehouse", "lastmile"],
            "decision": "request_changes",
            "maximum_supported_volume": capacity,
        })

    for department, section in sections.items():
        turnaround = section.get("returns_turnaround_hours")

        if (
            type(turnaround) in (int, float)
            and turnaround < 48
        ):
            conflicts.append({
                "trigger_id": "returns-sla-breach",
                "arbiter": (
                    "Sofía Ramos"
                    if department == "reverse"
                    else "Miguel Torres"
                ),
                "departments": [department],
                "decision": "request_changes",
                "minimum_hours": 48,
            })

    return conflicts
