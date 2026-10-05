"""Small, deterministic redaction helpers for logs and incident packets."""

from __future__ import annotations

import re
from typing import Any


SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|token|secret|password|passwd|authorization|cookie|credential)",
    re.IGNORECASE,
)
BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*")
ASSIGNMENT = re.compile(
    r"(?i)\b([A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY))\s*=\s*([^\s]+)"
)


def redact_text(value: str) -> str:
    value = BEARER.sub("Bearer [REDACTED]", value)
    return ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value
