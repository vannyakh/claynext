"""Character-Aware Khmer Dialogue Localization (milestone 1).

Pure Python, data-driven modules (no media work, no Rust needed):

- ``speech_profile`` — Character Speech Profiles, project config, per-project store
- ``relationships``  — Relationship Context Analyzer (directed edges + evidence)
- ``pronouns``       — Khmer Pronoun Resolver (rules in prompts/dictionaries/khmer/pronouns.yaml)
- ``slang``          — Slang and Profanity Selector (never above source intensity)
- ``dialect``        — Regional Dialect Adapter (verified entries only)
- ``naturalizer``    — Emotion-Aware Dialogue Naturalizer (constraints; rewrites later)
- ``tts_normalizer`` — TTS Pronunciation Normalizer (localized_text → tts_text)
- ``postcheck``      — deterministic pronoun / intensity verification
- ``evaluator``      — Translation Quality Evaluator over the pronoun case set
- ``skill``          — ``movie.khmer_natural_dialogue`` session for the translate path
"""
from __future__ import annotations

from claynext.models.khmer_localization.pronouns import (
    Party,
    PronounContext,
    PronounDecision,
    PronounResolver,
)
from claynext.models.khmer_localization.speech_profile import (
    LocalizationConfig,
    LocalizationStore,
    SceneStyle,
    SpeechProfile,
)
from claynext.models.khmer_localization.tts_normalizer import normalize_for_tts, tts_field

__all__ = [
    "LocalizationConfig",
    "LocalizationStore",
    "Party",
    "PronounContext",
    "PronounDecision",
    "PronounResolver",
    "SceneStyle",
    "SpeechProfile",
    "normalize_for_tts",
    "tts_field",
]
