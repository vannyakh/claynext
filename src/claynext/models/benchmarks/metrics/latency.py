"""Latency from measured samples only."""
from __future__ import annotations

from typing import Any

from claynext.models.benchmarks.metrics.common import metric


def latency_metric(samples_ms: list[float]) -> dict[str, Any]:
    if not samples_ms:
        return metric("latency", unit="ms", reason="no measured latency on the translator result")
    mean = sum(samples_ms) / len(samples_ms)
    return metric(
        "latency",
        value=mean,
        unit="ms",
        n=len(samples_ms),
        method="measured",
        reason="mean of measured latencies; not a quality score",
        details={"samples_ms": list(samples_ms)},
    )


def tokens_per_second(tokens_out: int | None, latency_ms: float | None) -> float | None:
    if not tokens_out or not latency_ms or latency_ms <= 0:
        return None
    return tokens_out / (latency_ms / 1000.0)
