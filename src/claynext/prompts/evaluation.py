"""Offline regression evaluations for skills.

Each JSONL case holds skill inputs, a recorded model reply, and the
expected verdicts. Running a case renders the prompt and checks the reply;
it never calls a model, so results are deterministic.

Case keys: ``id``, ``skill`` (optional spec ``id@^1.0``), ``inputs``,
``output`` (object, array, or raw string), and ``expect`` with any of
``valid``, ``errors_contain``, ``prompt_contains``, ``prompt_excludes``,
``glossary_ok``, ``timing_ok``, ``review_ids``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from claynext.prompts import loader
from claynext.prompts.registry import SkillRegistry, get_registry
from claynext.prompts.translation import (
    CountUnits,
    glossary_misses,
    review_items,
    timing_overflows,
)

TRANSLATION_CASES = loader.EVALUATIONS_DIR / "translation_cases.jsonl"


def run_case(
    case: dict[str, Any],
    *,
    registry: SkillRegistry | None = None,
    count_units: CountUnits | None = None,
) -> dict[str, Any]:
    reg = registry or get_registry()
    sid, _, spec = str(case.get("skill") or "movie.dialogue_translation@^1.0").partition("@")
    skill = reg.get(sid, spec)
    inputs = case["inputs"]
    expect = case.get("expect") or {}
    failures: list[str] = []

    prompt = skill.render(inputs).text
    for needle in expect.get("prompt_contains") or []:
        if needle not in prompt:
            failures.append(f"prompt is missing {needle!r}")
    for needle in expect.get("prompt_excludes") or []:
        if needle in prompt:
            failures.append(f"prompt should not contain {needle!r}")

    res = skill.validate_output(case.get("output"), inputs)
    if "valid" in expect and res.ok != bool(expect["valid"]):
        failures.append(f"valid={res.ok}, expected {expect['valid']}: {res.errors[:3]}")
    joined = " | ".join(res.errors)
    for needle in expect.get("errors_contain") or []:
        if needle not in joined:
            failures.append(f"errors do not mention {needle!r}: {joined[:200]}")

    rows = (res.data or {}).get("translations") or [] if res.ok else []
    metrics: dict[str, Any] = {"valid": res.ok, "errors": res.errors[:5]}
    if res.ok:
        misses = glossary_misses(inputs, rows)
        metrics["glossary_misses"] = misses
        if "glossary_ok" in expect and (not misses) != bool(expect["glossary_ok"]):
            failures.append(f"glossary_ok={not misses}, expected {expect['glossary_ok']}: {misses}")
        if count_units is not None:
            over = timing_overflows(inputs, rows, count_units)
            metrics["timing_overflows"] = over
            if "timing_ok" in expect and (not over) != bool(expect["timing_ok"]):
                failures.append(f"timing_ok={not over}, expected {expect['timing_ok']}: {over}")
        review = sorted(item["id"] for item in review_items(rows))
        metrics["review_ids"] = review
        if "review_ids" in expect and review != sorted(str(x) for x in expect["review_ids"]):
            failures.append(f"review_ids={review}, expected {expect['review_ids']}")

    return {
        "id": case.get("id"),
        "skill": f"{skill.id}@{skill.version}",
        "passed": not failures,
        "failures": failures,
        "metrics": metrics,
    }


def run_suite(
    path: Path = TRANSLATION_CASES,
    *,
    registry: SkillRegistry | None = None,
    count_units: CountUnits | None = None,
) -> dict[str, Any]:
    results = [
        run_case(case, registry=registry, count_units=count_units)
        for case in loader.load_jsonl(path)
    ]
    failed = [r for r in results if not r["passed"]]
    return {
        "suite": path.name,
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": [r["id"] for r in failed],
        "results": results,
    }
