"""Pydantic contracts for ``movie.khmer_natural_dialogue``.

Registered into ``claynext.prompts.contracts.CONTRACTS`` on import so the
registry's validator runs them after the JSON Schema check. Without Pydantic
only the JSON Schema files apply.
"""
from __future__ import annotations

import warnings
from typing import Any, Literal

from claynext.prompts.contracts import CONTRACTS, HAVE_PYDANTIC

OUTPUT_CONTRACT = "khmer_localization"
INPUT_CONTRACT = "khmer_natural_dialogue.input"

if HAVE_PYDANTIC:
    from pydantic import BaseModel, ConfigDict, Field, field_validator

    # The contract field "register" shadows ABCMeta.register on the class only; instances are unaffected.
    warnings.filterwarnings("ignore", message=r'Field name "register" in "\w+" shadows', category=UserWarning)

    Register = Literal["formal", "neutral", "casual", "street", "regional"]
    ReviewFlag = Literal[
        "pronoun_uncertain", "register_uncertain", "idiom_uncertain", "intensity_uncertain",
        "regional_variant", "meaning_uncertain", "timing_tight",
    ]

    class _Loose(BaseModel):
        model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    class PronounPlan(_Loose):
        first_person: str = Field(min_length=1)
        second_person: str = Field(min_length=1)
        first_alternatives: list[str] = Field(default_factory=list)
        second_alternatives: list[str] = Field(default_factory=list)
        forbidden: list[str] = Field(default_factory=list)
        allow_rough: bool = False
        relation: str = "unknown"
        confidence: float = Field(default=0.0, ge=0, le=1)
        needs_review: bool = False

    class LineStyle(_Loose):
        emotion: str = "neutral"
        intensity: Literal["low", "medium", "high"] = "medium"
        register: Register = "neutral"
        slang_max: int = Field(ge=0, le=3)
        profanity_max: int = Field(ge=0, le=3)
        source_profanity: int = Field(default=0, ge=0, le=3)
        keep_intensity: bool = True
        catchphrases: list[str] = Field(default_factory=list)

    class InputLine(_Loose):
        id: int | str
        text: str
        speaker: str = ""
        listener: str = ""
        gender: str = ""
        expression: str = ""
        duration_sec: float = Field(default=0.0, ge=0)
        recommended_syllables: dict[str, int] | None = None
        pronoun_plan: PronounPlan
        style: LineStyle

    class KhmerDialogueInput(_Loose):
        source_language: str = ""
        target_language: str = Field(min_length=1)
        dialogue: list[InputLine] = Field(min_length=1)
        characters: dict[str, Any] = Field(default_factory=dict)
        scene_context: str = ""
        glossary: list[dict[str, str]] = Field(default_factory=list)

    class PronounsUsed(_Loose):
        first_person: list[str] = Field(default_factory=list)
        second_person: list[str] = Field(default_factory=list)

    class Candidate(_Loose):
        text: str = Field(min_length=1)
        register: str = ""
        note: str = ""

    class LocalizedLine(_Loose):
        id: int | str
        source_text: str
        localized_text: str = Field(min_length=1)
        tts_text: str | None = None
        pronouns_used: PronounsUsed = Field(default_factory=PronounsUsed)
        register: Register
        candidates: list[Candidate] = Field(default_factory=list, max_length=3)
        confidence: float = Field(ge=0, le=1)
        review_flags: list[ReviewFlag] = Field(default_factory=list)
        notes: str = ""

        @field_validator("tts_text")
        @classmethod
        def _blank_is_null(cls, value: str | None) -> str | None:
            return value if value and value.strip() else None

    class KhmerLocalization(_Loose):
        lines: list[LocalizedLine] = Field(min_length=1)

        @field_validator("lines")
        @classmethod
        def _unique_ids(cls, rows: list[LocalizedLine]) -> list[LocalizedLine]:
            seen: set[str] = set()
            for row in rows:
                if str(row.id) in seen:
                    raise ValueError(f"duplicate id {row.id}")
                seen.add(str(row.id))
            return rows

    CONTRACTS.setdefault(OUTPUT_CONTRACT, KhmerLocalization)
    CONTRACTS.setdefault(INPUT_CONTRACT, KhmerDialogueInput)
