"""Character Intelligence stage of the dub job (after translation, before TTS)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from claynext.models.character_intel.performance_planner import plan_performance, save_plan
from claynext.models.character_intel.prosody import analyze_segments_prosody
from claynext.models.character_intel.registry import UNKNOWN_NAME, CharacterRegistry

logger = logging.getLogger("claynext.character_intel")

PLAN_FILE = "performance_plan.json"
REGISTRY_FILE = "character_registry.json"


def planner_enabled() -> bool:
    try:
        from claynext.controllers.store import get_store

        return get_store().get_setting("dub", "performance_planner", "1") == "1"
    except Exception:
        return True


def _known_names(registry: CharacterRegistry, segments: list[dict[str, Any]]) -> list[str]:
    names = [str(c.get("name") or "") for c in registry.characters if c.get("name") != UNKNOWN_NAME]
    for seg in segments:
        label = str(seg.get("speaker") or "")
        if label and seg.get("speaker_label_source") != "voice" and label not in names:
            names.append(label)
    return [n for n in names if n]


def run_character_stage(
    segments: list[dict[str, Any]],
    *,
    media_path: str,
    audio_path: str,
    job_dir: str | Path,
    target_lang: str,
    source_lang: str = "",
    base_voice: str = "",
    ping: Callable[[int, str], None] | None = None,
    share: Callable[[str, Any], None] | None = None,
) -> dict[str, Any]:
    """Registry + prosody + performance plan. Lines are updated in place; never raises."""
    job = Path(job_dir)
    result: dict[str, Any] = {"plan_path": "", "registry_path": "", "engine": "", "characters": 0}
    try:
        registry = CharacterRegistry.for_media(media_path)
        profiles = registry.reconcile(segments, lang=target_lang, base_voice=base_voice)
        result["characters"] = len(profiles)
        if ping:
            ping(57, f"Character registry · {len(profiles)} character(s)")
    except Exception as exc:
        logger.warning("character registry failed: %s", exc)
        registry = None

    prosody: list[dict[str, Any] | None] = []
    if ping:
        ping(57, "Reading delivery from the original voices…")
    try:
        prosody = analyze_segments_prosody(audio_path, segments)
    except Exception as exc:
        logger.debug("prosody failed: %s", exc)

    try:
        names = _known_names(registry, segments) if registry else []
        plan = plan_performance(segments, lang=target_lang, names=names, prosody=prosody)
        result["engine"] = plan.get("engine", "")
        result["plan_path"] = save_plan(plan, job / PLAN_FILE)
        styled = sum(1 for row in plan["lines"] if row.get("style") != "neutral")
        if ping:
            ping(57, f"Performance plan · {styled}/{len(plan['lines'])} expressive line(s)")
        if share:
            share("performance", plan)
    except Exception as exc:
        logger.warning("performance plan failed: %s", exc)

    if registry is not None:
        try:
            registry.update_from_plan(segments, source_lang=source_lang)
            result["registry_path"] = registry.save()
            registry.save(job / REGISTRY_FILE)
            if share:
                share("characters", registry.to_dict())
        except Exception as exc:
            logger.warning("character registry save failed: %s", exc)
    return result
