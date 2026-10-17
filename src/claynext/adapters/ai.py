"""
AI Adapter: Python models → claynext-ai Rust runtime (LLM, OCR, VAD, TTS tags).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from claynext.adapters.rust_bridge import RustAiAdapter

logger = logging.getLogger("claynext.adapters.ai")


class AiAdapter:
    """Domain facade over ``RustAiAdapter`` for Studio models/services."""

    def is_available(self) -> bool:
        return RustAiAdapter.is_available()

    def get_device_config(self) -> dict[str, Any]:
        return RustAiAdapter.get_device_config()

    def parse_retry_after(
        self, status: int, header: str | None = None, body: str = ""
    ) -> tuple[bool, float]:
        return RustAiAdapter.parse_retry_after(status, header=header, body=body)

    def acquire_llm_key(
        self, keys: list[dict[str, Any]], provider: str
    ) -> dict[str, Any] | None:
        return RustAiAdapter.acquire_llm_key(keys, provider)

    def soonest_cooldown(self, keys: list[dict[str, Any]], provider: str) -> float:
        return RustAiAdapter.soonest_cooldown(keys, provider)

    def parse_expression_tags(self, text: str) -> list[dict[str, Any]]:
        return RustAiAdapter.parse_expression_tags(text)

    def chunk_subtitles(self, text: str, max_chars: int = 1500) -> list[dict[str, Any]]:
        return RustAiAdapter.chunk_subtitles(text, max_chars=max_chars)

    def filter_ocr(
        self, boxes: list[dict[str, Any]], min_confidence: float = 0.5
    ) -> list[dict[str, Any]]:
        return RustAiAdapter.filter_ocr(boxes, min_confidence=min_confidence)

    def vad_chunk(
        self,
        media_path: str | Path | None = None,
        *,
        sample_rate: int = 16000,
        threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        return RustAiAdapter.vad_chunk(
            media_path, sample_rate=sample_rate, threshold=threshold
        )

    def build_translate_prompt(
        self, source_lang: str, target_lang: str, text: str
    ) -> str | None:
        return RustAiAdapter.build_translate_prompt(source_lang, target_lang, text)


_ai_adapter: AiAdapter | None = None


def get_ai_adapter() -> AiAdapter:
    global _ai_adapter
    if _ai_adapter is None:
        _ai_adapter = AiAdapter()
    return _ai_adapter
