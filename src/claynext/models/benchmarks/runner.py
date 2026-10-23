"""Provider-neutral benchmark runner.

Wraps ``run_evaluation`` for the pronoun post-check. Translation uses one
callable, a gateway provider, or a local model adapter. Reports record the
prompt version and decoding config. They do not contain a quality score unless
a later human review says so, and this runner never invents one.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from claynext.models.benchmarks.leaderboard import leaderboard
from claynext.models.benchmarks.leakage import assert_no_leakage
from claynext.models.benchmarks.metrics import collect_metrics
from claynext.models.benchmarks.promotion import evaluate_promotion
from claynext.models.benchmarks.prompt import (
    PROMPT_VERSION,
    contains_model_id,
    judge_prompt,
    template_sha256,
    translation_prompt,
)
from claynext.models.benchmarks.providers import coerce_output, redact_provider_error
from claynext.models.benchmarks.rubric import empty_uncertainty
from claynext.models.benchmarks.schema import (
    SCHEMA_VERSION,
    BenchmarkRow,
    GoldSetError,
    SplitLockError,
    assert_not_synthetic_gold,
)
from claynext.models.llm_gateway.base import Pricing

Translator = Callable[[BenchmarkRow], Any]
PROBE_ROW_CAP = 20


def decoding_config(
    *,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    top_p: float | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    return {
        "prompt_version": PROMPT_VERSION,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
        "seed": seed,
    }


def run_benchmark(
    rows: list[BenchmarkRow],
    translate: Translator,
    *,
    train_rows: list[BenchmarkRow] | None = None,
    model_id: str = "",
    provider_label: str = "callable",
    dataset_version: str = "",
    decoding: dict[str, Any] | None = None,
    pricing: Pricing | None = None,
    trace_cost: float | None = None,
    glossary: list[dict[str, str]] | None = None,
    output_schema: dict[str, Any] | None = None,
    gold_benchmark: bool = False,
    synthetic_fixture: bool = False,
    judge: Callable[[str], str] | None = None,
    out_dir: str | Path | None = None,
    hosted_probe: bool = False,
) -> dict[str, Any]:
    """Score rows with a fake or live translator. Refuses family leakage and synthetic gold."""
    if hosted_probe and len(rows) > PROBE_ROW_CAP:
        raise ValueError(f"hosted probe cap is {PROBE_ROW_CAP} rows")
    if not rows:
        raise ValueError("no rows to score")
    versions = {row.dataset_version for row in rows}
    if len(versions) != 1:
        raise ValueError("rows must share one dataset version")
    version = dataset_version or next(iter(versions))
    if dataset_version and dataset_version != next(iter(versions)):
        raise ValueError("dataset_version does not match the rows")
    assert_no_leakage(rows, train_rows)
    for row in rows:
        if row.split != "test" or not row.locked:
            raise SplitLockError(f"{row.id} must be a locked test row")
        if row.review_status == "gold":
            assert_not_synthetic_gold(row)
    if gold_benchmark and any(not row.is_gold_reference() for row in rows):
        raise GoldSetError("refusing gold benchmark: a row is not human-reviewed gold")
    for row in rows:
        prompt = translation_prompt(row)
        if contains_model_id(prompt, model_id):
            raise ValueError("translation prompt contains the model id")

    decode = dict(decoding or decoding_config())
    outputs: dict[str, str] = {}
    usages: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    judge_raw: list[dict[str, str]] = []
    for row in rows:
        produced = coerce_output(translate(row))
        outputs[row.id] = produced["text"]
        usages.append(produced)
        raw_rows.append({
            "id": row.id,
            "dialogue_family_id": row.dialogue_family_id,
            "text": produced["text"],
            "trace_id": produced.get("trace_id") or "",
            "latency_ms": produced.get("latency_ms"),
        })
        if judge is not None:
            blinded = judge_prompt(
                source_text=row.source_text,
                reference_khmer=row.reference_khmer,
                hypothesis=produced["text"],
            )
            if contains_model_id(blinded, model_id):
                raise ValueError("judge prompt contains the model id")
            judge_raw.append({"id": row.id, "text": judge(blinded), "used_as_score": False})

    folder = Path(out_dir) if out_dir else None
    pronoun_dir = folder / "evaluation-runner" if folder else None
    metrics = collect_metrics(
        rows,
        outputs,
        usages,
        pricing=pricing,
        trace_cost=trace_cost,
        glossary=glossary,
        schema=output_schema,
        pronoun_out_dir=pronoun_dir,
    )
    gold = all(row.is_gold_reference() for row in rows)
    promotion = evaluate_promotion(None, synthetic_fixture=synthetic_fixture, candidate_id=model_id)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "synthetic_fixture": synthetic_fixture,
        "not_a_gold_benchmark": not gold,
        "quality_score": None,
        "dataset_version": version,
        "prompt_version": PROMPT_VERSION,
        "prompt_template_sha256": template_sha256(),
        "prompt_includes_model_id": False,
        "decoding": decode,
        "provider_label": provider_label,
        "model_id": model_id,
        "split": "test",
        "n_rows": len(rows),
        "leakage_check": {"ok": True, "families": []},
        "metrics": metrics,
        "uncertainty": empty_uncertainty(),
        "promotion": promotion,
        "leaderboard": leaderboard([{
            "candidate_id": model_id or provider_label,
            "promotion": promotion,
        }]),
        "judge_raw": judge_raw,
        "outputs": raw_rows,
        "cost_usd": metrics["cost"]["value"],
    }
    if folder is not None:
        folder.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{version}__{provider_label}__{PROMPT_VERSION}")
        path = folder / f"{safe}.json"
        path.write_text(_dumps(report), encoding="utf-8")
        report["path"] = str(path)
    return report


def _dumps(report: dict[str, Any]) -> str:
    return redact_provider_error(json.dumps(report, ensure_ascii=False, indent=2))
