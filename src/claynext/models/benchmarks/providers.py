"""Translators for the benchmark runner.

OpenAI-compatible calls go through ``llm_gateway``. Gemini goes through the
existing teacher provider. A local model id is a callable the caller supplies.
None of these builders put the model id into the prompt text.
"""
from __future__ import annotations

from typing import Any, Callable

from claynext.models.benchmarks.prompt import translation_prompt
from claynext.models.benchmarks.schema import BenchmarkRow
from claynext.models.llm_gateway.base import ChatMessage, ChatRequest

TranslateResult = dict[str, Any]
LocalComplete = Callable[..., Any]


def coerce_output(value: Any) -> TranslateResult:
    if isinstance(value, str):
        return _blank(value.strip())
    if isinstance(value, tuple):
        text = str(value[0] if value else "").strip()
        out = _blank(text)
        out["trace_id"] = str(value[1] if len(value) > 1 else "")
        return out
    if isinstance(value, dict):
        out = _blank(str(value.get("text") or "").strip())
        for key in ("latency_ms", "cost_usd", "tokens_in", "tokens_out"):
            if key in value:
                out[key] = value[key]
        out["trace_id"] = str(value.get("trace_id") or "")
        return out
    raise TypeError("translator must return str, tuple, or dict")


def _blank(text: str) -> TranslateResult:
    return {
        "text": text,
        "latency_ms": None,
        "cost_usd": None,
        "tokens_in": None,
        "tokens_out": None,
        "trace_id": "",
    }


def gateway_translator(provider: Any, *, temperature: float = 0.0) -> Callable[[BenchmarkRow], TranslateResult]:
    """One row through an ``LlmProvider``. Works for OpenAI-compatible fakes and live clients."""

    def translate(row: BenchmarkRow) -> TranslateResult:
        request = ChatRequest(
            messages=[ChatMessage("user", translation_prompt(row))],
            temperature=temperature,
            tags={"benchmark_row": row.id, "prompt_version": "khmer-movie-benchmark-1"},
        )
        response = provider.complete(request)
        return {
            "text": (response.text or "").strip(),
            "latency_ms": response.latency_ms,
            "cost_usd": response.usage.cost_usd,
            "tokens_in": response.usage.tokens_in,
            "tokens_out": response.usage.tokens_out,
            "trace_id": response.trace_id,
        }

    return translate


def gemini_teacher_translator(
    teacher: Any,
    *,
    temperature: float = 0.0,
) -> Callable[[BenchmarkRow], TranslateResult]:
    """Adapter over an object with ``complete(prompt, temperature=, response_json=)``."""

    def translate(row: BenchmarkRow) -> TranslateResult:
        result = teacher.complete(
            translation_prompt(row),
            temperature=temperature,
            response_json=False,
        )
        if not getattr(result, "ok", False):
            error = str(getattr(result, "error", "") or "gemini failed")
            raise RuntimeError(redact_provider_error(error))
        return _blank((getattr(result, "text", "") or "").strip())

    return translate


def local_model_translator(
    model_id: str,
    complete: LocalComplete,
) -> Callable[[BenchmarkRow], TranslateResult]:
    """``complete(prompt)`` talks to a model that is already loaded. This does not download weights."""

    def translate(row: BenchmarkRow) -> TranslateResult:
        produced = complete(translation_prompt(row))
        output = coerce_output(produced)
        output["model_id"] = model_id
        return output

    return translate


def redact_provider_error(text: str) -> str:
    import re

    from claynext.models.llm_gateway.openai_provider import redact

    cleaned = redact(text or "")
    cleaned = re.sub(r"(key=)[^&\s\"']+", r"\1***", cleaned, flags=re.IGNORECASE)
    return cleaned
