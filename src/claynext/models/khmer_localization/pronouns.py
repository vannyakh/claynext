"""Khmer Pronoun Resolver: deterministic first / second person choice from relationship data.

Order of authority, highest first:

1. per-scene override (``LocalizationConfig.scene_overrides``),
2. character override for this listener (``SpeechProfile.pronoun_overrides``),
3. relationship rule from ``pronouns.yaml`` (+ matching variants, register,
   and the speaker's own habits when the rule allows that form),
4. age fallback when the relationship is unknown (always reviewed),
5. defaults (ខ្ញុំ / អ្នក).

Habit-gated forms (ញ៉ុំ) are chosen only from the character's own habit and
never in a formal register. Rough forms (អញ / ឯង / ហ្អែង) are chosen only when
the rule allows them (close peers, parent to child, open hostility); anger
alone does not allow them. Otherwise the decision is flagged for review.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from claynext.models.khmer_localization.lexicon import PronounInventory, load_inventory
from claynext.models.khmer_localization.speech_profile import (
    LocalizationConfig,
    SpeechProfile,
    age_relation,
    normalize_age_group,
    normalize_gender,
)

ANGRY = {"angry", "furious", "rage", "resentful", "annoyed", "shouting"}
_FLIP = {"older": "younger", "younger": "older", "peer": "peer", "unknown": "unknown"}


@dataclass
class Party:
    id: str
    gender: str = "unknown"
    age_group: str = "unknown"
    profile: SpeechProfile | None = None

    def __post_init__(self) -> None:
        if self.profile is not None:
            if self.gender in ("", "unknown"):
                self.gender = self.profile.gender
            if self.age_group in ("", "unknown"):
                self.age_group = self.profile.age_group
        self.gender = normalize_gender(self.gender)
        self.age_group = normalize_age_group(self.age_group)


@dataclass
class PronounContext:
    speaker: Party
    listener: Party | None = None
    relation: str = ""
    relation_source: str = ""
    relation_confidence: float = 1.0
    hostility: int = 0
    intimacy: int = 0
    register: str = "neutral"
    emotion: str = "neutral"
    scene_id: str = ""
    scene_formality: str = "neutral"
    listener_inferred: bool = False

    @property
    def formal(self) -> bool:
        return self.register == "formal" or self.scene_formality == "formal"


@dataclass
class PronounDecision:
    first_person: str
    second_person: str
    first_alternatives: list[str] = field(default_factory=list)
    second_alternatives: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    allow_rough: bool = False
    relation: str = ""
    source: str = "default"
    confidence: float = 0.0
    needs_review: bool = False
    reasons: list[str] = field(default_factory=list)
    review_reasons: list[str] = field(default_factory=list)
    dictionary_version: str = ""

    @property
    def allowed_first(self) -> list[str]:
        return _uniq([self.first_person, *self.first_alternatives])

    @property
    def allowed_second(self) -> list[str]:
        return _uniq([self.second_person, *self.second_alternatives])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def plan(self) -> dict[str, Any]:
        """Compact constraint block for the skill prompt."""
        return {
            "first_person": self.first_person,
            "second_person": self.second_person,
            "first_alternatives": list(self.first_alternatives),
            "second_alternatives": list(self.second_alternatives),
            "forbidden": list(self.forbidden),
            "allow_rough": self.allow_rough,
            "relation": self.relation or "unknown",
            "confidence": round(self.confidence, 3),
            "needs_review": self.needs_review,
        }


def _uniq(items) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def _pick(slot: Any, keys: list[str]) -> tuple[list[str], str]:
    if slot is None:
        return [], ""
    if isinstance(slot, list):
        return [str(x) for x in slot], "list"
    for key in keys:
        if key and slot.get(key):
            return [str(x) for x in slot[key]], key
    return [str(x) for x in slot.get("default") or []], "default"


def _matches(when: dict[str, Any], ctx: PronounContext, age: str, profile: SpeechProfile | None) -> bool:
    for key, want in (when or {}).items():
        if key == "register" and ctx.register not in want:
            return False
        if key == "emotion" and ctx.emotion not in want:
            return False
        if key == "hostility_min" and ctx.hostility < int(want):
            return False
        if key == "age" and age not in want:
            return False
        if key == "listener_age" and (ctx.listener is None or ctx.listener.age_group not in want):
            return False
        if key == "scene_formality" and ctx.scene_formality not in want:
            return False
        if key == "slang_min" and (profile is None or profile.slang_level < int(want)):
            return False
    return True


class PronounResolver:
    def __init__(
        self,
        inventory: PronounInventory | None = None,
        config: LocalizationConfig | None = None,
    ):
        self.inv = inventory or load_inventory()
        self.config = config or LocalizationConfig()
        data = self.inv.data
        self.defaults = dict(data.get("defaults") or {})
        self.review_confidence = float(
            self.config.review_confidence if config else data.get("review_confidence") or 0.6
        )

    def resolve(self, ctx: PronounContext) -> PronounDecision:
        d = self._base(ctx)
        self._apply_overrides(ctx, d)
        d.first_alternatives = [f for f in _uniq(d.first_alternatives) if f != d.first_person and f not in d.forbidden]
        d.second_alternatives = [f for f in _uniq(d.second_alternatives) if f != d.second_person and f not in d.forbidden]
        d.forbidden = [f for f in _uniq(d.forbidden) if f not in (d.first_person, d.second_person)]
        d.confidence = round(max(0.0, min(1.0, d.confidence)), 3)
        if d.confidence < self.review_confidence and "confidence below review threshold" not in d.review_reasons:
            d.review_reasons.append("confidence below review threshold")
        d.review_reasons = _uniq(d.review_reasons)
        d.needs_review = bool(d.review_reasons)
        d.dictionary_version = self.inv.version
        return d

    # ── rule path ───────────────────────────────────────────────────────
    def _base(self, ctx: PronounContext) -> PronounDecision:
        speaker, listener = ctx.speaker, ctx.listener
        profile = speaker.profile
        age = age_relation(speaker.age_group, listener.age_group) if listener else "unknown"
        key, rule = self.inv.relation(ctx.relation) if ctx.relation else ("", None)
        d = PronounDecision(first_person="", second_person="", relation=key if rule else "")
        if listener is None:
            d.review_reasons.append("listener unknown")
        elif ctx.listener_inferred:
            d.review_reasons.append("listener inferred from turn order")

        if rule is None:
            if ctx.relation:
                d.reasons.append(f"relation {ctx.relation!r} not in dictionary")
            fb = (self.inv.data.get("age_fallback") or {}).get(age) or {}
            rule = {"first": fb.get("first"), "second": fb.get("second"), "second_alt": fb.get("second_alt")}
            d.source = "age_fallback"
            d.confidence = float(self.defaults.get("confidence") or 0.4)
            d.review_reasons.append("relationship unknown")
            d.reasons.append(f"age fallback ({age})")
        else:
            d.source = "relation_rule"
            d.confidence = float(rule.get("confidence") or 0.6) * float(ctx.relation_confidence or 0.0)
            d.reasons.append(f"rule {key}")
            if ctx.relation_source == "heuristic":
                d.review_reasons.append("relationship inferred from a vocative cue")

        s_gender = speaker.gender if speaker.gender != "unknown" else ""
        l_gender = listener.gender if listener and listener.gender != "unknown" else ""
        prefer = str(rule.get("prefer") or "age")
        s_age = age if age != "unknown" else ""
        l_age = _FLIP[age] if age != "unknown" else ""
        if rule.get("reciprocal") and (not s_gender or not l_gender or s_gender == l_gender):
            first_keys, second_keys = [s_age], [l_age]
            if not s_age:
                d.review_reasons.append("couple of same or unknown gender with unknown ages: បង / អូន direction unclear")
        elif prefer == "gender":
            first_keys, second_keys = [s_gender, s_age], [l_gender, l_age]
        else:
            first_keys, second_keys = [s_age, s_gender], [l_age, l_gender]

        first, _ = _pick(rule.get("first"), first_keys)
        second, _ = _pick(rule.get("second"), second_keys)
        first_alt, _ = _pick(rule.get("first_alt"), first_keys)
        second_alt, _ = _pick(rule.get("second_alt"), second_keys)
        d.forbidden = [str(x) for x in rule.get("forbidden") or []]
        d.allow_rough = bool(rule.get("allow_rough"))

        for variant in rule.get("variants") or []:
            if not _matches(variant.get("when") or {}, ctx, age, profile):
                continue
            if "first" in variant:
                first = _pick(variant["first"], first_keys)[0]
            if "second" in variant:
                second = _pick(variant["second"], second_keys)[0]
            first_alt += _pick(variant.get("first_alt"), first_keys)[0]
            second_alt += _pick(variant.get("second_alt"), second_keys)[0]
            if "allow_rough" in variant:
                d.allow_rough = bool(variant["allow_rough"])
            if "confidence" in variant:
                d.confidence = float(variant["confidence"]) * float(ctx.relation_confidence or 0.0)
            if variant.get("review"):
                d.review_reasons.append(str(variant["review"]))
            d.reasons.append(f"variant {variant.get('when')}")

        if ctx.formal and not rule.get("register_locked"):
            formal_second = _pick(self.inv.data.get("formal_second"), [l_gender])[0]
            if formal_second and second and second[0] not in formal_second:
                second_alt = second + second_alt
                second = formal_second
                d.reasons.append("formal register: polite second person")
            first_alt += _pick(self.inv.data.get("formal_first_alt"), [s_gender])[0]
        if ctx.register == "street" and rule.get("respect"):
            d.review_reasons.append("street register toward a respected listener")

        first = first or [str(self.defaults.get("first") or "ខ្ញុំ")]
        second = second or [str(self.defaults.get("second") or "អ្នក")]
        gated = self.inv.habit_gated
        first = [f for f in first if f not in gated] + [f for f in first if f in gated]
        d.first_person, d.second_person = first[0], second[0]
        d.first_alternatives = first[1:] + first_alt
        d.second_alternatives = second[1:] + second_alt

        self._apply_habits(ctx, d, profile)

        rough = self.inv.rough_forms
        if ctx.emotion in ANGRY and not d.allow_rough:
            d.reasons.append("anger alone does not allow rough pronouns")
        for slot in ("first_person", "second_person"):
            form = getattr(d, slot)
            if form in rough and not d.allow_rough:
                d.review_reasons.append(f"rough form {form} between a non-hostile, non-intimate pair")
        return d

    def _apply_habits(self, ctx: PronounContext, d: PronounDecision, profile: SpeechProfile | None) -> None:
        if profile is None:
            return
        rough, gated = self.inv.rough_forms, self.inv.habit_gated
        for slot, habits in (("first", profile.habitual_first_person), ("second", profile.habitual_second_person)):
            current = getattr(d, f"{slot}_person")
            allowed = [current, *getattr(d, f"{slot}_alternatives")]
            for raw in habits or []:
                form = self.inv.canonical(raw)
                if form in d.forbidden:
                    d.reasons.append(f"habit {form} is forbidden for {d.relation or 'this pair'}")
                    if form in rough:
                        d.review_reasons.append(f"character habitually uses {form}; not allowed toward this listener")
                    continue
                if form in gated and ctx.formal:
                    d.review_reasons.append(f"habit {form} conflicts with a formal scene; kept {current}")
                    continue
                if form not in allowed:
                    d.reasons.append(f"habit {form} not suitable for {d.relation or 'unknown relation'}")
                    if form in rough:
                        d.review_reasons.append(f"character habitually uses {form}; not allowed toward this listener")
                    continue
                if form != current:
                    setattr(d, f"{slot}_alternatives", [current, *getattr(d, f"{slot}_alternatives")])
                    setattr(d, f"{slot}_person", form)
                    d.reasons.append(f"character habit {form}")
                    d.confidence = max(d.confidence, min(0.9, profile.confidence or 0.7))
                break

    def _apply_overrides(self, ctx: PronounContext, d: PronounDecision) -> None:
        listener_id = ctx.listener.id if ctx.listener else "*"
        layers = []
        if ctx.speaker.profile is not None:
            layers.append(("character_override", ctx.speaker.profile.overrides_for(listener_id), 0.95))
        layers.append((
            "scene_override",
            self.config.scene_override(ctx.scene_id, ctx.speaker.id, listener_id),
            1.0,
        ))
        for source, row, conf in layers:
            if not row:
                continue
            changed = []
            for slot in ("first", "second"):
                form = str(row.get(slot) or "")
                if not form:
                    continue
                old = getattr(d, f"{slot}_person")
                if old and old != form:
                    setattr(d, f"{slot}_alternatives", [old, *getattr(d, f"{slot}_alternatives")])
                setattr(d, f"{slot}_person", form)
                changed.append(slot)
            if not changed:
                continue
            d.source = source
            d.confidence = conf
            d.reasons.append(f"{source} sets {', '.join(changed)}" + (f" ({row['note']})" if row.get("note") else ""))
            if set(changed) == {"first", "second"}:
                d.review_reasons = []
            else:
                d.review_reasons = [r for r in d.review_reasons if "confidence" not in r]
