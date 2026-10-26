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

    return issues
