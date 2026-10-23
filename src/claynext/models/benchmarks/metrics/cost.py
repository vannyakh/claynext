"""Cost from a provider trace or a caller-supplied price config. No built-in price list."""
from __future__ import annotations

from typing import Any

from claynext.models.benchmarks.metrics.common import metric
from claynext.models.llm_gateway.base import Pricing


def cost_metric(
    usages: list[dict[str, Any]],
    *,
    pricing: Pricing | None = None,
    trace_cost: float | None = None,
) -> dict[str, Any]:
    if trace_cost is not None:
        return metric(
            "cost",
            value=float(trace_cost),
            unit="usd",
            n=len(usages) or None,
            method="provider_trace",
            reason="cost already recorded on the provider trace",
        )
    if pricing is None:
        return metric(
            "cost",
            unit="usd",
            reason="no user-supplied price config and no provider-trace cost",
        )
    complete = [
        row for row in usages
        if row.get("tokens_in") is not None and row.get("tokens_out") is not None
    ]
    if not usages or len(complete) != len(usages):
        return metric(
            "cost",
            unit="usd",
            method="user_supplied_pricing",
            reason="price config is present but token counts are incomplete; cost left unset",
        )
    total = sum(pricing.cost(int(row["tokens_in"]), int(row["tokens_out"])) for row in complete)
    return metric(
        "cost",
        value=total,
        unit="usd",
        n=len(complete),
        method="user_supplied_pricing",
        reason="computed from the caller-supplied price config",
    )
