from __future__ import annotations

import asyncio
import math
import os
import struct
import subprocess
import threading
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List

import edge_tts

_kitten_lock = threading.Lock()
_kitten_models: dict[str, Any] = {}
_voxcpm_lock = threading.Lock()
_voxcpm_models: dict[str, Any] = {}
_edge_endpoint_ready = False


def _ensure_edge_tts_endpoint() -> None:
    """Point edge-tts at the current Microsoft host (legacy Bing WSS returns 403)."""
    global _edge_endpoint_ready
    if _edge_endpoint_ready:
        return
    try:
        import edge_tts.communicate as edge_communicate
        from edge_tts.constants import TRUSTED_CLIENT_TOKEN

        # speech.platform.bing.com rejects Sec-MS-GEC v1; msedgeservices accepts it.
        # See: https://github.com/rany2/edge-tts/issues/490
        edge_communicate.WSS_URL = (
            "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
            f"?Ocp-Apim-Subscription-Key={TRUSTED_CLIENT_TOKEN}"
        )
        _edge_endpoint_ready = True
    except Exception:
        # Keep package default; synthesize will surface the network error.
        _edge_endpoint_ready = True


def voice_display_fallback(voice_id: str) -> str:
    """Derive a short label from a raw voice id when not in the catalog."""
    if not voice_id:
        return "Voice"
    stem = voice_id.split("/")[-1].replace("Neural", "")
    skip = {
        "edge", "kitten", "voxcpm", "en", "us", "km", "kh", "vi", "vn",
        "ja", "jp", "ko", "kr", "zh", "cn", "female", "male",
    }
    for part in reversed(stem.replace("_", "-").split("-")):
        if part.isalpha() and len(part) >= 3 and part.lower() not in skip:
            return part[:1].upper() + part[1:]
    return stem or "Voice"


