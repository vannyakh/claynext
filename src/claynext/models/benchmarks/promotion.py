"""Promotion gate. The default decision is not promoted.

Proposed rates are targets. They are applied only when a human review record
actually contains them. Automatic metric structures cannot open this gate.
"""
from __future__ import annotations

from typing import Any

from claynext.models.benchmarks.rubric import (
    DIMENSIONS,
    NATURAL_PASS_MIN,
    item_disagreements,
    reviewer_ids,
    uncertainty,
)

# Targets, not measured results.
PROPOSED_GATES = {
    "meaning": 0.98,
    "natural_khmer": 0.90,
    "pronoun": 0.97,
    "emotion_register": 0.95,
    "terminology": 0.98,
    "structured_output": 0.99,
}


def _resolved_item(item: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    adjudication = item.get("adjudication") or {}
    by_dim: dict[str, list[dict[str, Any]]] = {}
    for score in item.get("scores") or []:
        dim = str(score.get("dimension") or "")
        if dim:
            by_dim.setdefault(dim, []).append(score)
    resolved: dict[str, Any] = {}
    missing: list[str] = []
    for dim in DIMENSIONS:
        if dim in adjudication:
            resolved[dim] = dict(adjudication[dim])
            resolved[dim]["source"] = "adjudication"
            continue
        scores = by_dim.get(dim) or []
        if not scores:
            missing.append(dim)
            continue
        if dim == "natural_khmer":
            ratings = [score.get("rating") for score in scores if score.get("rating") is not None]
            if len(ratings) >= 1 and len(set(ratings)) == 1:
                resolved[dim] = {"rating": ratings[0], "source": "unanimous"}
            else:
                missing.append(dim)
        else:
            passed = [score.get("passed") for score in scores if score.get("passed") is not None]
            if len(passed) >= 1 and len(set(passed)) == 1:
                resolved[dim] = {"passed": passed[0], "source": "unanimous"}
            else:
                missing.append(dim)
    return resolved, missing


def _rates(resolved_items: list[dict[str, Any]]) -> dict[str, float]:
    rates: dict[str, float] = {}
    count = len(resolved_items)
    for dim in DIMENSIONS:
        if dim == "natural_khmer":
            hits = sum(1 for item in resolved_items if int(item[dim]["rating"]) >= NATURAL_PASS_MIN)
        else:
            hits = sum(1 for item in resolved_items if item[dim].get("passed") is True)
        rates[dim] = hits / count
    return rates


def evaluate_promotion(
    reviews: list[dict[str, Any]] | None = None,
    *,
    baseline_improved: bool | None = None,
    critical_semantic_regressions: int | None = None,
    licence_allows_deployment: bool = False,
    cto_approved: bool = False,
    qa_approved: bool = False,
    synthetic_fixture: bool = False,
    candidate_id: str = "",
) -> dict[str, Any]:
    """Return a promotion decision. Missing gates stay closed."""
    decision: dict[str, Any] = {
        "promoted": False,
        "decision": "not_promoted",
        "candidate_id": candidate_id,
        "proposed_gates": dict(PROPOSED_GATES),
        "observed": {},
        "missing": [],
        "reasons": [],
        "uncertainty": uncertainty(reviews),
        "synthetic_fixture": synthetic_fixture,
        "model_evaluated": False,
    }
    reasons: list[str] = decision["reasons"]
    if synthetic_fixture:
        reasons.append("synthetic fixture reviews cannot promote a model")
    if not reviews:
        reasons.append("no human review record")
        return decision
    if len(reviewer_ids(reviews)) < 2:
        reasons.append("fewer than two reviewers")
    missing: list[str] = []
    disagreements: list[str] = []
    resolved_items: list[dict[str, Any]] = []
    for item in reviews:
        disagreements.extend(
            f"{item.get('item_id')}:{dim}" for dim in item_disagreements(item)
        )
        resolved, item_missing = _resolved_item(item)
        if item_missing:
            missing.extend(f"{item.get('item_id')}:{dim}" for dim in item_missing)
            continue
        resolved_items.append(resolved)
    if disagreements:
        reasons.append("unresolved reviewer disagreement")
        decision["missing"].extend(disagreements)
    if missing or len(resolved_items) != len(reviews):
        reasons.append("human gates are incomplete")
        decision["missing"].extend(missing)
    else:
        observed = _rates(resolved_items)
        decision["observed"] = observed
        for dim, target in PROPOSED_GATES.items():
            if observed[dim] < target:
                reasons.append(f"{dim} {observed[dim]:.3f} is below the target {target:.2f}")
    if baseline_improved is not True:
        reasons.append("improvement versus baseline is not recorded")
    if critical_semantic_regressions is None:
        reasons.append("critical semantic regressions were not recorded")
    elif critical_semantic_regressions != 0:
        reasons.append("critical semantic regression")
    if not licence_allows_deployment:
        reasons.append("licence does not allow deployment")
    if not cto_approved:
        reasons.append("CTO approval flag is false")
    if not qa_approved:
        reasons.append("QA approval flag is false")
    if reasons:
        return decision
    decision["promoted"] = True
    decision["decision"] = "promoted"
    return decision
