"""Deterministic checks on a localized line. Flags problems; never rewrites the line.

Khmer often drops pronouns, so a planned pronoun that is absent is fine.
Violations: a forbidden form, a rough form the plan did not allow, or
profanity above the allowed level. Warnings: a pronoun the plan did not
list, a habit-gated form (ញ៉ុំ) the plan did not choose, declared
``pronouns_used`` that do not match the text.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from claynext.models.khmer_localization.lexicon import PronounInventory, load_inventory
from claynext.models.khmer_localization.slang import khmer_intensity


@dataclass
class CheckResult:
    detected: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    profanity_level: int = 0
    profanity_terms: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["ok"] = self.ok
        return out


def check_line(
    text: str,
    plan: dict[str, Any],
    *,
    profanity_max: int | None = None,
    declared: dict[str, list[str]] | None = None,
    inventory: PronounInventory | None = None,
) -> CheckResult:
    inv = inventory or load_inventory()
    res = CheckResult()
    found = [m.form for m in inv.detect(text)]
    res.detected = list(dict.fromkeys(found))
    forbidden = set(plan.get("forbidden") or [])
    first = [plan.get("first_person"), *(plan.get("first_alternatives") or [])]
    second = [plan.get("second_person"), *(plan.get("second_alternatives") or [])]
    allowed = {f for f in first + second if f}
    rough = inv.rough_forms
    allow_rough = bool(plan.get("allow_rough"))
    for form in res.detected:
        if form in forbidden:
            res.violations.append(f"forbidden_pronoun:{form}")
        elif form in rough and form not in allowed and not allow_rough:
            res.violations.append(f"rough_pronoun_unplanned:{form}")
        elif form not in allowed:
            res.warnings.append(f"unplanned_pronoun:{form}")
        if form in inv.habit_gated and form != plan.get("first_person"):
            res.warnings.append(f"habit_gated_form_unplanned:{form}")
    if profanity_max is not None:
        res.profanity_level, res.profanity_terms = khmer_intensity(text)
        if res.profanity_level > profanity_max:
            res.violations.append(f"profanity_above_limit:{res.profanity_level}>{profanity_max}")
    if declared:
        said = {inv.canonical(f) for forms in declared.values() for f in forms or []}
        missing = sorted(f for f in said if f and f not in res.detected)
        if missing:
            res.warnings.append("declared_pronoun_missing:" + ",".join(missing))
    return res