class TTSEngine:
    """
    Text-to-Speech engine: KittenTTS (CPU ONNX), Edge TTS (online), and VoxCPM (local neural).
    """
    PROVIDERS = [
        "KittenTTS (Local CPU/ONNX)",
        "Microsoft Edge TTS (Online Free)",
        "VoxCPM (Local Neural · Multilingual)",
    ]

    KITTEN_MODELS = [
        ("KittenML/kitten-tts-nano-0.8-fp32", "Kitten Nano (15M · Ultra-Fast CPU)"),
        ("KittenML/kitten-tts-nano-0.8-int8", "Kitten Nano (15M INT8 · Quantized)"),
        ("KittenML/kitten-tts-micro-0.8", "Kitten Micro (40M · Balanced)"),
        ("KittenML/kitten-tts-mini-0.8", "Kitten Mini (80M · High Quality)"),
    ]

    VOXCPM_MODELS = [
        ("openbmb/VoxCPM2", "VoxCPM2 (2B · 30 languages · 48kHz)"),
        ("openbmb/VoxCPM1.5", "VoxCPM1.5 (Balanced · Cloning)"),
        ("openbmb/VoxCPM-0.5B", "VoxCPM 0.5B (Lighter · Faster)"),
    ]
    VOXCPM_DEFAULT_MODEL = "openbmb/VoxCPM2"

    # ``name`` / ``alias`` = short character label only (no engine/model prefix).
    # Engine lives in ``tag``; language / gender stay as separate fields.
    KITTEN_VOICES = [
        {"id": "kitten-Bella", "name": "Bella", "lang": "English", "tag": "KittenTTS", "gender": "Female", "alias": "Bella"},
        {"id": "kitten-Jasper", "name": "Jasper", "lang": "English", "tag": "KittenTTS", "gender": "Male", "alias": "Jasper"},
        {"id": "kitten-Luna", "name": "Luna", "lang": "English", "tag": "KittenTTS", "gender": "Female", "alias": "Luna"},
        {"id": "kitten-Bruno", "name": "Bruno", "lang": "English", "tag": "KittenTTS", "gender": "Male", "alias": "Bruno"},
        {"id": "kitten-Rosie", "name": "Rosie", "lang": "English", "tag": "KittenTTS", "gender": "Female", "alias": "Rosie"},
        {"id": "kitten-Hugo", "name": "Hugo", "lang": "English", "tag": "KittenTTS", "gender": "Male", "alias": "Hugo"},
        {"id": "kitten-Kiki", "name": "Kiki", "lang": "English", "tag": "KittenTTS", "gender": "Female", "alias": "Kiki"},
        {"id": "kitten-Leo", "name": "Leo", "lang": "English", "tag": "KittenTTS", "gender": "Male", "alias": "Leo"},
    ]

    # Voice Design prompts — VoxCPM synthesizes from the parenthetical description.
    VOXCPM_VOICES = [
        {
            "id": "voxcpm-khmer-female",
            "name": "Sreynich",
            "alias": "Sreynich",
            "lang": "Khmer",
            "tag": "VoxCPM",
            "gender": "Female",
            "design": "A young Khmer woman, clear natural voice, warm and steady",
        },
        {
            "id": "voxcpm-khmer-male",
            "name": "Vichea",
            "alias": "Vichea",
            "lang": "Khmer",
            "tag": "VoxCPM",
            "gender": "Male",
            "design": "A Khmer man, clear natural voice, calm and confident",
        },
        {
            "id": "voxcpm-en-female",
            "name": "Ava",
            "alias": "Ava",
            "lang": "English",
            "tag": "VoxCPM",
            "gender": "Female",
            "design": "A young woman, gentle and sweet voice, natural American English",
        },
        {
            "id": "voxcpm-en-male",
            "name": "Noah",
            "alias": "Noah",
            "lang": "English",
            "tag": "VoxCPM",
            "gender": "Male",
            "design": "A young man, warm clear voice, natural American English",
        },
        {
            "id": "voxcpm-vi-female",
            "name": "Linh",
            "alias": "Linh",
            "lang": "Vietnamese",
            "tag": "VoxCPM",
            "gender": "Female",
            "design": "A young Vietnamese woman, soft clear voice",
        },
        {
            "id": "voxcpm-vi-male",
            "name": "Minh",
            "alias": "Minh",
            "lang": "Vietnamese",
            "tag": "VoxCPM",
            "gender": "Male",
            "design": "A Vietnamese man, clear natural voice",
        },
        {
            "id": "voxcpm-zh-female",
            "name": "Xiaoxuan",
            "alias": "Xiaoxuan",
            "lang": "Chinese",
            "tag": "VoxCPM",
            "gender": "Female",
            "design": "A young Chinese woman, gentle and clear Mandarin voice",
        },
        {
            "id": "voxcpm-ja-female",
            "name": "Hana",
            "alias": "Hana",
            "lang": "Japanese",
            "tag": "VoxCPM",
            "gender": "Female",
            "design": "A young Japanese woman, soft expressive voice",
        },
    ]

    EDGE_VOICES = [
        {"id": "km-KH-SreymomNeural", "name": "Sreymom", "alias": "Sreymom", "lang": "Khmer", "tag": "Neural", "gender": "Female"},
        {"id": "km-KH-PisethNeural", "name": "Piseth", "alias": "Piseth", "lang": "Khmer", "tag": "Neural", "gender": "Male"},
        {"id": "en-US-AvaNeural", "name": "Ava", "alias": "Ava", "lang": "English", "tag": "Neural", "gender": "Female"},
        {"id": "en-US-AndrewNeural", "name": "Andrew", "alias": "Andrew", "lang": "English", "tag": "Neural", "gender": "Male"},
        {"id": "vi-VN-HoaiMyNeural", "name": "Hoài My", "alias": "Hoài My", "lang": "Vietnamese", "tag": "Neural", "gender": "Female"},
        {"id": "vi-VN-NamMinhNeural", "name": "Nam Minh", "alias": "Nam Minh", "lang": "Vietnamese", "tag": "Neural", "gender": "Male"},
        {"id": "ja-JP-NanamiNeural", "name": "Nanami", "alias": "Nanami", "lang": "Japanese", "tag": "Anime/Neural", "gender": "Female"},
        {"id": "ko-KR-SunHiNeural", "name": "Sun-Hi", "alias": "Sun-Hi", "lang": "Korean", "tag": "K-Drama", "gender": "Female"},
        {"id": "zh-CN-XiaoxiaoNeural", "name": "Xiaoxiao", "alias": "Xiaoxiao", "lang": "Chinese", "tag": "Neural", "gender": "Female"},
    ]

    VOICE_PRESETS = KITTEN_VOICES + VOXCPM_VOICES + EDGE_VOICES

    @staticmethod
    def _is_kitten_voice(voice_id: str) -> bool:
        if not voice_id:
            return False
        if voice_id.startswith("kitten-"):
            return True
        return voice_id in {"Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"}

    @staticmethod
    def _is_voxcpm_voice(voice_id: str) -> bool:
        if not voice_id:
            return False
        if voice_id.startswith("voxcpm-"):
            return True
        return any(v["id"] == voice_id for v in TTSEngine.VOXCPM_VOICES)

    @staticmethod
    def _is_edge_voice(voice_id: str) -> bool:
        if not voice_id:
            return False
        return voice_id[:3] in {"en-", "vi-", "ja-", "ko-", "zh-", "es-", "fr-", "de-", "th-", "ru-", "km-"}

    @staticmethod
    def kitten_voices() -> List[Dict[str, Any]]:
        return list(TTSEngine.KITTEN_VOICES)

    @staticmethod
    def voxcpm_voices() -> List[Dict[str, Any]]:
        return list(TTSEngine.VOXCPM_VOICES)

    @staticmethod
    def edge_voices() -> List[Dict[str, Any]]:
        return list(TTSEngine.EDGE_VOICES)

    @staticmethod
    def voice_label(voice: dict[str, Any] | str) -> str:
        """Short character name only (no engine / model prefix)."""
        if isinstance(voice, str):
            for item in TTSEngine.VOICE_PRESETS:
                if item.get("id") == voice:
                    return TTSEngine.voice_label(item)
            return voice_display_fallback(voice)
        alias = str(voice.get("alias") or "").strip()
        if alias:
            return alias
        name = str(voice.get("name") or "").strip()
        if name:
            # Strip legacy "Engine - Name (…)" if any old cached rows appear
            if " - " in name:
                name = name.split(" - ", 1)[1]
            if "(" in name:
                name = name.split("(", 1)[0]
            name = name.strip()
            if name:
                return name
        return voice_display_fallback(str(voice.get("id") or "Voice"))

    @staticmethod
    def list_voices(lang: str | None = None) -> List[Dict[str, Any]]:
        """
        Core voice catalog for UI / cast / CLI.

        Each row: ``id``, ``name`` (short label), ``lang``, ``tag`` (engine),
        ``gender``. Optional ``lang`` filters by language (Chinese* → Chinese).
        """
        want = ""
        if lang:
            want = "Chinese" if str(lang).startswith("Chinese") else str(lang)
        rows: list[dict[str, Any]] = []
        for voice in TTSEngine.VOICE_PRESETS:
            if want and str(voice.get("lang") or "") != want:
                continue
            vid = str(voice.get("id") or "")
            if not vid:
                continue
            rows.append({
                "id": vid,
                "name": TTSEngine.voice_label(voice),
                "lang": str(voice.get("lang") or ""),
                "tag": str(voice.get("tag") or ""),
                "gender": str(voice.get("gender") or ""),
                "alias": str(voice.get("alias") or TTSEngine.voice_label(voice)),
                "design": voice.get("design") or "",
            })
        if want and not rows:
            return TTSEngine.list_voices(None)
        return rows

    @staticmethod
    def voxcpm_available() -> bool:
        try:
            import voxcpm  # noqa: F401
            return True
        except Exception:
            return False

    @staticmethod
    def _voxcpm_voice_meta(voice_id: str) -> dict[str, Any]:
        for voice in TTSEngine.VOXCPM_VOICES:
            if voice["id"] == voice_id:
                return voice
        return TTSEngine.VOXCPM_VOICES[0]

    @staticmethod
    def synthesize(
        text: str,
        voice_id: str,
        output_path: str,
        *,
        speed: float = 1.0,
        pitch: float = 0.0,
        model_name: str = "",
        reference_wav: str = "",
        progress_callback: Callable | None = None,
        allow_expression_tags: bool = True,
    ) -> str:
        """Route to Kitten / VoxCPM / Edge based on voice id.

        When ``allow_expression_tags`` is True (default), inline cues like
        ``[laugh]`` / ``[sigh]`` / ``[excited]`` are expanded before speaking.
        """
        if allow_expression_tags:
            from claynext.models.tts_expression import has_expression_tags, synthesize_with_tags

            if has_expression_tags(text or ""):
                return synthesize_with_tags(
                    text,
                    voice_id,
                    output_path,
                    speed=speed,
                    pitch=pitch,
                    model_name=model_name,
                    reference_wav=reference_wav,
                    progress_callback=progress_callback,
                )
        return TTSEngine._synthesize_plain(
            text,
            voice_id,
            output_path,
            speed=speed,
            pitch=pitch,
            model_name=model_name,
            reference_wav=reference_wav,
            progress_callback=progress_callback,
        )

    @staticmethod
    def _synthesize_plain(
        text: str,
        voice_id: str,
        output_path: str,
        *,
        speed: float = 1.0,
        pitch: float = 0.0,
        model_name: str = "",
        reference_wav: str = "",
        progress_callback: Callable | None = None,
    ) -> str:
        """Engine dispatch without expression-tag expansion."""
        if TTSEngine._is_voxcpm_voice(voice_id):
            return TTSEngine.synthesize_voxcpm(
                text,
                voice_id,
                output_path,
                model_name=model_name or TTSEngine.VOXCPM_DEFAULT_MODEL,
                reference_wav=reference_wav,
                progress_callback=progress_callback,
            )
        if TTSEngine._is_kitten_voice(voice_id):
            return TTSEngine.synthesize_kitten(
                text,
                voice_id,
                output_path,
                speed=speed,
                model_name=model_name or "KittenML/kitten-tts-nano-0.8-fp32",
                progress_callback=progress_callback,
            )
        return TTSEngine.synthesize_edge(
            text,
            voice_id,
            output_path,
            speed=speed,
            pitch=pitch,
            progress_callback=progress_callback,
        )

    @staticmethod
    def is_kitten_model_downloaded(model_name: str) -> bool:
        from claynext.models.hf_hub import is_model_downloaded
        return is_model_downloaded(model_name)

    @staticmethod
    def pull_kitten_model(
        model_name: str,
        progress_callback: Callable | None = None,
    ) -> Any:
        from claynext.models.hf_hub import pull_model
        pull_model(model_name, progress_callback)
        return TTSEngine.get_kitten_model(model_name, progress_callback)

    @staticmethod
    def get_kitten_model(
        model_name: str = "KittenML/kitten-tts-nano-0.8-fp32",
        progress_callback: Callable | None = None,
    ) -> Any:
        with _kitten_lock:
            if model_name in _kitten_models:
                return _kitten_models[model_name]

            from claynext.utils.config import MODELS_DIR
            from claynext.models.hf_hub import is_model_downloaded, pull_model

            if not is_model_downloaded(model_name):
                if progress_callback:
                    progress_callback(10, f"Pulling {model_name} from Hugging Face…")
                pull_model(model_name, progress_callback)

            if progress_callback:
                progress_callback(30, f"Loading KittenTTS ({model_name})…")

            from kittentts import KittenTTS
            try:
                model = KittenTTS(model_name, cache_dir=str(MODELS_DIR))
            except Exception:
                try:
                    model = KittenTTS(model_name)
                except Exception:
                    alt = "KittenML/kitten-tts-nano-0.8-fp32" if "fp32" not in model_name else "KittenML/kitten-tts-micro-0.8"
                    model = KittenTTS(alt)
                    _kitten_models[alt] = model

            _kitten_models[model_name] = model
            return model

    @staticmethod
    def get_voxcpm_model(
        model_name: str = VOXCPM_DEFAULT_MODEL,
        progress_callback: Callable | None = None,
    ) -> Any:
        """Lazy-load a VoxCPM model (optional dependency: `uv sync --extra voxcpm`)."""
        if not TTSEngine.voxcpm_available():
            raise RuntimeError(
                "VoxCPM is not installed. Run: uv sync --extra voxcpm\n"
                "Requires Python 3.10–3.12, PyTorch ≥ 2.5, and preferably CUDA."
            )
        with _voxcpm_lock:
            if model_name in _voxcpm_models:
                return _voxcpm_models[model_name]
            if progress_callback:
                progress_callback(20, f"Loading VoxCPM ({model_name})… first run downloads weights")
            from voxcpm import VoxCPM

            model = VoxCPM.from_pretrained(model_name, load_denoiser=False)
            _voxcpm_models[model_name] = model
            if progress_callback:
                progress_callback(45, "VoxCPM model ready")
            return model

    @staticmethod
    def synthesize_voxcpm(
        text: str,
        voice_id: str,
        output_path: str,
        *,
        model_name: str = VOXCPM_DEFAULT_MODEL,
        reference_wav: str = "",
        cfg_value: float = 2.0,
        inference_timesteps: int = 10,
        seed: int = 42,
        progress_callback: Callable | None = None,
    ) -> str:
        """Synthesize with VoxCPM Voice Design (or optional reference clone)."""
        raw = (text or "").strip()
        if not raw:
            raise RuntimeError("No text to speak.")

        meta = TTSEngine._voxcpm_voice_meta(voice_id)
        design = str(meta.get("design") or "").strip()
        speak = f"({design}){raw}" if design and not reference_wav else raw
        label = meta.get("name") or voice_id

        if progress_callback:
            progress_callback(25, f"Synthesizing with VoxCPM [{label}]…")

        model = TTSEngine.get_voxcpm_model(model_name or TTSEngine.VOXCPM_DEFAULT_MODEL, progress_callback)
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        wav_out = str(target.with_suffix(".wav"))

        if progress_callback:
            progress_callback(55, "Generating neural speech (VoxCPM)…")

        kwargs: dict[str, Any] = {
            "text": speak,
            "cfg_value": float(cfg_value),
            "inference_timesteps": int(inference_timesteps),
            "seed": int(seed),
        }
        if reference_wav and os.path.isfile(reference_wav):
            kwargs["reference_wav_path"] = reference_wav

        wav = model.generate(**kwargs)
        import soundfile as sf

        rate = int(getattr(getattr(model, "tts_model", None), "sample_rate", None) or 48000)
        sf.write(wav_out, wav, rate)

        if output_path.lower().endswith(".mp3"):
            if progress_callback:
                progress_callback(85, "Encoding to MP3…")
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                ffmpeg_exe = "ffmpeg"
            cmd = [
                ffmpeg_exe, "-hide_banner", "-loglevel", "error", "-y",
                "-i", wav_out,
                "-codec:a", "libmp3lame", "-q:a", "2",
                output_path,
            ]
            subprocess.run(cmd, check=True)
            if os.path.exists(wav_out) and wav_out != output_path:
                try:
                    os.remove(wav_out)
                except Exception:
                    pass
            actual_path = output_path
        else:
            actual_path = wav_out

        if progress_callback:
            progress_callback(100, f"VoxCPM speech ready [{label}]")
        return actual_path

    @staticmethod
    def synthesize_kitten(
        text: str,
        voice_id: str,
        output_path: str,
        speed: float = 1.0,
        model_name: str = "KittenML/kitten-tts-nano-0.8-fp32",
        progress_callback: Callable | None = None,
    ) -> str:
        raw = (text or "").strip()
        if not raw:
            raise RuntimeError("No text to speak.")

        alias = voice_id.replace("kitten-", "") if voice_id.startswith("kitten-") else voice_id
        valid_aliases = {"Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"}
        if alias not in valid_aliases:
            alias = "Bella"

        if progress_callback:
            progress_callback(25, f"Synthesizing with KittenTTS [{alias}]…")

        model = TTSEngine.get_kitten_model(model_name, progress_callback)
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        wav_out = str(target.with_suffix(".wav"))

        if progress_callback:
            progress_callback(55, "Generating speech waveform (CPU ONNX)…")

        audio = model.generate(raw, voice=alias, speed=speed)
        import soundfile as sf
        sf.write(wav_out, audio, 24000)

        # If user explicitly requested .mp3, convert via FFmpeg
        if output_path.lower().endswith(".mp3"):
            if progress_callback:
                progress_callback(85, "Encoding to MP3…")
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                ffmpeg_exe = "ffmpeg"
            cmd = [
                ffmpeg_exe, "-hide_banner", "-loglevel", "error", "-y",
                "-i", wav_out,
                "-codec:a", "libmp3lame", "-q:a", "2",
                output_path,
            ]
            subprocess.run(cmd, check=True)
            if os.path.exists(wav_out) and wav_out != output_path:
                try:
                    os.remove(wav_out)
                except Exception:
                    pass
            actual_path = output_path
        else:
            actual_path = wav_out

        if progress_callback:
            progress_callback(100, f"KittenTTS speech ready [{alias}]")
        return actual_path

    @staticmethod
    def synthesize_edge(
        text: str,
        voice_id: str,
        output_path: str,
        speed: float = 1.0,
        pitch: float = 0.0,
        progress_callback: Callable | None = None,
    ) -> str:
        raw = (text or "").strip()
        if not raw:
            raise RuntimeError("No text to speak.")
        if not TTSEngine._is_edge_voice(voice_id):
            raise RuntimeError(f"Voice is not an Edge neural voice: {voice_id}")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        rate_str = f"{int((speed - 1.0) * 100):+d}%"
        pitch_str = f"{int(pitch):+d}Hz"
        _ensure_edge_tts_endpoint()
        if progress_callback:
            progress_callback(40, "Streaming Edge TTS…")

        async def _run_edge():
            communicate = edge_tts.Communicate(raw, voice=voice_id, rate=rate_str, pitch=pitch_str)
            await communicate.save(output_path)

        try:
            try:
                asyncio.run(_run_edge())
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(_run_edge())
                finally:
                    loop.close()
        except Exception as exc:
            msg = str(exc)
            if "403" in msg or "Invalid response status" in msg:
                raise RuntimeError(
                    "Edge TTS was rejected by Microsoft (403). "
                    "Check your network/VPN, then retry."
                ) from exc
            raise RuntimeError(f"Edge TTS failed: {exc}") from exc
        if not Path(output_path).is_file() or Path(output_path).stat().st_size == 0:
            raise RuntimeError("Edge TTS did not write an audio file. Check your network connection.")
        if progress_callback:
            progress_callback(100, "Edge TTS speech ready")
        return output_path

    @staticmethod
    def _extract_peaks(file_path: str, count: int = 70) -> list[float]:
        try:
            import soundfile as sf
            import numpy as np
            data, _ = sf.read(file_path)
            if len(data.shape) > 1:
                data = data.mean(axis=1)
            if len(data) == 0:
                return [0.0] * count
            chunk_size = max(1, len(data) // count)
            peaks = []
            for i in range(count):
                chunk = data[i * chunk_size : (i + 1) * chunk_size]
                peaks.append(float(np.abs(chunk).max()) if len(chunk) > 0 else 0.0)
            max_p = max(peaks) if peaks and max(peaks) > 0 else 1.0
            return [p / max_p for p in peaks]
        except Exception:
            return [abs(math.sin(i * 0.15)) * 0.85 for i in range(count)]

    @staticmethod
    def _probe_duration(file_path: str) -> float:
        try:
            import soundfile as sf
            info = sf.info(file_path)
            return float(info.duration)
        except Exception:
            return 2.0

    @staticmethod
    def generate_speech(
        text: str,
        voice_id: str,
        speed: float = 1.0,
        pitch: float = 0.0,
        provider: str = "KittenTTS (Local CPU/ONNX)",
        output_path: str | None = None,
        model_name: str = "KittenML/kitten-tts-nano-0.8-fp32",
        reference_wav: str = "",
        progress_callback: Callable | None = None,
    ) -> Dict[str, Any]:
        """Synthesize text with KittenTTS, VoxCPM, or Edge TTS."""
        if progress_callback:
            progress_callback(10, f"Connecting to {provider} voice '{voice_id}'…")

        use_wav = (
            TTSEngine._is_kitten_voice(voice_id)
            or TTSEngine._is_voxcpm_voice(voice_id)
            or "Kitten" in (provider or "")
            or "VoxCPM" in (provider or "")
        )
        if output_path is None:
            ext = ".wav" if use_wav else ".mp3"
            output_path = str(Path(f"data/outputs/generated_speech{ext}").resolve())

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 1. VoxCPM local neural TTS (multilingual / voice design)
        if TTSEngine._is_voxcpm_voice(voice_id) or "VoxCPM" in (provider or ""):
            try:
                vox_model = model_name if model_name.startswith("openbmb/") else TTSEngine.VOXCPM_DEFAULT_MODEL
                actual_path = TTSEngine.synthesize_voxcpm(
                    text,
                    voice_id,
                    output_path,
                    model_name=vox_model,
                    reference_wav=reference_wav,
                    progress_callback=progress_callback,
                )
                duration = TTSEngine._probe_duration(actual_path)
                peaks = TTSEngine._extract_peaks(actual_path)
                return {
                    "text": text,
                    "duration": duration,
                    "sample_rate": 48000,
                    "wave_peaks": peaks,
                    "file_path": actual_path,
                }
            except Exception as exc:
                if progress_callback:
                    progress_callback(35, f"VoxCPM error: {exc} — trying other engines…")

        # 2. KittenTTS local synthesis
        if TTSEngine._is_kitten_voice(voice_id) or "Kitten" in (provider or ""):
            try:
                kitten_model = model_name if "kitten" in model_name.lower() else "KittenML/kitten-tts-nano-0.8-fp32"
                actual_path = TTSEngine.synthesize_kitten(
                    text, voice_id, output_path, speed=speed, model_name=kitten_model, progress_callback=progress_callback
                )
                duration = TTSEngine._probe_duration(actual_path)
                peaks = TTSEngine._extract_peaks(actual_path)
                return {
                    "text": text,
                    "duration": duration,
                    "sample_rate": 24000,
                    "wave_peaks": peaks,
                    "file_path": actual_path,
                }
            except Exception as exc:
                if progress_callback:
                    progress_callback(40, f"KittenTTS error: {exc} — attempting Edge TTS fallback…")

        # 3. Microsoft Edge TTS online synthesis
        if TTSEngine._is_edge_voice(voice_id) or "Edge" in (provider or ""):
            try:
                edge_voice = voice_id if TTSEngine._is_edge_voice(voice_id) else "en-US-AvaNeural"
                actual_path = TTSEngine.synthesize_edge(
                    text, edge_voice, output_path, speed=speed, pitch=pitch, progress_callback=progress_callback
                )
                duration = TTSEngine._probe_duration(actual_path)
                peaks = TTSEngine._extract_peaks(actual_path)
                return {
                    "text": text,
                    "duration": duration,
                    "sample_rate": 24000,
                    "wave_peaks": peaks,
                    "file_path": actual_path,
                }
            except Exception as exc:
                if progress_callback:
                    progress_callback(60, f"Edge TTS unavailable: {exc} — falling back to local synthesizer…")

        # 4. Fallback tone synthesizer
        sample_rate = 22050
        duration = max(1.5, len(text) * 0.06 / max(0.2, speed))
        num_samples = int(sample_rate * duration)
        base_freq = 220.0 * (2.0 ** (pitch / 12.0))

        raw_samples = []
        wave_peaks = []
        chunk_size = max(1, num_samples // 100)

        for i in range(num_samples):
            t = i / sample_rate
            envelope = math.sin(math.pi * t / duration) ** 2
            vocal_mod = math.sin(2 * math.pi * 5 * t)
            sample_val = math.sin(2 * math.pi * (base_freq + 30 * vocal_mod) * t) * envelope * 0.6
            int_sample = int(sample_val * 32767)
            raw_samples.append(int_sample)

            if i % chunk_size == 0:
                wave_peaks.append(abs(sample_val))

        wav_path = str(Path(output_path).with_suffix(".wav"))
        with wave.open(wav_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            for s in raw_samples:
                wf.writeframes(struct.pack("<h", s))

        if progress_callback:
            progress_callback(100, f"Speech generated successfully ({duration:.2f}s)")

        return {
            "text": text,
            "duration": duration,
            "sample_rate": sample_rate,
            "wave_peaks": wave_peaks,
            "file_path": wav_path,
        }

