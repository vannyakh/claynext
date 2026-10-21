"""Google AI Studio / Gemini API teacher for KSLD.

This module wraps the existing Studio Gemini HTTP path (``TranslateEngine`` +
``llm_keys`` key pool). It does **not** submit Vertex AI supervised fine-tuning
jobs — see ``training/vertex_tuning_client.py``.

Capabilities (AI Studio):
- Generate natural Khmer conversational translations, slang variants, character
  speech styles, and emotional expression cues.
- Optional audio analysis hooks when the model supports multimodal input.
- Cost tracking via ``note_llm_usage`` when responses include usage metadata.

Does **not** retrain the base model by uploading a dataset.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

ProgressCb = Callable[[int, str], None] | None

# Models tried in order (same rolling list as TranslateEngine).
DEFAULT_TEACHER_MODELS = ("gemini-3.8-flash", "gemini-flash-latest")


@dataclass
class GeminiTeacherResult:
    ok: bool
    text: str = ""
    model: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] | None = None
    error: str = ""
    skipped: bool = False


class GeminiTeacherProvider:
    """Dataset teacher using Google AI Studio Gemini generateContent."""

    provider_id = "google_ai_studio_gemini"

    def __init__(self, *, models: tuple[str, ...] = DEFAULT_TEACHER_MODELS):
        self.models = models

    def available(self) -> bool:
        try:
            from claynext.models.llm_keys import get_key_pool

            pool = get_key_pool()
            return bool(pool.secrets("gemini") or pool.ready_count("gemini") > 0)
        except Exception:
            return False

    def capabilities(self) -> dict[str, Any]:
        """Documented capability table; flags marked unverified until probe."""
        return {
            "platform": "google_ai_studio",
            "not_vertex_tuning": True,
            "text_generation": True,
            "khmer_dialogue_teacher": True,
            "audio_analyze": "unverified",  # multimodal depends on model
            "speech_generation": "see google_tts_provider",
            "supervised_fine_tuning": False,
            "models": list(self.models),
            "models_status": "unverified_until_call",
        }

    def complete(
        self,
        prompt: str,
        *,
        temperature: float = 0.4,
        response_json: bool = True,
        progress_callback: ProgressCb = None,
    ) -> GeminiTeacherResult:
        """Raw generateContent; returns text (or skipped if no key)."""
        if not self.available():
            return GeminiTeacherResult(
                ok=False,
                skipped=True,
                error="No Gemini API key configured (GEMINI_API_KEY / Google AI Studio keys).",
            )
        try:
            from claynext.models.translate_service import TranslateEngine

            generation = {"temperature": temperature}
            if response_json:
                generation["responseMimeType"] = "application/json"
            last_err = "Gemini teacher request failed"
            for model in self.models:
                try:
                    # Reuse pacing + key rotation; parse as free text when not line-list JSON.
                    text = self._generate_text(
                        model, prompt, generation=generation, progress_callback=progress_callback
                    )
                    return GeminiTeacherResult(ok=True, text=text, model=model)
                except Exception as exc:
                    last_err = str(exc)
                    logger.info("Gemini teacher model %s failed: %s", model, exc)
                    continue
            return GeminiTeacherResult(ok=False, error=last_err)
        except Exception as exc:
            return GeminiTeacherResult(ok=False, error=str(exc))

    def generate_khmer_candidates(
        self,
        source_text: str,
        *,
        source_lang: str = "en",
        emotion: str = "neutral",
        register: str = "neutral",
        speaker_id: str = "",
        listener_id: str = "",
        progress_callback: ProgressCb = None,
    ) -> GeminiTeacherResult:
        """Ask Gemini for natural / slang / character-style Khmer candidates."""
        prompt = self._build_candidate_prompt(
            source_text,
            source_lang=source_lang,
            emotion=emotion,
            register=register,
            speaker_id=speaker_id,
            listener_id=listener_id,
        )
        # Prefer skill template when registry has it.
        skill_prompt = self._try_skill_prompt(
            source_text,
            source_lang=source_lang,
            emotion=emotion,
            register=register,
            speaker_id=speaker_id,
            listener_id=listener_id,
        )
        if skill_prompt:
            prompt = skill_prompt

        result = self.complete(prompt, progress_callback=progress_callback)
        if not result.ok:
            return result
        parsed = self._parse_candidates(result.text)
        result.candidates = parsed
        return result

    def analyze_audio_hook(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> GeminiTeacherResult:
        """Placeholder multimodal hook — capability unverified until model probe."""
        return GeminiTeacherResult(
            ok=False,
            skipped=True,
            error=(
                "Audio analysis via Gemini multimodal is not enabled in milestone 1 "
                "(capability=unverified). Use ASR adapters for transcription."
            ),
        )

    # ── internals ──────────────────────────────────────────────────────

    @staticmethod
    def _generate_text(
        model: str,
        prompt: str,
        *,
        generation: dict,
        progress_callback: ProgressCb,
    ) -> str:
        """HTTP generateContent with key pool + usage logging (no line-list parse)."""
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

        def _do(api_key: str) -> str:
            TranslateEngine._pace_gemini(api_key)
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                f"?key={urllib.parse.quote(api_key)}"
            )
            body = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": generation,
            }).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
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
            return (
                raw.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )

        return get_key_pool().call_with_rotation(
            "gemini", _do, progress=progress_callback, max_cooldown_waits=3
        )

    @staticmethod
    def _try_skill_prompt(
        source_text: str,
        *,
        source_lang: str,
        emotion: str,
        register: str,
        speaker_id: str,
        listener_id: str,
    ) -> str | None:
        try:
            from claynext.prompts import get_registry

            skill = get_registry().get("ksld.gemini_candidates")
            rendered = skill.render({
                "source_language": source_lang,
                "source_text": source_text,
                "emotion": emotion,
                "register": register,
                "speaker_id": speaker_id,
                "listener_id": listener_id,
            })
            return getattr(rendered, "text", None) or str(rendered)
        except Exception:
            return None

    @staticmethod
    def _build_candidate_prompt(
        source_text: str,
        *,
        source_lang: str,
        emotion: str,
        register: str,
        speaker_id: str,
        listener_id: str,
    ) -> str:
        return (
            "You are a native Khmer dialogue coach for film dubbing.\n"
            "Produce THREE spoken-Khmer translation candidates for the source line.\n"
            "Return JSON only: {\"candidates\":[{\"text\":\"...\",\"style\":\"natural|slang|character\","
            "\"register\":\"...\",\"emotion\":\"...\",\"notes\":\"...\"}]}\n"
            "Rules: natural spoken Khmer (not textbook); keep meaning; mark uncertain "
            "pronouns in notes; never claim the output is gold/verified.\n"
            f"source_language: {source_lang}\n"
            f"speaker: {speaker_id or 'A'} → listener: {listener_id or 'B'}\n"
            f"emotion: {emotion}; register: {register}\n"
            f"source_text: {source_text}\n"
        )

    @staticmethod
    def _parse_candidates(text: str) -> list[dict[str, Any]]:
        text = (text or "").strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Strip markdown fences if present.
            if "```" in text:
                inner = text.split("```", 2)
                chunk = inner[1] if len(inner) > 1 else text
                if chunk.lstrip().startswith("json"):
                    chunk = chunk.lstrip()[4:]
                try:
                    data = json.loads(chunk.strip())
                except json.JSONDecodeError:
                    return [{"text": text, "style": "natural", "notes": "unparsed"}]
            else:
                return [{"text": text, "style": "natural", "notes": "unparsed"}]
        if isinstance(data, dict):
            rows = data.get("candidates") or data.get("lines") or []
            if isinstance(rows, list):
                out = []
                for row in rows:
                    if isinstance(row, str):
                        out.append({"text": row, "style": "natural"})
                    elif isinstance(row, dict) and row.get("text"):
                        out.append(row)
                return out
        if isinstance(data, list):
            return [
                {"text": r, "style": "natural"} if isinstance(r, str) else r
                for r in data
                if (isinstance(r, str) and r) or (isinstance(r, dict) and r.get("text"))
            ]
        return []
