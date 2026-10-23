"""Shared shape for benchmark metrics. Unscored metrics keep value null."""
from __future__ import annotations

from typing import Any


def metric(
    name: str,
    *,
    value: float | None = None,
    unit: str | None = None,
    n: int | None = None,
    agreement: float | None = None,
    method: str = "not_scored",
    reason: str = "",
    details: dict[str, Any] | None = None,
    automatic_check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "metric": name,
        "value": value,
        "unit": unit,
        "n": n,
        "agreement": agreement,
        "method": method,
        "reason": reason,
        "details": details or {},
        "automatic_check": automatic_check,
    }


def not_scored(name: str, reason: str) -> dict[str, Any]:
    return metric(name, reason=reason)
