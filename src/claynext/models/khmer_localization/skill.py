"""``movie.khmer_natural_dialogue`` session for the movie translate path.

Same interface as ``TranslationSkillSession`` (render / check / rows /
record / save), so ``TranslateEngine._skill_batch`` drives it unchanged.
Before rendering, every line gets a pronoun plan (Khmer Pronoun Resolver)
and style limits (Slang and Profanity Selector). After the model replies,
the post-check verifies each line and the session records the three text
fields, candidates, decisions, confidence, and review reasons.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from claynext.models.khmer_localization import contracts as _contracts  # noqa: F401  (registers contracts)
from claynext.models.khmer_localization.lexicon import PronounInventory, load_inventory
from claynext.models.khmer_localization.naturalizer import line_constraints
from claynext.models.khmer_localization.postcheck import check_line
from claynext.models.khmer_localization.pronouns import Party, PronounContext, PronounDecision, PronounResolver
from claynext.models.khmer_localization.relationships import analyze_line
from claynext.models.khmer_localization.slang import LevelDecision, select_levels
from claynext.models.khmer_localization.speech_profile import LocalizationStore, character_key, normalize_gender
from claynext.models.khmer_localization.tts_normalizer import tts_field
from claynext.prompts import loader
from claynext.prompts.registry import Skill, get_registry
from claynext.prompts.translation import CountUnits, TranslationSkillSession, default_runs_dir
from claynext.prompts.validator import ValidationResult

SKILL_ID = "movie.khmer_natural_dialogue"
SKILL_SPEC = "^0.1"
SETTING_KEY = "skill_khmer_natural_dialogue"
REVIEW_CONFIDENCE = 0.6
_KEEP_LINES = 2000


def is_khmer(target_lang: str) -> bool:
    lang = loader.load_language(target_lang or "")
    return bool(lang and lang["id"] == "khmer")


def _source_marker_language(source_lang: str) -> str:
    low = (source_lang or "").strip().lower()
    return "english" if low in ("", "auto", "auto detect") or low.startswith("english") else low


class KhmerDialogueSession(TranslationSkillSession):
    def __init__(
        self,
        skill: Skill,
        *,
        segments: list[dict[str, Any]],
        source_lang: str,
        target_lang: str,
        glossary: Iterable[dict[str, Any]] = (),
        run_dir: str | Path | None = None,
        count_units: CountUnits | None = None,
        store: LocalizationStore | None = None,
        characters: Iterable[dict[str, Any]] = (),
        inventory: PronounInventory | None = None,
        provider: Any = None,
    ):
        super().__init__(
            skill, segments=segments, source_lang=source_lang, target_lang=target_lang,
            glossary=glossary, run_dir=run_dir, count_units=count_units,
        )
        if not run_dir:
            self.path = default_runs_dir() / f"{self.project_key}.{skill.id}.json"
        self.inventory = inventory or load_inventory(force_fallback=skill.force_fallback)
        self.store = store if store is not None else LocalizationStore.for_project(self.project_key, run_dir)
        self.store.seed_from_characters(characters)
        self.store.seed_from_segments(segments)
        self.resolver = PronounResolver(self.inventory, self.store.config)
        self.provider = provider
        self._plans: dict[str, tuple[PronounDecision, LevelDecision, dict[str, Any]]] = {}
        self._lines: dict[str, dict[str, Any]] = {}

    def translate_chunk(self, prompt: str, *, temperature: float = 0.3) -> dict[str, Any]:
        """One skill prompt through the attached gateway. The trace id is kept on the run."""
        from claynext.models.llm_chat import chat_through

        if self.provider is None:
            raise RuntimeError("Khmer gateway is not attached")
        text = chat_through(self.provider, prompt, temperature=temperature)
        from claynext.models.llm_chat import last_chat

        response = last_chat()
        trace_id = response.trace_id if response is not None else ""
        model = response.model if response is not None else ""
        return {"text": text, "trace_id": trace_id, "model": model, "temperature": temperature}

    # ── planning ────────────────────────────────────────────────────────
    def _listener(self, seg: dict[str, Any]) -> tuple[str, bool]:
        explicit = str(seg.get("listener_id") or seg.get("listener") or "").strip()
        if explicit:
            return explicit, False
        me = character_key(seg)
        key = str(seg.get("id"))
        if key not in self._order:
            return "", False
        idx = self._order.index(key)
        for j in (idx - 1, idx + 1):
            if 0 <= j < len(self._order):
                other = character_key(self._segments[self._order[j]])
                if other and other != me:
                    return other, True
        return "", False

    def plan_line(self, seg: dict[str, Any]) -> tuple[PronounDecision, LevelDecision, dict[str, Any]]:
        text = str(seg.get("text") or seg.get("original_text") or "")
        speaker = character_key(seg)
        listener, inferred = self._listener(seg)
        cfg = self.store.config
        sp = self.store.effective(speaker) if speaker else None
        lp = self.store.effective(listener) if listener else None
        rel = self.store.relationships.get(speaker, listener) if listener else None
        if rel is None and listener:
            rel = analyze_line(text, speaker, listener, inventory=self.inventory)
        scene_id = str(seg.get("scene_id") or "")
        scene = cfg.scene(scene_id)
        register = (scene.register if scene and scene.register else "") or (sp.register if sp else cfg.default_register)
        listener_party = None
        if listener:
            hint = ""
            if rel is not None and rel.evidence:
                hint = str(rel.evidence[0].get("listener_gender") or "")
            listener_party = Party(listener, gender=hint, profile=lp)
        ctx = PronounContext(
            speaker=Party(speaker, gender=normalize_gender(seg.get("gender")), profile=sp),
            listener=listener_party,
            relation=rel.relation if rel else "",
            relation_source=rel.source if rel else "",
            relation_confidence=rel.confidence if rel else 1.0,
            hostility=rel.hostility if rel else 0,
            intimacy=rel.intimacy if rel else 0,
            register=register,
            emotion=str(seg.get("expression") or "neutral").strip().lower() or "neutral",
            scene_id=scene_id,
            scene_formality=scene.formality if scene else "neutral",
            listener_inferred=inferred,
        )
        decision = self.resolver.resolve(ctx)
        levels = select_levels(text, sp, cfg, scene, source_language=_source_marker_language(self.source_lang))
        style = line_constraints(emotion=ctx.emotion, register=register, levels=levels, profile=sp)
        meta = {"speaker": speaker, "listener": listener, "listener_inferred": inferred,
                "relation_source": ctx.relation_source, "scene_id": scene_id}
        self._plans[str(seg.get("id"))] = (decision, levels, meta)
        return decision, levels, {**style, "_meta": meta}

    def _character_summary(self, keys: Iterable[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for key in keys:
            prof = self.store.effective(key) if key else None
            if prof is None:
                continue
            row = {
                "gender": prof.gender, "age_group": prof.age_group, "register": prof.register,
                "slang_level": prof.slang_level, "profanity_level": prof.profanity_level,
                "social_role": prof.social_role, "catchphrases": prof.catchphrases[:3],
            }
            out[prof.name or key] = {k: v for k, v in row.items() if v not in ("", [], "unknown")}
        return out

    def build_inputs(self, payload: list[dict[str, Any]]) -> dict[str, Any]:
        base = super().build_inputs(payload)
        keys: list[str] = []
        for row in base["dialogue"]:
            seg = {**self._segments.get(str(row["id"]), {}), **{k: v for k, v in row.items() if v not in ("", None)}}
            decision, _levels, style = self.plan_line(seg)
            meta = style.pop("_meta")
            row["listener"] = meta["listener"]
            row["pronoun_plan"] = decision.plan()
            row["style"] = style
            keys += [meta["speaker"], meta["listener"]]
        return {
            "source_language": base["source_language"],
            "target_language": base["target_language"],
            "dialogue": base["dialogue"],
            "characters": self._character_summary(dict.fromkeys(k for k in keys if k)),
            "scene_context": base["scene_context"],
            "glossary": base["glossary"],
        }

    # ── reply ───────────────────────────────────────────────────────────
    def check(self, mapped: Any, inputs: dict[str, Any]) -> ValidationResult:
        res = self.skill.validate_output(mapped, inputs)
        if not res.ok:
            return res
        by_id = {str(line["id"]): line for line in inputs.get("dialogue") or []}
        review: list[dict[str, Any]] = []
        for row in res.data.get("lines") or []:
            key = str(row.get("id"))
            line = by_id.get(key) or {}
            plan, style = line.get("pronoun_plan") or {}, line.get("style") or {}
            localized = str(row.get("localized_text") or "").strip()
            pc = check_line(
                localized, plan, profanity_max=int(style.get("profanity_max", 0)),
                declared=row.get("pronouns_used") or None, inventory=self.inventory,
            )
            warnings = list(pc.warnings)
            if str(row.get("source_text") or "").strip() != str(line.get("text") or "").strip():
                warnings.append("source_text_changed")
            cap = int((line.get("recommended_syllables") or {}).get("max") or 0)
            if self.count_units is not None and cap and localized:
                units = int(self.count_units(localized, self.target_lang))
                if units > cap:
                    warnings.append(f"timing_overflow:{units}>{cap}")
            tts = row.get("tts_text")
            tts_source = "model" if tts else "normalizer"
            if not tts:
                tts = tts_field(localized)
            conf = float(row.get("confidence") or 0.0)
            flags = list(row.get("review_flags") or [])
            reasons = [*pc.violations, *flags]
            if plan.get("needs_review"):
                reasons.append("pronoun_plan_needs_review")
            if conf < REVIEW_CONFIDENCE:
                reasons.append("low_confidence")
            decision, levels, meta = self._plans.get(key, (None, None, {}))
            record = {
                "id": key,
                "speaker": meta.get("speaker", ""),
                "listener": meta.get("listener", ""),
                "listener_inferred": meta.get("listener_inferred", False),
                "source_text": str(line.get("text") or ""),
                "localized_text": localized,
                "tts_text": tts,
                "tts_source": tts_source if tts else "",
                "register": row.get("register"),
                "pronouns_used": row.get("pronouns_used") or {},
                "pronouns_detected": pc.detected,
                "candidates": row.get("candidates") or [],
                "confidence": conf,
                "review_flags": flags,
                "violations": pc.violations,
                "warnings": warnings,
                "needs_review": bool(reasons),
                "review_reasons": reasons + (decision.review_reasons if decision else []),
                "pronoun_decision": decision.to_dict() if decision else plan,
                "levels": levels.to_dict() if levels else {},
                "notes": str(row.get("notes") or ""),
            }
            with self._lock:
                self._lines[key] = record
            res.warnings.extend(f"id {key}: {w}" for w in pc.violations + warnings)
            if record["needs_review"]:
                review.append({"id": key, "confidence": conf, "notes": "; ".join(record["review_reasons"][:4])})
        with self._lock:
            self._review.extend(review)
        return res

    @staticmethod
    def rows(res: ValidationResult) -> list[dict[str, Any]]:
        return [
            {"id": row.get("id"), "translated_text": str(row.get("localized_text") or "").strip()}
            for row in res.data.get("lines") or []
        ]

    def lines(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._lines.items()}

    def tts_texts(self) -> dict[str, str]:
        """Line id → text for the voice engine (falls back to the localized line)."""
        return {k: v["tts_text"] or v["localized_text"] for k, v in self.lines().items()}

    def report(self) -> dict[str, Any]:
        out = super().report()
        lines = list(self.lines().values())
        traces = [str(call.get("trace_id") or "") for call in out.get("calls") or [] if call.get("trace_id")]
        out["khmer_localization"] = {
            "dictionary_version": self.inventory.version,
            "store": str(self.store.path or ""),
            "trace_ids": traces,
            "summary": {
                "lines": len(lines),
                "needs_review": sum(1 for r in lines if r["needs_review"]),
                "violations": sum(1 for r in lines if r["violations"]),
            },
            "lines": lines[:_KEEP_LINES],
        }
        return out

    def save(self) -> Path | None:
        path = super().save()
        try:
            self.store.save()
        except Exception:
            pass
        return path


def open_session(
    segments: list[dict[str, Any]],
    *,
    source_lang: str,
    target_lang: str,
    glossary: Iterable[dict[str, Any]] = (),
    run_dir: str | Path | None = None,
    count_units: CountUnits | None = None,
    characters: Iterable[dict[str, Any]] = (),
    provider: Any = None,
) -> KhmerDialogueSession:
    skill = get_registry().get(SKILL_ID, SKILL_SPEC)
    return KhmerDialogueSession(
        skill, segments=segments, source_lang=source_lang, target_lang=target_lang,
        glossary=glossary, run_dir=run_dir, count_units=count_units, characters=characters,
        provider=provider,
    )


def session_if_enabled(
    segments: list[dict[str, Any]],
    *,
    source_lang: str,
    target_lang: str,
    glossary: Iterable[dict[str, Any]] = (),
    run_dir: str | Path | None = None,
    count_units: CountUnits | None = None,
) -> KhmerDialogueSession | None:
    """Session when the studio setting is on and the target is Khmer; otherwise None."""
    if not is_khmer(target_lang):
        return None
    from claynext.models.features import get_feature_setting

    if get_feature_setting(SETTING_KEY, "0") != "1":
        return None
    return open_session(
        segments, source_lang=source_lang, target_lang=target_lang,
        glossary=glossary, run_dir=run_dir, count_units=count_units,
    )
