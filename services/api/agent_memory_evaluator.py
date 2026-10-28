"""Evaluación conservadora de posibles recuerdos del agente."""

import re


SENSITIVE_PATTERNS = (
    r"\b(?:password|contraseña|passwd|secret|token|api[_ -]?key)\b",
    r"\b(?:bearer)\s+\S+",
    r"\b(?:sk-[A-Za-z0-9_-]{12,})\b",
)

PREFERENCE_PATTERNS = (
    r"^(?:prefiero|yo prefiero)\s+(.+)$",
    r"^(?:me gusta que)\s+(.+)$",
    r"^(?:quiero que siempre)\s+(.+)$",
)


def contains_sensitive_memory(content: str) -> bool:
    """Detecta patrones sensibles conocidos; no es un DLP completo."""
    if not isinstance(content, str):
        return True
    return any(
        re.search(pattern, content, re.IGNORECASE)
        for pattern in SENSITIVE_PATTERNS
    )


def evaluate_memory_candidate(message: str) -> dict | None:
    """Propone, pero nunca persiste un recuerdo."""
    if not isinstance(message, str):
        return None

    content = message.strip()

    if not content or len(content) > 500:
        return None

    if any(
        re.search(pattern, content, re.IGNORECASE)
        for pattern in SENSITIVE_PATTERNS
    ):
        return None

    for pattern in PREFERENCE_PATTERNS:
        match = re.fullmatch(
            pattern,
            content,
            flags=re.IGNORECASE,
        )
        if match:
            preference = match.group(1).strip(" .")

            if len(preference) < 4:
                return None

            return {
                "category": "preference",
                "content": f"El usuario prefiere {preference}.",
                "requires_confirmation": True,
            }

    return None
