"""Pydantic contracts for skill inputs and outputs.

The JSON Schema files in ``schemas/`` are the canonical contracts and are
always checked. These models add typed normalization when Pydantic is
installed; ``CONTRACTS`` is empty without it.
"""
from __future__ import annotations

from typing import Any

try:
    from pydantic import BaseModel, ConfigDict, Field, field_validator

    HAVE_PYDANTIC = True
except ImportError:  # pragma: no cover - exercised by forcing the fallback in tests
    HAVE_PYDANTIC = False

CONTRACTS: dict[str, Any] = {}

if HAVE_PYDANTIC:

    class _Loose(BaseModel):
        model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    class SpeechQuota(_Loose):
        min: int = Field(default=0, ge=0)
        target: int = Field(default=0, ge=0)
        max: int = Field(default=0, ge=0)

    class DialogueLine(_Loose):
        id: int | str
        text: str
        speaker: str = ""
        gender: str = ""
        expression: str = ""
        duration_sec: float = Field(default=0.0, ge=0)
        recommended_syllables: SpeechQuota | None = None

    class CharacterProfile(_Loose):
        gender: str = ""
        role: str = ""
        personality: str = ""
        notes: str = ""

    class GlossaryEntry(_Loose):
        source: str = Field(min_length=1)
        target: str = Field(min_length=1)
        note: str = ""

    class DialogueTranslationInput(_Loose):
        source_language: str = ""
        target_language: str = Field(min_length=1)
        dialogue: list[DialogueLine] = Field(min_length=1)
        scene_context: str = ""
        character_profile: dict[str, CharacterProfile] = Field(default_factory=dict)
        glossary: list[GlossaryEntry] = Field(default_factory=list)

    class TranslatedLine(_Loose):
        id: int | str
        translation: str = Field(min_length=1)
        confidence: float | None = Field(default=None, ge=0, le=1)
        notes: str = ""

    class DialogueTranslation(_Loose):
        translations: list[TranslatedLine] = Field(min_length=1)

        @field_validator("translations")
        @classmethod
        def _unique_ids(cls, rows: list[TranslatedLine]) -> list[TranslatedLine]:
            seen: set[str] = set()
            for row in rows:
                key = str(row.id)
                if key in seen:
                    raise ValueError(f"duplicate id {key}")
                seen.add(key)
            return rows

    CONTRACTS.update({
        "translation": DialogueTranslation,
        "dialogue_translation.input": DialogueTranslationInput,
    })
