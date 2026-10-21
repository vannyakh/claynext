"""SGLang-Omni provider.

The server speaks the OpenAI audio and chat APIs. Capabilities come from
``GET /v1/models``. A Whisper-only server can transcribe and is not offered
for translation or voices. Timing and the final mix stay on the normal path.
"""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from claynext.models.ai_provider import ProviderCapabilities, ProviderError
from claynext.utils.job_control import JobCancelled

DEFAULT_URL = "http://127.0.0.1:8000"
_PROBE_TTL = 30.0

_ASR_NEEDLES = ("whisper", "asr", "transcribe")
_CHAT_NEEDLES = ("qwen", "llama", "gemma", "chat", "instruct")
_TTS_NEEDLES = ("tts", "speech", "vox", "fish", "higgs", "moss")
_NOT_CHAT = ("whisper", "tts", "asr", "transcribe", "speech")
_NOT_ASR = ("tts", "speech")

_provider: SGLangOmniProvider | None = None


def base_url() -> str:
    env = (os.environ.get("SGLANG_OMNI_URL") or "").strip()
    if env:
        return env.rstrip("/")
    try:
        from claynext.models.features import get_feature_setting

        saved = (get_feature_setting("sglang_omni_url", DEFAULT_URL) or "").strip()
        if saved:
            return saved.rstrip("/")
    except Exception:
        pass
    return DEFAULT_URL


def get_provider() -> SGLangOmniProvider:
    global _provider
    url = base_url()
    if _provider is None or _provider.endpoint != url:
        _provider = SGLangOmniProvider(url)
    return _provider


def reset_provider() -> None:
    """Drop the cached health probe. Tests and a URL change use this."""
    global _provider
    _provider = None


def available() -> bool:
    return get_provider().available()


def can_translate() -> bool:
    try:
        return get_provider().capabilities().supports("translate")
    except Exception:
        return False


def transcribe(media_path: str, language: str = "Auto Detect", *, control: Any = None) -> list[dict[str, Any]]:
    return get_provider().transcribe(media_path, language, control=control)


def chat(prompt: str, *, control: Any = None) -> str:
    return get_provider().complete(prompt, control=control)


def synthesize(text: str, output_path: str, *, voice: str = "female", control: Any = None) -> str:
    return get_provider().speak(text, output_path, voice=voice, control=control)


