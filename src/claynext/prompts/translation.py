"""``movie.dialogue_translation`` session for the movie translate path.

The session turns translate batches into skill inputs, renders the prompt,
checks the model reply, and records each call. Backend calls stay in
``TranslateEngine``; this module only sees data.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from claynext.prompts import loader
from claynext.prompts.registry import RenderedPrompt, Skill, get_registry
from claynext.prompts.validator import ValidationResult

SKILL_ID = "movie.dialogue_translation"
SKILL_SPEC = "^1.0"
SETTING_KEY = "skill_dialogue_translation"
REVIEW_CONFIDENCE = 0.6
_CONTEXT_LINES = 2
_KEEP_RUNS = 20

CountUnits = Callable[[str, str], int]


def _norm_term(text: str) -> str:
    return (text or "").strip().lower()


def _term_in(term: str, text: str) -> bool:
    term, text = _norm_term(term), (text or "").lower()
    if not term:
        return False
    if term.isascii():
        return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None
    return term in text


def merge_glossary(*sources: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Later sources win on the same source term (project over language defaults)."""
    merged: dict[str, dict[str, str]] = {}
    for rows in sources:
        for row in rows or []:
            src = str(row.get("source") or "").strip()
            tgt = str(row.get("target") or "").strip()
            if src and tgt:
                merged[_norm_term(src)] = {"source": src, "target": tgt, "note": str(row.get("note") or "").strip()}
    return list(merged.values())


def glossary_for(lines: list[dict[str, Any]], glossary: list[dict[str, str]]) -> list[dict[str, str]]:
    """Only the terms that occur in these lines, to keep prompts short."""
    blob = "\n".join(str(line.get("text") or "") for line in lines)
    return [row for row in glossary if _term_in(row["source"], blob)]


