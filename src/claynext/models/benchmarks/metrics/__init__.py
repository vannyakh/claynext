"""Metric structures for the Khmer movie benchmark. Unscored fields stay null."""
from __future__ import annotations

from typing import Any

from claynext.models.benchmarks.metrics.cost import cost_metric
from claynext.models.benchmarks.metrics.human_dims import emotion_metric, meaning_metric, naturalness_metric
from claynext.models.benchmarks.metrics.latency import latency_metric, tokens_per_second
from claynext.models.benchmarks.metrics.pronouns import pronoun_metric
from claynext.models.benchmarks.metrics.structured import schema_validity_metric
from claynext.models.benchmarks.metrics.terminology import terminology_metric
from claynext.models.benchmarks.schema import BenchmarkRow
from claynext.models.llm_gateway.base import Pricing


def collect_metrics(
    rows: list[BenchmarkRow],
    outputs: dict[str, str],
    usages: list[dict[str, Any]],
    *,
    pricing: Pricing | None = None,
    trace_cost: float | None = None,
    glossary: list[dict[str, str]] | None = None,
    schema: dict[str, Any] | None = None,
    pronoun_out_dir=None,
) -> dict[str, Any]:
    samples = [float(row["latency_ms"]) for row in usages if isinstance(row.get("latency_ms"), (int, float))]
    token_rate = None
    if len(usages) == 1:
        token_rate = tokens_per_second(usages[0].get("tokens_out"), usages[0].get("latency_ms"))
    latency = latency_metric(samples)
    latency["tokens_per_second"] = token_rate
    return {
        "meaning": meaning_metric(None),
        "naturalness": naturalness_metric(None),
        "pronoun_accuracy": pronoun_metric(rows, outputs, out_dir=pronoun_out_dir),
        "emotion_register": emotion_metric(None),
        "terminology": terminology_metric(rows, outputs, glossary),
        "structured_output": schema_validity_metric(outputs, schema),
        "latency": latency,
        "cost": cost_metric(usages, pricing=pricing, trace_cost=trace_cost),
    }