class SGLangOmniProvider:
    provider_id = "sglang-omni"

    def __init__(self, endpoint: str | None = None):
        self.endpoint = (endpoint or base_url()).rstrip("/")
        self._probed_at = 0.0
        self._caps = ProviderCapabilities()
        self._probe_ok = False

    def available(self) -> bool:
        try:
            self.capabilities()
        except Exception:
            return False
        return self._probe_ok and bool(self._caps.models)

    def capabilities(self) -> ProviderCapabilities:
        now = time.monotonic()
        if now - self._probed_at < _PROBE_TTL:
            return self._caps
        self._probed_at = now
        try:
            models = tuple(self._model_ids())
            self._probe_ok = True
        except ProviderError:
            self._probe_ok = False
            self._caps = ProviderCapabilities()
            return self._caps
        self._caps = ProviderCapabilities(
            models=models,
            transcribe=_match(models, "asr"),
            translate=_match(models, "chat"),
            speak=_match(models, "tts"),
        )
        return self._caps

    def transcribe(
        self,
        media_path: str,
        language: str = "Auto Detect",
        *,
        control: Any = None,
    ) -> list[dict[str, Any]]:
        _checkpoint(control)
        model = self._require("transcribe")
        path = Path(media_path)
        fields = {"model": model, "response_format": "verbose_json"}
        code = _lang_code(language)
        if code:
            fields["language"] = code
        raw = self._multipart(
            "/v1/audio/transcriptions",
            fields,
            {"file": (path.name or "audio.wav", path.read_bytes(), "application/octet-stream")},
            timeout=300,
            control=control,
        )
        return _transcript_rows(raw)

    def complete(self, prompt: str, *, control: Any = None) -> str:
        _checkpoint(control)
        model = self._require("translate")
        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "You translate movie dialogue. Reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }).encode("utf-8")
        raw = self._request(
            "/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            timeout=180,
            control=control,
        )
        data = _json_object(raw, "SGLang-Omni chat returned a response that is not JSON.")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError("SGLang-Omni chat returned no choices.", code="empty", provider=self.provider_id)
        text = str(((choices[0] or {}).get("message") or {}).get("content") or "").strip()
        if not text:
            raise ProviderError("SGLang-Omni chat returned an empty reply.", code="empty", provider=self.provider_id)
        return text

    def speak(
        self,
        text: str,
        output_path: str,
        *,
        voice: str = "",
        control: Any = None,
    ) -> str:
        _checkpoint(control)
        spoken = (text or "").strip()
        if not spoken:
            raise ProviderError("No text to speak.", code="empty", provider=self.provider_id)
        model = self._require("speak")
        body = json.dumps({
            "model": model,
            "input": spoken,
            "voice": voice or "female",
            "response_format": "wav",
        }).encode("utf-8")
        audio = self._request(
            "/v1/audio/speech",
            data=body,
            headers={"Content-Type": "application/json"},
            timeout=180,
            control=control,
        )
        if not audio:
            raise ProviderError("SGLang-Omni speech returned empty audio.", code="empty", provider=self.provider_id)
        return _write_audio(audio, output_path)

    def _require(self, kind: str) -> str:
        caps = self.capabilities()
        model = getattr(caps, kind, None)
        if model:
            return str(model)
        label = {"transcribe": "transcription", "translate": "translation", "speak": "speech"}.get(kind, kind)
        raise ProviderError(
            f"SGLang-Omni at {self.endpoint} has no {label} model in /v1/models.",
            code="capability",
            provider=self.provider_id,
        )

    def _model_ids(self) -> list[str]:
        raw = self._request("/v1/models", timeout=1.5, retry=False)
        data = _json_object(raw, "SGLang-Omni /v1/models did not return JSON.")
        rows = data.get("data")
        ids: list[str] = []
        for row in rows or []:
            if isinstance(row, dict) and row.get("id"):
                ids.append(str(row["id"]))
        return ids

    def _request(
        self,
        path: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30,
        control: Any = None,
        retry: bool = True,
    ) -> bytes:
        attempts = 2 if retry else 1
        last = "request failed"
        for attempt in range(attempts):
            _checkpoint(control)
            req = urllib.request.Request(
                self.endpoint + path,
                data=data,
                headers=headers or {},
                method="POST" if data is not None else "GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read()
            except JobCancelled:
                raise
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
                if exc.code in {502, 503, 504} and attempt + 1 < attempts:
                    last = f"{exc.code} {detail}"
                    continue
                code = "capability" if exc.code == 400 else "http"
                raise ProviderError(
                    f"SGLang-Omni {path}: {exc.code} {detail}",
                    code=code,
                    provider=self.provider_id,
                ) from exc
            except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
                last = str(getattr(exc, "reason", exc) or exc)
                if attempt + 1 < attempts:
                    continue
                offline = isinstance(exc, urllib.error.URLError) and not isinstance(getattr(exc, "reason", None), socket.timeout)
                code = "unavailable" if offline else "timeout"
                if code == "unavailable":
                    message = (
                        f"SGLang-Omni is not running at {self.endpoint}. "
                        "Start it with: sgl-omni serve --model-path <model> --port 8000"
                    )
                else:
                    message = f"SGLang-Omni timed out at {self.endpoint}: {last}"
                raise ProviderError(message, code=code, provider=self.provider_id) from exc
        raise ProviderError(f"SGLang-Omni failed at {self.endpoint}: {last}", code="unavailable", provider=self.provider_id)

    def _multipart(
        self,
        path: str,
        fields: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
        *,
        timeout: float,
        control: Any = None,
    ) -> bytes:
        boundary = f"----claynext-{uuid.uuid4().hex}"
        chunks: list[bytes] = []
        for key, value in fields.items():
            chunks.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
            )
        for key, (filename, payload, mime) in files.items():
            chunks.append(
                (
                    f"--{boundary}\r\n"
                    f"Content-Disposition: form-data; name=\"{key}\"; filename=\"{filename}\"\r\n"
                    f"Content-Type: {mime}\r\n\r\n"
                ).encode()
            )
            chunks.append(payload)
            chunks.append(b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode())
        return self._request(
            path,
            data=b"".join(chunks),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            timeout=timeout,
            control=control,
        )


