"""Comparison report for untuned, prompted, LoRA/QLoRA, DPO, and hosted systems.

Metric fields stay null until a measurement is supplied. Quality stays null
when the references are not native-reviewed. The report does not promote a
model and does not rank one system above another.
"""
from __future__ import annotations

import json
from typing import Any

from claynext.models.benchmarks.leaderboard import leaderboard
from claynext.models.benchmarks.metrics.cost import cost_metric
from claynext.models.benchmarks.promotion import evaluate_promotion
from claynext.models.benchmarks.prompt import (
    JUDGE_PROMPT_VERSION,
    contains_model_id,
    judge_prompt,
)
from claynext.models.llm_gateway.base import Pricing

# Role, kind, present by default. DPO is absent until preference pairs exist.
_ROLES = (
    ("A", "untuned", True),
    ("B", "prompted_baseline", True),
    ("C", "lora_qlora", True),
    ("D", "dpo", False),
    ("E", "hosted", True),
)

_SLOT_LEGEND = {
    "A": "untuned",
    "B": "prompted baseline",
    "C": "LoRA/QLoRA",
    "D": "DPO if preference pairs exist",
    "E": "hosted GPT/Gemini",
}


def _synthetic_reference(origin: str, native_reviewed: bool) -> bool:
    label = (origin or "").strip().lower()
    if label in {"synthetic", "gemini_teacher", "synthetic/gemini_teacher"}:
        return True
    if "synthetic" in label or "gemini_teacher" in label:
        return True
    return not native_reviewed


def _claims_win(payload: dict[str, Any]) -> bool:
    if payload.get("winner") or payload.get("beats_gpt") or payload.get("beats"):
        return True
    blob = json.dumps(payload, ensure_ascii=False).lower()
    return "beats gpt" in blob or "beat gpt" in blob


def build_comparison_judge_prompt(
    *,
    source_text: str,
    reference_khmer: str,
    hypothesis: str,
    model_ids: list[str],
) -> str:
    """Blind judge text. Raises when a model name would be included."""
    text = judge_prompt(
        source_text=source_text,
        reference_khmer=reference_khmer,
        hypothesis=hypothesis,
    )
    for model_id in model_ids:
        if contains_model_id(text, model_id):
            raise ValueError("judge prompt contains the model name")
    return text


def _measured_number(measured: dict[str, Any], key: str) -> float | None:
    value = measured.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def comparison_report(
    *,
    native_reviewed: bool = False,
    reference_origin: str = "gemini_teacher",
    dpo_present: bool = False,
    model_ids: list[str] | None = None,
    pricing: Pricing | None = None,
    measurements: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Shape a five-slot comparison. Default metrics are null. Nothing is promoted."""
    supplied = measurements or {}
    for payload in supplied.values():
        if _claims_win(payload):
            raise ValueError("comparison report cannot claim a model beat a hosted system")

    synthetic = _synthetic_reference(reference_origin, native_reviewed)
    not_gold = (not native_reviewed) or synthetic
    allow_quality = native_reviewed and not synthetic
    promotion = evaluate_promotion(
        None,
        synthetic_fixture=synthetic or not_gold,
        candidate_id="",
    )
    prompt = build_comparison_judge_prompt(
        source_text="Go home.",
        reference_khmer="ទៅផ្ទះហើយ",
        hypothesis="ទៅផ្ទះ",
        model_ids=list(model_ids or []),
    )
    models: list[dict[str, Any]] = []
    for role, kind, default_present in _ROLES:
        present = bool(dpo_present) if role == "D" else default_present
        measured = dict(supplied.get(role) or {})
        usages: list[dict[str, Any]] = []
        if measured.get("tokens_in") is not None or measured.get("tokens_out") is not None:
            usages = [{
                "tokens_in": measured.get("tokens_in"),
                "tokens_out": measured.get("tokens_out"),
            }]
        trace_cost = measured.get("trace_cost") if "trace_cost" in measured else None
        cost = cost_metric(usages, pricing=pricing, trace_cost=trace_cost)
        quality = _measured_number(measured, "quality") if allow_quality else None
        regression = measured.get("regression_risk") if allow_quality else None
        if regression is not None and not isinstance(regression, str):
            regression = None
        models.append({
            "role": role,
            "kind": kind,
            "label": _SLOT_LEGEND[role],
            "present": present,
            "blocked_reason": (
                "" if present or role != "D"
                else "DPO is blocked until human preference pairs exist"
            ),
            "quality": quality,
            "latency_ms": _measured_number(measured, "latency_ms"),
            "vram_gb": _measured_number(measured, "vram_gb"),
            "cost_usd": cost["value"],
            "cost": cost,
            "regression_risk": regression,
            "promotion": "not_promoted",
        })

    report: dict[str, Any] = {
        "schema": "model-comparison-1",
        "slot_legend": dict(_SLOT_LEGEND),
        "not_a_gold_benchmark": not_gold,
        "synthetic_reference": synthetic,
        "native_reviewed": bool(native_reviewed) and not synthetic,
        "promotion": promotion,
        "winner": None,
        "quality_score": None,
        "leaderboard": leaderboard([
            {"candidate_id": slot["role"], "promotion": promotion}
            for slot in models
        ]),
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "judge_prompt_includes_model_name": False,
        "judge_prompt": prompt,
        "models": models,
        "hosted_slot_note": (
            "Slot E stays unscored until a native-reviewed gold set exists. "
            "A capped probe is not a promotion."
        ),
        "cost_policy": "caller-supplied price or provider trace; no built-in price list",
    }
    return report
