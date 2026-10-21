"""Gemini speech generation (TTS) previews for Khmer — AI Studio only.

Official reference: https://ai.google.dev/gemini-api/docs/speech-generation

Gemini 3.8 Flash-Lite TTS lists Khmer among supported languages — verify at
call time. Missing keys or unsupported models skip gracefully (never crash Studio).

Text Gemini SFT (Vertex) does **not** train this TTS voice model.
Voice cloning / cinematic voice engine lives in ``claynext.voice_training``.
"""
from __future__ import annotations

import base64
import json
import logging
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

ProgressCb = Callable[[int, str], None] | None

# Candidate model ids — probe at call time; do not hard-fail Studio if renamed.
DEFAULT_TTS_MODELS = (
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
    "gemini-3.8-flash-lite-preview-tts",
)


@dataclass
class GeminiTtsPreviewResult:
    ok: bool
    path: str = ""
    model: str = ""
    voice: str = ""
    skipped: bool = False
    error: str = ""
    reason: str = ""  # missing_key | unsupported_model | api_error | empty_audio


class GeminiTtsProvider:
    """Generate short Khmer TTS previews via Gemini speech-generation API."""

    provider_id = "google_ai_studio_gemini_tts"

    def __init__(self, *, models: tuple[str, ...] = DEFAULT_TTS_MODELS):
        self.models = models

    def available(self) -> bool:
        try:
            from claynext.models.llm_keys import get_key_pool

            pool = get_key_pool()
            return bool(pool.secrets("gemini") or pool.ready_count("gemini") > 0)
        except Exception:
            return False

    def capabilities(self) -> dict[str, Any]:
        return {
            "platform": "google_ai_studio",
            "speech_generation": True,
            "khmer_listed": "unverified_until_call",
            "docs": "https://ai.google.dev/gemini-api/docs/speech-generation",
            "models": list(self.models),
            "models_status": "unverified_until_call",
            "trains_voice_model": False,
            "vertex_sft_affects_tts": False,
        }

    def synthesize_preview(
        self,
        text: str,
        output_path: str | Path,
        *,
        voice: str = "Kore",
        style_instruction: str = "",
        language_code: str = "km",
        progress_callback: ProgressCb = None,
    ) -> GeminiTtsPreviewResult:
        """Write a WAV preview. Skips cleanly when key/model unavailable."""
        text = (text or "").strip()
        if not text:
            return GeminiTtsPreviewResult(
                ok=False, skipped=True, reason="empty_audio", error="Empty text."
            )
        if not self.available():
            return GeminiTtsPreviewResult(
                ok=False,
                skipped=True,
                reason="missing_key",
                error="No Gemini API key — TTS preview skipped.",
            )

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        prompt = text
        if style_instruction:
            prompt = f"{style_instruction.strip()}\n\nSpeak in Khmer:\n{text}"
        elif language_code.lower().startswith("km"):
            prompt = f"Speak the following naturally in Khmer:\n{text}"

        last_err = "Gemini TTS failed"
        for model in self.models:
            if progress_callback:
                progress_callback(10, f"Trying {model}…")
            try:
                pcm = self._generate_pcm(
                    model, prompt, voice=voice, progress_callback=progress_callback
                )
                if not pcm:
                    last_err = f"{model}: empty audio"
                    continue
                self._write_wav(out, pcm)
                if progress_callback:
                    progress_callback(100, "TTS preview ready")
                return GeminiTtsPreviewResult(
                    ok=True, path=str(out), model=model, voice=voice
                )
            except Exception as exc:
                msg = str(exc)
                last_err = msg
                logger.info("Gemini TTS model %s failed: %s", model, msg)
                # 404 / not found → try next model as unsupported.
                if "404" in msg or "not found" in msg.lower() or "NOT_FOUND" in msg:
                    continue
                continue

        reason = "unsupported_model" if "404" in last_err or "NOT_FOUND" in last_err else "api_error"
        return GeminiTtsPreviewResult(
            ok=False,
            skipped=True,
            reason=reason,
            error=last_err[:500],
        )

    @staticmethod
    def _generate_pcm(
        model: str,
        prompt: str,
        *,
        voice: str,
        progress_callback: ProgressCb,
    ) -> bytes:
        import urllib.error
        import urllib.parse
        import urllib.request

        from claynext.models.llm_keys import (
            InvalidKeyError,
            RateLimitError,
            get_key_pool,
            is_rate_limit,
            note_llm_usage,
            parse_retry_after,
        )
        from claynext.models.translate_service import TranslateEngine

        def _do(api_key: str) -> bytes:
            TranslateEngine._pace_gemini(api_key)
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                f"?key={urllib.parse.quote(api_key)}"
            )
            body = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": voice},
                        }
                    },
                },
            }).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                note_llm_usage(model, raw)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code in (401, 403):
                    raise InvalidKeyError(f"{model}: {exc.code}") from exc
                if is_rate_limit(exc.code, detail):
                    raise RateLimitError(
                        f"{model}: rate limited", parse_retry_after(exc.headers, detail)
                    ) from exc
                raise RuntimeError(f"{model}: {exc.code} {detail[:400]}") from exc

            parts = (
                raw.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
            )
            for part in parts:
                inline = part.get("inlineData") or part.get("inline_data") or {}
                data = inline.get("data")
                if data:
                    return base64.b64decode(data)
            return b""

        return get_key_pool().call_with_rotation(
            "gemini", _do, progress=progress_callback, max_cooldown_waits=2
        )

    @staticmethod
    def _write_wav(path: Path, pcm: bytes, *, rate: int = 24000, channels: int = 1) -> None:
        """Gemini TTS returns raw PCM s16le; wrap as WAV for QMediaPlayer."""
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(pcm)
