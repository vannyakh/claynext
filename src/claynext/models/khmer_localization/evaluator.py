"""Translation Quality Evaluator for Khmer pronoun / relationship cases.

Each JSONL case describes speaker, listener, relationship, scene, and the
expected pronoun forms (allowed / forbidden / not_auto), plus a reference
line. The evaluator checks, without calling a model:

- resolver: the Pronoun Resolver's choice against the expectations,
- levels: the allowed profanity level never exceeds the expected maximum,
- reference: the reference line passes the post-check,
- outputs (optional): model outputs ``{case_id: localized_text}`` pass it too.

Cases carry ``review.status``. Only ``reviewed`` cases are native-speaker
verified; ``reviewed_only=True`` restricts scoring to them. Agreement on
pending cases measures consistency with draft expectations, not quality.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from claynext.models.khmer_localization.lexicon import PronounInventory, load_inventory
from claynext.models.khmer_localization.postcheck import check_line
from claynext.models.khmer_localization.pronouns import Party, PronounContext, PronounResolver
from claynext.models.khmer_localization.slang import select_levels
from claynext.models.khmer_localization.speech_profile import LocalizationConfig, SpeechProfile
from claynext.prompts import loader

CASES = loader.EVALUATIONS_DIR / "khmer_pronoun_cases.jsonl"
REVIEW_STATUSES = ("pending_native_review", "reviewed", "needs_changes", "rejected")
REQUIRED = (
    "id", "category", "source_language", "source_text", "speaker", "relationship",
    "scene", "register", "emotion", "expected", "reference_khmer", "notes", "review",
)


def validate_case(case: dict[str, Any]) -> list[str]:
    errors = [f"missing {k}" for k in REQUIRED if k not in case]
    review = case.get("review") or {}
    status = review.get("status")
    if status not in REVIEW_STATUSES:
        errors.append(f"review.status {status!r} not in {REVIEW_STATUSES}")
    if status == "reviewed" and not (review.get("reviewer") and review.get("reviewed_at")):
        errors.append("reviewed cases need reviewer and reviewed_at")
    exp = case.get("expected") or {}
    for slot in ("first_person", "second_person"):
        if not isinstance(exp.get(slot), dict):
            errors.append(f"expected.{slot} must be an object")
    return errors


def load_cases(path: Path = CASES, *, reviewed_only: bool = False) -> list[dict[str, Any]]:
    rows = loader.load_jsonl(path)
    if reviewed_only:
        rows = [r for r in rows if (r.get("review") or {}).get("status") == "reviewed"]
    return rows


def _profile(party: dict[str, Any]) -> SpeechProfile | None:
    raw = party.get("profile")
    if not raw:
        return None
    data = {"character_id": party.get("id") or "x", "gender": party.get("gender"), "age_group": party.get("age_group"), **raw}
    return SpeechProfile.from_dict(data)


def _party(row: dict[str, Any] | None) -> Party | None:
    if not row:
        return None
    return Party(str(row.get("id") or ""), gender=str(row.get("gender") or ""),
                 age_group=str(row.get("age_group") or ""), profile=_profile(row))


def case_context(case: dict[str, Any]) -> PronounContext:
    rel = case.get("relationship") or {}
    scene = case.get("scene") or {}
    return PronounContext(
        speaker=_party(case["speaker"]),
        listener=_party(case.get("listener")),
        relation=str(rel.get("relation") or ""),
        relation_source=str(rel.get("source") or ("dataset" if rel.get("relation") else "")),
        relation_confidence=float(rel.get("confidence", 1.0)),
        hostility=int(rel.get("hostility") or 0),
        intimacy=int(rel.get("intimacy") or 0),
        register=str(case.get("register") or "neutral"),
        emotion=str(case.get("emotion") or "neutral"),
        scene_id=str(scene.get("id") or ""),
        scene_formality=str(scene.get("formality") or "neutral"),
    )


def _expected_plan(exp: dict[str, Any], inv: PronounInventory) -> dict[str, Any]:
    first = list((exp.get("first_person") or {}).get("allowed") or [])
    second = list((exp.get("second_person") or {}).get("allowed") or [])
    forbidden = list((exp.get("first_person") or {}).get("forbidden") or []) + list(
        (exp.get("second_person") or {}).get("forbidden") or []
    )
    return {
        "first_person": first[0] if first else "",
        "first_alternatives": first[1:],
        "second_person": second[0] if second else "",
        "second_alternatives": second[1:],
        "forbidden": forbidden,
        "allow_rough": any(f in inv.rough_forms for f in first + second),
    }


def _text_failures(
    text: str,
    plan: dict[str, Any],
    max_prof: int | None,
    inv: PronounInventory,
    third_person: list[str] = (),
) -> tuple[list[str], dict]:
    res = check_line(text, plan, profanity_max=max_prof, inventory=inv)
    allowed = {plan["first_person"], plan["second_person"], *plan["first_alternatives"],
               *plan["second_alternatives"], *third_person}
    fails = list(res.violations)
    fails += [f"unexpected_pronoun:{f}" for f in res.detected if f not in allowed]
    return fails, res.to_dict()


def evaluate_case(
    case: dict[str, Any],
    *,
    resolver: PronounResolver,
    inventory: PronounInventory,
    output_text: str | None = None,
) -> dict[str, Any]:
    exp = case.get("expected") or {}
    failures: dict[str, list[str]] = {"resolver": [], "levels": [], "reference": [], "output": []}
    errors = validate_case(case)
    if errors:
        failures["resolver"].extend(f"case: {e}" for e in errors)
        return {"id": case.get("id"), "passed": False, "failures": failures}

    ctx = case_context(case)
    d = resolver.resolve(ctx)
    for slot, chosen in (("first_person", d.first_person), ("second_person", d.second_person)):
        want = exp.get(slot) or {}
        allowed = want.get("allowed") or []
        if allowed and chosen not in allowed:
            failures["resolver"].append(f"{slot} {chosen} not in allowed {allowed}")
        if chosen in (want.get("forbidden") or []):
            failures["resolver"].append(f"{slot} {chosen} is forbidden")
        if chosen in (want.get("not_auto") or []):
            failures["resolver"].append(f"{slot} {chosen} must not be chosen automatically")
    if exp.get("needs_review") is not None and bool(exp["needs_review"]) != d.needs_review:
        failures["resolver"].append(f"needs_review={d.needs_review}, expected {exp['needs_review']}: {d.review_reasons}")

    project = LocalizationConfig.from_dict(case.get("project") or {})
    levels = select_levels(case["source_text"], ctx.speaker.profile, project)
    max_prof = exp.get("max_profanity_level")
    if max_prof is not None and levels.allowed_profanity > int(max_prof):
        failures["levels"].append(f"allowed profanity {levels.allowed_profanity} > expected max {max_prof}")

    plan = _expected_plan(exp, inventory)
    cap = int(max_prof) if max_prof is not None else levels.allowed_profanity
    third = list(exp.get("third_person_refs") or [])
    ref_fail, ref_check = _text_failures(case["reference_khmer"], plan, cap, inventory, third)
    failures["reference"] = ref_fail
    out_check = None
    if output_text is not None:
        failures["output"], out_check = _text_failures(output_text, plan, cap, inventory, third)

    return {
        "id": case["id"],
        "category": case["category"],
        "review_status": case["review"]["status"],
        "passed": not any(failures.values()),
        "failures": failures,
        "decision": {
            "first_person": d.first_person,
            "second_person": d.second_person,
            "needs_review": d.needs_review,
            "review_reasons": d.review_reasons,
            "confidence": d.confidence,
            "source": d.source,
        },
        "levels": levels.to_dict(),
        "reference_check": ref_check,
        "output_check": out_check,
    }


def run(
    path: Path = CASES,
    *,
    reviewed_only: bool = False,
    outputs: dict[str, str] | None = None,
    force_fallback: bool = False,
) -> dict[str, Any]:
    everything = load_cases(path)
    cases = load_cases(path, reviewed_only=reviewed_only)
    inv = load_inventory(force_fallback=force_fallback)
    resolver = PronounResolver(inv)
    results = [
        evaluate_case(c, resolver=resolver, inventory=inv,
                      output_text=(outputs or {}).get(str(c.get("id"))) if outputs else None)
        for c in cases
    ]

    def _stage(name: str) -> dict[str, Any]:
        bad = [r["id"] for r in results if r["failures"].get(name)]
        return {"passed": len(results) - len(bad), "failed": bad}

    status_counts = Counter((c.get("review") or {}).get("status") for c in everything)
    reviewed = status_counts.get("reviewed", 0)
    report = {
        "suite": path.name,
        "dictionary_version": inv.version,
        "total_cases": len(everything),
        "evaluated": len(results),
        "reviewed_only": reviewed_only,
        "by_review_status": dict(sorted(status_counts.items())),
        "by_category": dict(sorted(Counter(c.get("category") for c in cases).items())),
        "resolver": _stage("resolver"),
        "levels": _stage("levels"),
        "reference": _stage("reference"),
        "resolver_needs_review": sum(1 for r in results if r.get("decision", {}).get("needs_review")),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": [r["id"] for r in results if not r["passed"]],
        "note": (
            "No case is native-speaker reviewed yet; results measure consistency with draft expectations only."
            if reviewed == 0 else f"{reviewed} case(s) are native-speaker reviewed."
        ),
        "results": results,
    }
    if outputs is not None:
        report["outputs"] = _stage("output")
        report["outputs"]["missing"] = [str(c["id"]) for c in cases if str(c["id"]) not in outputs]
    return report


if __name__ == "__main__":
    import json
    import sys

    rep = run(reviewed_only="--reviewed-only" in sys.argv)
    rep.pop("results")
    print(json.dumps(rep, ensure_ascii=False, indent=2))
