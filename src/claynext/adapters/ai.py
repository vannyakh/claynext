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

    def scan_burned_captions(
        self,
        video_path: str,
        roi: dict[str, Any],
        *,
        sample_interval: float = 0.4,
        start_sec: float = 0.0,
        end_sec: float = 0.0,
        min_confidence: float = 0.5,
        lang: str = "Auto",
        progress_callback=None,
    ) -> list[dict[str, Any]] | None:
        """Timed burned-in captions. None when the Rust tool cannot run."""
        return RustAiAdapter.scan_burned_captions(
            video_path,
            roi,
            sample_interval=sample_interval,
            start_sec=start_sec,
            end_sec=end_sec,
            min_confidence=min_confidence,
            lang=lang,
            progress_callback=progress_callback,
        )

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

    def fit_speech(
        self, lines: list[dict[str, Any]], turns: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        """Snap transcript lines onto soundtrack speech turns. None if Rust is missing."""
        return RustAiAdapter.fit_speech(lines, turns)

    def decode_mono_pcm(self, media_path: str | Path, sample_rate: int = 8000) -> bytes:
        """Mono f32le PCM of a media file. Empty bytes when nothing can decode it."""
        try:
            from claynext.adapters.ffmpeg_adapter import get_ffmpeg_adapter

            chunk = get_ffmpeg_adapter().decode_audio_pcm_f32(
                media_path, sample_rate=sample_rate, channels=1
            )
            raw = chunk.raw_pcm if chunk else b""
            if raw:
                return raw
        except Exception as exc:
            logger.debug("Rust PCM decode failed: %s", exc)
        import os
        import tempfile

        tmp_path = ""
        try:
            from claynext.adapters.ffmpeg_service import run_ffmpeg

            with tempfile.NamedTemporaryFile(suffix=".f32", delete=False) as tmp:
                tmp_path = tmp.name
            proc = run_ffmpeg(
                ["-y", "-i", str(media_path), "-vn", "-ac", "1", "-ar", str(int(sample_rate)),
                 "-f", "f32le", "-acodec", "pcm_f32le", tmp_path],
                timeout=600,
            )
            if proc.returncode == 0 and Path(tmp_path).is_file():
                return Path(tmp_path).read_bytes()
        except Exception as exc:
            logger.debug("FFmpeg PCM decode failed: %s", exc)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        return b""

    def analyze_prosody_pcm(
        self, pcm: bytes, sample_rate: int, spans: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        """Per-line energy / pitch / voicing from Rust. None when the binary is missing."""
        if not pcm or not spans or not RustAiAdapter.is_available():
            return None
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".f32", delete=False) as tmp:
            tmp.write(pcm)
            tmp_path = tmp.name
        try:
            return RustAiAdapter.analyze_prosody_pcm(tmp_path, sample_rate, spans)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

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
