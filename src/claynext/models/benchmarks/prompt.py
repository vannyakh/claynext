"""Standard benchmark prompt. The model id is never interpolated into the text."""
from __future__ import annotations

import hashlib

from claynext.models.benchmarks.schema import BenchmarkRow

PROMPT_VERSION = "khmer-movie-benchmark-1"
JUDGE_PROMPT_VERSION = "khmer-movie-judge-1"

_TEMPLATE = (
    "Translate the movie dialogue into natural spoken Khmer.\n"
    "Keep the speaker's meaning, emotion, and relationship.\n"
    "Reply with the Khmer line only.\n"
    "Source language: {source_language}\n"
    "Dialogue:\n{source_text}\n"
)

_JUDGE = (
    "Compare the hypothesis to the reference for a Khmer movie dialogue line.\n"
    "Consider meaning, naturalness, pronouns, emotion and register, and terminology.\n"
    "You are not told which system wrote the hypothesis. Do not guess a product or model name.\n"
    "Source:\n{source_text}\n"
    "Reference:\n{reference_khmer}\n"
    "Hypothesis:\n{hypothesis}\n"
)


def translation_prompt(row: BenchmarkRow) -> str:
    return _TEMPLATE.format(
        source_language=row.source_language or "und",
        source_text=row.source_text,
    )


def prompt_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def template_sha256() -> str:
    return prompt_sha256(_TEMPLATE)


def judge_prompt(*, source_text: str, reference_khmer: str, hypothesis: str) -> str:
    """Blind judge prompt. Callers must not append a model id."""
    return _JUDGE.format(
        source_text=source_text,
        reference_khmer=reference_khmer,
        hypothesis=hypothesis,
    )


def contains_model_id(text: str, model_id: str) -> bool:
    label = (model_id or "").strip().lower()
    if not label:
        return False
    return label in text.lower()