def _checkpoint(control: Any) -> None:
    if control is not None and hasattr(control, "checkpoint"):
        control.checkpoint()


def _env_model(kind: str) -> str:
    name = {"asr": "SGLANG_OMNI_ASR_MODEL", "chat": "SGLANG_OMNI_CHAT_MODEL", "tts": "SGLANG_OMNI_TTS_MODEL"}[kind]
    return (os.environ.get(name) or "").strip()


def _match(models: tuple[str, ...], kind: str) -> str | None:
    forced = _env_model(kind)
    if forced:
        if not models or forced in models:
            return forced
        return None
    for item in models:
        low = item.lower()
        if kind == "asr" and any(n in low for n in _ASR_NEEDLES) and not any(n in low for n in _NOT_ASR):
            return item
        if kind == "chat" and any(n in low for n in _CHAT_NEEDLES) and not any(n in low for n in _NOT_CHAT):
            return item
        if kind == "tts" and any(n in low for n in _TTS_NEEDLES):
            return item
    return None


def _lang_code(language: str) -> str:
    key = (language or "").strip().lower()
    codes = {
        "chinese": "zh",
        "english": "en",
        "khmer": "km",
        "vietnamese": "vi",
        "japanese": "ja",
        "korean": "ko",
        "thai": "th",
        "french": "fr",
        "german": "de",
        "spanish": "es",
        "russian": "ru",
    }
    if key in {"", "auto", "auto detect"}:
        return ""
    return codes.get(key, key[:8])


def _clock(seconds: float) -> str:
    sec = max(0.0, float(seconds))
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    whole = int(sec % 60)
    millis = int(round((sec - int(sec)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{whole:02d},{millis:03d}"


def _json_object(raw: bytes, message: str) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ProviderError(message, code="empty", provider="sglang-omni") from exc
    if not isinstance(data, dict):
        raise ProviderError(message, code="empty", provider="sglang-omni")
    return data


def _transcript_rows(raw: bytes) -> list[dict[str, Any]]:
    data = _json_object(raw, "SGLang-Omni transcription was not JSON.")
    segments = data.get("segments")
    rows: list[dict[str, Any]] = []
    if isinstance(segments, list) and segments:
        for item in segments:
            if not isinstance(item, dict):
                continue
            text = " ".join(str(item.get("text") or "").split()).strip()
            if not text:
                continue
            rows.append({
                "id": len(rows) + 1,
                "start": _clock(float(item.get("start") or 0)),
                "end": _clock(float(item.get("end") or 0)),
                "speaker": str(item.get("speaker") or ""),
                "text": text,
                "confidence": 0.85,
                "source": "sglang-omni",
            })
    elif str(data.get("text") or "").strip():
        rows.append({
            "id": 1,
            "start": "00:00:00,000",
            "end": _clock(float(data.get("duration") or 1)),
            "speaker": "",
            "text": " ".join(str(data["text"]).split()),
            "confidence": 0.8,
            "source": "sglang-omni",
        })
    if not rows:
        raise ProviderError("SGLang-Omni returned no transcript lines.", code="empty", provider="sglang-omni")
    return rows


def _write_audio(audio: bytes, output_path: str) -> str:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    wav_out = target if target.suffix.lower() == ".wav" else target.with_suffix(".wav")
    wav_out.write_bytes(audio)
    if target.suffix.lower() == ".mp3":
        from claynext.adapters.ffmpeg_adapter import run_ffmpeg

        ok = run_ffmpeg([
            "-y", "-i", str(wav_out),
            "-codec:a", "libmp3lame", "-q:a", "2",
            str(target),
        ])
        if not ok or not target.is_file():
            raise ProviderError("Failed to encode SGLang-Omni speech to MP3.", code="http", provider="sglang-omni")
        try:
            wav_out.unlink()
        except Exception:
            pass
        return str(target)
    return str(wav_out)