def glossary_misses(inputs: dict[str, Any], translations: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_id = {str(row.get("id")): str(row.get("translation") or "") for row in translations}
    misses = []
    for line in inputs.get("dialogue") or []:
        out = by_id.get(str(line.get("id")), "")
        for term in inputs.get("glossary") or []:
            if _term_in(term["source"], str(line.get("text") or "")) and term["target"].lower() not in out.lower():
                misses.append({"id": str(line.get("id")), "source": term["source"], "target": term["target"]})
    return misses


def timing_overflows(
    inputs: dict[str, Any],
    translations: list[dict[str, Any]],
    count_units: CountUnits,
) -> list[dict[str, Any]]:
    by_id = {str(row.get("id")): str(row.get("translation") or "") for row in translations}
    lang = str(inputs.get("target_language") or "")
    over = []
    for line in inputs.get("dialogue") or []:
        cap = int((line.get("recommended_syllables") or {}).get("max") or 0)
        text = by_id.get(str(line.get("id")), "")
        if cap > 0 and text:
            units = int(count_units(text, lang))
            if units > cap:
                over.append({"id": str(line.get("id")), "units": units, "max": cap})
    return over


def review_items(translations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for row in translations:
        conf = row.get("confidence")
        if (isinstance(conf, (int, float)) and conf < REVIEW_CONFIDENCE) or row.get("notes"):
            items.append({"id": str(row.get("id")), "confidence": conf, "notes": str(row.get("notes") or "")})
    return items


def project_key(segments: list[dict[str, Any]], source_lang: str, target_lang: str) -> str:
    texts = "\n".join(str(s.get("text") or s.get("original_text") or "") for s in segments[:64])
    raw = f"{source_lang}|{target_lang}|{len(segments)}|{texts}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def default_runs_dir() -> Path:
    from claynext.utils.paths import CACHE_DIR

    return CACHE_DIR / "skills" / "runs"


class TranslationSkillSession:
    """One movie translate run through ``movie.dialogue_translation``."""

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
    ):
        self.skill = skill
        self.source_lang = source_lang or "auto"
        self.target_lang = target_lang
        self.count_units = count_units
        self._order = [str(s.get("id")) for s in segments]
        self._segments = {str(s.get("id")): s for s in segments}
        lang = loader.load_language(target_lang, force_fallback=skill.force_fallback)
        self.glossary = merge_glossary((lang or {}).get("glossary") or [], glossary)
        self.project_key = project_key(segments, self.source_lang, target_lang)
        if run_dir:
            self.path = Path(run_dir) / "skill_runs" / f"{skill.id}.json"
        else:
            self.path = default_runs_dir() / f"{self.project_key}.json"
        self._lock = threading.Lock()
        self._calls: list[dict[str, Any]] = []
        self._review: list[dict[str, Any]] = []
        self.started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    @property
    def max_lines(self) -> int:
        return max(1, int(self.skill.manifest.limits.get("max_lines_per_call") or 16))

    def supports(self, backend: str) -> bool:
        return self.skill.supports_backend(backend)

    def chunks(self, batch: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        n = self.max_lines
        return [batch[i:i + n] for i in range(0, len(batch), n)]

    def _profiles(self, payload: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for line in payload:
            name = str(line.get("speaker") or "").strip()
            if not name or name in out:
                continue
            seg = self._segments.get(str(line.get("id")), {})
            profile = {
                "gender": str(line.get("gender") or seg.get("gender") or ""),
                "role": str(seg.get("character_role") or ""),
                "personality": str(seg.get("personality") or ""),
                "notes": "",
            }
            out[name] = {k: v for k, v in profile.items() if v}
        return out

    def _scene(self, payload: list[dict[str, Any]]) -> str:
        if not payload:
            return ""
        first = str(payload[0].get("id"))
        if first not in self._order:
            return ""
        idx = self._order.index(first)
        rows = []
        for key in self._order[max(0, idx - _CONTEXT_LINES):idx]:
            seg = self._segments[key]
            text = str(seg.get("text") or seg.get("original_text") or "").strip()
            if text:
                who = str(seg.get("speaker") or "").strip()
                rows.append(f"{who}: {text}" if who else text)
        return "\n".join(rows)

    def build_inputs(self, payload: list[dict[str, Any]]) -> dict[str, Any]:
        dialogue = []
        for line in payload:
            row = {
                "id": line.get("id"),
                "text": str(line.get("text") or ""),
                "speaker": str(line.get("speaker") or ""),
                "gender": str(line.get("gender") or ""),
                "expression": str(line.get("expression") or ""),
                "duration_sec": float(line.get("duration_sec") or 0.0),
            }
            quota = line.get("recommended_syllables")
            if isinstance(quota, dict) and quota.get("target"):
                row["recommended_syllables"] = {k: int(quota.get(k) or 0) for k in ("min", "target", "max")}
            dialogue.append(row)
        return {
            "source_language": self.source_lang,
            "target_language": self.target_lang,
            "dialogue": dialogue,
            "scene_context": self._scene(payload),
            "character_profile": self._profiles(payload),
            "glossary": glossary_for(dialogue, self.glossary),
        }

    def render(self, payload: list[dict[str, Any]]) -> tuple[RenderedPrompt, dict[str, Any]]:
        inputs = self.build_inputs(payload)
        return self.skill.render(inputs), inputs

    def check(self, mapped: Any, inputs: dict[str, Any]) -> ValidationResult:
        res = self.skill.validate_output(mapped, inputs)
        if not res.ok:
            return res
        rows = res.data.get("translations") or []
        for miss in glossary_misses(inputs, rows):
            res.warnings.append(f"id {miss['id']}: glossary {miss['source']} → {miss['target']} not used")
        if self.count_units is not None:
            for over in timing_overflows(inputs, rows, self.count_units):
                res.warnings.append(f"id {over['id']}: {over['units']} units > max {over['max']}")
        with self._lock:
            self._review.extend(review_items(rows))
        return res

    @staticmethod
    def rows(res: ValidationResult) -> list[dict[str, Any]]:
        return [
            {"id": row.get("id"), "translated_text": str(row.get("translation") or "").strip()}
            for row in res.data.get("translations") or []
        ]

    def record(
        self,
        *,
        backend: str,
        model: str,
        settings_applied: dict[str, Any],
        inputs: dict[str, Any] | None,
        prompt: RenderedPrompt | None,
        result: ValidationResult | None,
        error: str = "",
        trace_id: str = "",
    ) -> None:
        entry = {
            "backend": backend,
            "model": model,
            "settings_applied": dict(settings_applied),
            "lines": len((inputs or {}).get("dialogue") or []),
            "glossary_terms": len((inputs or {}).get("glossary") or []),
            "prompt_chars": len(prompt.text) if prompt else 0,
            "validation": result.summary() if result else None,
            "fallback": result is None or not result.ok,
            "error": error[:300],
            "trace_id": str(trace_id or ""),
        }
        with self._lock:
            self._calls.append(entry)

    def report(self) -> dict[str, Any]:
        with self._lock:
            calls = list(self._calls)
            review = list(self._review)
        ok = [c for c in calls if not c["fallback"]]
        return {
            "run_started": self.started,
            "skill_id": self.skill.id,
            "version": self.skill.version,
            "fingerprint": self.skill.fingerprint,
            "lock": self.skill.lock_status(),
            "settings": self.skill.settings,
            "source_language": self.source_lang,
            "target_language": self.target_lang,
            "lines": len(self._order),
            "summary": {
                "calls": len(calls),
                "validated": len(ok),
                "fallbacks": len(calls) - len(ok),
                "lines_from_skill": sum(c["lines"] for c in ok),
                "lines_from_legacy": sum(c["lines"] for c in calls if c["fallback"]),
            },
            "calls": calls,
            "review": review[:100],
        }

    def save(self) -> Path | None:
        """Append this run to the per-project JSON. Never raises."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            runs = list(data.get("runs") or [])
            runs.append(self.report())
            payload = {"project_key": self.project_key, "skill_id": self.skill.id, "runs": runs[-_KEEP_RUNS:]}
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return self.path
        except Exception:
            return None


def open_session(
    segments: list[dict[str, Any]],
    *,
    source_lang: str,
    target_lang: str,
    glossary: Iterable[dict[str, Any]] = (),
    run_dir: str | Path | None = None,
    count_units: CountUnits | None = None,
) -> TranslationSkillSession:
    skill = get_registry().get(SKILL_ID, SKILL_SPEC)
    return TranslationSkillSession(
        skill,
        segments=segments,
        source_lang=source_lang,
        target_lang=target_lang,
        glossary=glossary,
        run_dir=run_dir,
        count_units=count_units,
    )
