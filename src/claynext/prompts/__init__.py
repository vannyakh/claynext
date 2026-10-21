"""Versioned AI skills: manifests, templates, contracts, and evaluations.

Skills guide a model; they do not train it or add capabilities. A skill is
data (``skills/<name>/skill.yaml`` + ``prompt.j2``) rendered and validated
here, then sent through the caller's existing provider path.

    from claynext.prompts import get_registry

    skill = get_registry().get("movie.dialogue_translation", "^1.0")
    prompt = skill.render(inputs)
    result = skill.validate_output(reply, inputs)
"""
from __future__ import annotations

from claynext.prompts.registry import (
    RenderedPrompt,
    Skill,
    SkillNotFound,
    SkillRegistry,
    SkillResolutionError,
    get_registry,
)

__all__ = [
    "RenderedPrompt",
    "Skill",
    "SkillNotFound",
    "SkillRegistry",
    "SkillResolutionError",
    "get_registry",
]
