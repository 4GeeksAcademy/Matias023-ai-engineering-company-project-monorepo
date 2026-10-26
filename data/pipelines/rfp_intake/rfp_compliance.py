"""Deterministic checks for explicit TrackFlow commercial violations."""

import re


def check_commercial_rules(
    draft: str,
    country: str,
) -> list[str]:
    """Return detected violations; empty is not proof of full compliance."""

    if not isinstance(draft, str) or not draft.strip():
        return ["Empty proposal"]

    issues = []
    country_key = country.strip().casefold() if isinstance(country, str) else ""

    if country_key in {"usa", "us", "united states"}:
        expected = "USD"
        forbidden = "EUR"
    elif country_key in {"spain", "españa"}:
        expected = "EUR"
        forbidden = "USD"
    else:
        return ["Unsupported or unconfirmed client country"]

    if re.search(rf"\b{forbidden}\b", draft, re.IGNORECASE):
        issues.append(
            f"Currency mismatch: {forbidden} appears in a {expected} proposal"
        )

    # Only flag explicit promises; avoid mistaking references to the
    # client's original requirements for TrackFlow commitments.
    promise = re.compile(
        r"(?:procesaremos|procesamiento garantizado|"
        r"garantizamos procesar|we guarantee processing|"
        r"we will process)"
        r"[^.\n]{0,100}?"
        r"(\d{1,3})\s*(?:horas|hours|hrs)\b",
        re.IGNORECASE,
    )

    for match in promise.finditer(draft):
        if int(match.group(1)) < 48:
            issues.append(
                "Returns processing commitment below 48 hours"
            )

    lower = draft.casefold()

    # Missing commitments cannot be approved as confirmed compliance.
    sla_pattern = re.compile(
        r"(?:sla|on.time delivery|entregas? a tiempo)"
        r"[^.\n]{0,100}?\b\d{1,3}(?:[.,]\d+)?\s*%",
        re.IGNORECASE,
    )
    if not sla_pattern.search(draft):
        issues.append("On-time delivery SLA percentage missing")

    discount_terms = (
        "descuento por volumen",
        "descuentos por volumen",
        "volume discount",
        "volume-based discount",
    )
    if not any(term in lower for term in discount_terms):
        issues.append("Volume discount table missing or unconfirmed")

    confidential_rates = re.compile(
        r"(?:tarifa negociada|negotiated carrier rate)"
        r"[^.\n]{0,100}?(?:\d+[.,]\d*|USD|EUR|\$|€)",
        re.IGNORECASE,
    )
    if confidential_rates.search(draft):
        issues.append("Potential disclosure of negotiated carrier rates")

    return issues
