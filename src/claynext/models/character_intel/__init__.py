"""Character Intelligence Engine: registry, prosody, performance plan, expression mapping."""
from __future__ import annotations

from claynext.models.character_intel.expression_mapper import STYLES, map_delivery, provider_for_voice
from claynext.models.character_intel.performance_planner import (
    plan_performance,
    set_line_style,
    style_parts,
    tempo_window,
)
from claynext.models.character_intel.registry import CharacterRegistry, registry_path
from claynext.models.character_intel.stage import planner_enabled, run_character_stage

__all__ = [
    "STYLES",
    "CharacterRegistry",
    "map_delivery",
    "plan_performance",
    "planner_enabled",
    "provider_for_voice",
    "registry_path",
    "run_character_stage",
    "set_line_style",
    "style_parts",
    "tempo_window",
]
