from __future__ import annotations

import asyncio
import math
import os
import struct
import threading
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List

try:
    import edge_tts
except ImportError:
    edge_tts = None  # type: ignore[assignment]

_kitten_lock = threading.Lock()
_kitten_models: dict[str, Any] = {}
_voxcpm_lock = threading.Lock()
_voxcpm_models: dict[str, Any] = {}
_omnivoice_lock = threading.Lock()
_omnivoice_models: dict[str, Any] = {}
_edge_endpoint_ready = False


def _seed_voxcpm(seed: int) -> None:
    """VoxCPM dropped the generate(seed=) argument. Seed the RNGs instead."""
    try:
        import numpy as np

        np.random.seed(seed % (2**32))
    except Exception:
        pass
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


def _voxcpm_runtime() -> dict[str, Any]:
    """Device and compile flags for the VoxCPM 2 loader.

    ``optimize`` turns on ``torch.compile``, which is aimed at CUDA. CPU and
    Apple Silicon stay eager so the first synthesis does not fail to compile.
    """
    device = "cpu"
    optimize = False
    try:
        import torch

        if torch.cuda.is_available():
            device = "auto"
            optimize = True
        elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            device = "mps"
    except Exception:
        pass
    return {"device": device, "optimize": optimize}


def _omnivoice_runtime() -> dict[str, Any]:
    """Device map and dtype for k2-fsa/OmniVoice.

    CUDA, Apple Silicon, and Intel Arc use float16. CPU stays on float32.
    """
    device_map = "cpu"
    dtype_name = "float32"
    try:
        import torch

        if torch.cuda.is_available():
            device_map = "cuda:0"
            dtype_name = "float16"
        elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            device_map = "mps"
            dtype_name = "float16"
        elif getattr(torch, "xpu", None) is not None and torch.xpu.is_available():
            device_map = "xpu"
            dtype_name = "float16"
        dtype = getattr(torch, dtype_name)
    except Exception:
        dtype = None
    runtime: dict[str, Any] = {"device_map": device_map}
    if dtype is not None:
        runtime["dtype"] = dtype
    return runtime


def _filter_call(fn: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    import inspect

    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return kwargs
    if any(item.kind == inspect.Parameter.VAR_KEYWORD for item in params.values()):
        return kwargs
    allowed = set(params)
    return {key: value for key, value in kwargs.items() if key in allowed}


def _call_voxcpm(model: Any, **kwargs: Any):
    """Call generate with only the arguments this VoxCPM build accepts."""
    import inspect

    seed = kwargs.get("seed")
    inner = getattr(model, "_generate", None) or getattr(model, "_VoxCPM__generate", None)
    allowed: set[str] | None = None
    if inner is not None:
        try:
            allowed = set(inspect.signature(inner).parameters)
        except (TypeError, ValueError):
            allowed = None
    if allowed is not None:
        kwargs = {key: value for key, value in kwargs.items() if key in allowed}
    if seed is not None and (allowed is None or "seed" not in (allowed or set())):
        _seed_voxcpm(int(seed))
    return model.generate(**kwargs)


def _ensure_edge_tts_endpoint() -> None:
    """Require the current Edge Read Aloud handshake.

    edge-tts 7.2.x sends a v1 Sec-MS-GEC token. Microsoft answers that with 403.
    7.3+ sends the v2 token on the library's own host. Rewriting WSS_URL to
    api.msedgeservices.com keeps the rejection, so this leaves the package URL alone.
    """
    global _edge_endpoint_ready
    if _edge_endpoint_ready:
        return
    from edge_tts.drm import DRM

    token = DRM.generate_sec_ms_gec()
    # v2 tokens are "<16 hex>-<64 hex>". A bare 64-hex digest is the rejected v1 token.
    if "-" not in token:
        raise RuntimeError(
            "Edge TTS client is too old (v1 handshake). "
            "Upgrade with: uv sync  (needs edge-tts>=7.3.1)"
        )
    _edge_endpoint_ready = True


def voice_display_fallback(voice_id: str) -> str:
    """Derive a short label from a raw voice id when not in the catalog."""
    if not voice_id:
        return "Voice"
    stem = voice_id.split("/")[-1].replace("Neural", "")
    skip = {
        "edge", "kitten", "voxcpm", "omnivoice", "eleven", "en", "us", "km", "kh", "vi", "vn",
        "ja", "jp", "ko", "kr", "zh", "cn", "female", "male",
    }
    for part in reversed(stem.replace("_", "-").split("-")):
        if part.isalpha() and len(part) >= 3 and part.lower() not in skip:
            return part[:1].upper() + part[1:]
    return stem or "Voice"


class TTSEngine:
    """
    Text-to-Speech engine: KittenTTS (CPU ONNX), Edge TTS (online), VoxCPM (local neural), OmniVoice, and ElevenLabs.
    """
    PROVIDERS = [
        "KittenTTS (Local CPU/ONNX)",
        "Microsoft Edge TTS (Online Free)",
        "VoxCPM (Local Neural · Multilingual)",
        "OmniVoice (Local · 600 languages)",
        "SGLang-Omni (Server)",
        "ElevenLabs (Online)",
    ]
    ELEVEN_MODEL = "eleven_multilingual_v2"

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

    OMNIVOICE_MODELS = [
        ("k2-fsa/OmniVoice", "OmniVoice (600+ languages · 24 kHz)"),
    ]
    OMNIVOICE_DEFAULT_MODEL = "k2-fsa/OmniVoice"
    OMNIVOICE_SAMPLE_RATE = 24000

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

    # Voice Design prompts. OmniVoice reads ``instruct`` (gender, pitch, accent).
    OMNIVOICE_VOICES = [
        {
            "id": "omnivoice-khmer-female",
            "name": "Sophea",
            "alias": "Sophea",
            "lang": "Khmer",
            "tag": "OmniVoice",
            "gender": "Female",
            "instruct": "female",
        },
        {
            "id": "omnivoice-khmer-male",
            "name": "Dara",
            "alias": "Dara",
            "lang": "Khmer",
            "tag": "OmniVoice",
            "gender": "Male",
            "instruct": "male",
        },
        {
            "id": "omnivoice-en-female",
            "name": "Clara",
            "alias": "Clara",
            "lang": "English",
            "tag": "OmniVoice",
            "gender": "Female",
            "instruct": "female, american accent",
        },
        {
            "id": "omnivoice-en-male",
            "name": "Owen",
            "alias": "Owen",
            "lang": "English",
            "tag": "OmniVoice",
            "gender": "Male",
            "instruct": "male, american accent",
        },
        {
            "id": "omnivoice-vi-female",
            "name": "Mai",
            "alias": "Mai",
            "lang": "Vietnamese",
            "tag": "OmniVoice",
            "gender": "Female",
            "instruct": "female",
        },
        {
            "id": "omnivoice-vi-male",
            "name": "Khoa",
            "alias": "Khoa",
            "lang": "Vietnamese",
            "tag": "OmniVoice",
            "gender": "Male",
            "instruct": "male",
        },
        {
            "id": "omnivoice-zh-female",
            "name": "Yue",
            "alias": "Yue",
            "lang": "Chinese",
            "tag": "OmniVoice",
            "gender": "Female",
            "instruct": "female",
        },
        {
            "id": "omnivoice-ja-female",
            "name": "Aoi",
            "alias": "Aoi",
            "lang": "Japanese",
            "tag": "OmniVoice",
            "gender": "Female",
            "instruct": "female",
        },
    ]

    SGLANG_VOICES = [
        {
            "id": "sglang:female",
            "name": "Aria",
            "alias": "Aria",
            "lang": "All",
            "tag": "SGLang-Omni",
            "gender": "Female",
            "voice": "female",
        },
        {
            "id": "sglang:male",
            "name": "Leo",
            "alias": "Leo",
            "lang": "All",
            "tag": "SGLang-Omni",
            "gender": "Male",
            "voice": "male",
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

    # Premade elevenlabs.io voices. Ids are `eleven:<api voice id>` so they never collide with Edge.
    ELEVEN_VOICES = [
        {"id": "eleven:JBFqnCBsd6RMkjVDRZzb", "name": "George", "alias": "George", "lang": "All", "tag": "ElevenLabs", "gender": "Male"},
        {"id": "eleven:EXAVITQu4vr4xnSDxMaL", "name": "Sarah", "alias": "Sarah", "lang": "All", "tag": "ElevenLabs", "gender": "Female"},
        {"id": "eleven:onwK4e9ZLuTAKqWW03F9", "name": "Daniel", "alias": "Daniel", "lang": "All", "tag": "ElevenLabs", "gender": "Male"},
        {"id": "eleven:XB0fDUnXU5powFXDhCwa", "name": "Charlotte", "alias": "Charlotte", "lang": "All", "tag": "ElevenLabs", "gender": "Female"},
        {"id": "eleven:21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "alias": "Rachel", "lang": "All", "tag": "ElevenLabs", "gender": "Female"},
        {"id": "eleven:pNInz6obpgDQGcFmaJgB", "name": "Adam", "alias": "Adam", "lang": "All", "tag": "ElevenLabs", "gender": "Male"},
        {"id": "eleven:ErXwobaYiN019PkySvjV", "name": "Antoni", "alias": "Antoni", "lang": "All", "tag": "ElevenLabs", "gender": "Male"},
        {"id": "eleven:TxGEqnHWrfWFTfGW9XjX", "name": "Josh", "alias": "Josh", "lang": "All", "tag": "ElevenLabs", "gender": "Male"},
    ]

    CLONE_VOICES = [
        {
            "id": "clone:movie",
            "name": "Actor Clone",
            "alias": "Actor Clone",
            "lang": "All",
            "tag": "Voice Clone",
            "gender": "Matched",
            "design": "Direct zero-shot voice clone & tone matching from movie audio",
        }
    ]

    VOICE_PRESETS = CLONE_VOICES + KITTEN_VOICES + VOXCPM_VOICES + OMNIVOICE_VOICES + SGLANG_VOICES + EDGE_VOICES + ELEVEN_VOICES

    @staticmethod
    def _is_clone_voice(voice_id: str) -> bool:
        if not voice_id:
            return False
        return voice_id.startswith("clone:") or voice_id == "clone:movie"

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
    def _is_omnivoice_voice(voice_id: str) -> bool:
        if not voice_id:
            return False
        if voice_id.startswith("omnivoice-"):
            return True
        return any(v["id"] == voice_id for v in TTSEngine.OMNIVOICE_VOICES)

    @staticmethod
    def _is_sglang_voice(voice_id: str) -> bool:
        return bool(voice_id) and voice_id.startswith("sglang:")

    @staticmethod
    def _is_eleven_voice(voice_id: str) -> bool:
        return bool(voice_id) and voice_id.startswith("eleven:")

    @staticmethod
    def _eleven_api_id(voice_id: str) -> str:
        return voice_id.split(":", 1)[1] if ":" in (voice_id or "") else voice_id

    @staticmethod
    def _is_edge_voice(voice_id: str) -> bool:
        if not voice_id:
            return False
        return voice_id[:3] in {"en-", "vi-", "ja-", "ko-", "zh-", "es-", "fr-", "de-", "th-", "ru-", "km-"}

    @staticmethod
    def clone_voices() -> List[Dict[str, Any]]:
        return list(TTSEngine.CLONE_VOICES)

    @staticmethod
    def kitten_voices() -> List[Dict[str, Any]]:
        return list(TTSEngine.KITTEN_VOICES)

    @staticmethod
    def voxcpm_voices() -> List[Dict[str, Any]]:
        return list(TTSEngine.VOXCPM_VOICES)

    @staticmethod
    def omnivoice_voices() -> List[Dict[str, Any]]:
        return list(TTSEngine.OMNIVOICE_VOICES)

    @staticmethod
    def edge_voices() -> List[Dict[str, Any]]:
        return list(TTSEngine.EDGE_VOICES)

    @staticmethod
    def eleven_voices() -> List[Dict[str, Any]]:
        """Voices this ElevenLabs account can preview. Falls back to the built-in list."""
        live = TTSEngine._account_eleven_voices()
        return live or list(TTSEngine.ELEVEN_VOICES)

    @staticmethod
    def _account_eleven_voices() -> List[Dict[str, Any]]:
        import json
        import time
        import urllib.request

        from claynext.utils.paths import CACHE_DIR

        cache = CACHE_DIR / "eleven_voices.json"
        fresh = False
        cached: list[dict] = []
        try:
            if cache.is_file():
                cached = json.loads(cache.read_text(encoding="utf-8"))
                fresh = time.time() - cache.stat().st_mtime < 12 * 3600
                if fresh and isinstance(cached, list) and cached:
                    return [row for row in cached if isinstance(row, dict) and row.get("id")]
        except Exception:
            cached = []
        try:
            from claynext.models.llm_keys import get_key_pool

            secrets = get_key_pool().secrets("elevenlabs")
            if not secrets:
                return cached
            req = urllib.request.Request(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": secrets[0]},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return cached
        rows: list[dict] = []
        for voice in payload.get("voices") or []:
            vid = str(voice.get("voice_id") or "").strip()
            if not vid:
                continue
            raw_name = str(voice.get("name") or "Voice")
            short = raw_name.split(" - ", 1)[0].strip() or raw_name
            gender = str((voice.get("labels") or {}).get("gender") or "").strip().title()
            rows.append({
                "id": f"eleven:{vid}",
                "name": short,
                "alias": short,
                "lang": "All",
                "tag": "ElevenLabs",
                "gender": gender,
            })
        if not rows:
            return cached
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(rows), encoding="utf-8")
        except Exception:
            pass
        return rows

    @staticmethod
    def voice_label(voice: dict[str, Any] | str) -> str:
        """Short character name only (no engine / model prefix)."""
        if isinstance(voice, str):
            if voice.startswith("clone:") or voice == "clone:movie":
                spk = voice.split(":", 1)[1] if ":" in voice else ""
                return f"Actor Clone ({spk})" if spk and spk != "movie" else "Actor Clone"
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
        catalog = (
            TTSEngine.CLONE_VOICES
            + TTSEngine.KITTEN_VOICES
            + TTSEngine.VOXCPM_VOICES
            + TTSEngine.OMNIVOICE_VOICES
            + TTSEngine.SGLANG_VOICES
            + TTSEngine.EDGE_VOICES
            + TTSEngine.eleven_voices()
        )
        for voice in catalog:
            v_lang = str(voice.get("lang") or "")
            if want and v_lang not in {"All", "all", want}:
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
                "instruct": voice.get("instruct") or "",
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
    def omnivoice_available() -> bool:
        try:
            import omnivoice  # noqa: F401
            return True
        except Exception:
            return False

    @staticmethod
    def _omnivoice_voice_meta(voice_id: str) -> dict[str, Any]:
        for voice in TTSEngine.OMNIVOICE_VOICES:
            if voice["id"] == voice_id:
                return voice
        return TTSEngine.OMNIVOICE_VOICES[0]

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
        control: Any = None,
        performance: dict[str, Any] | None = None,
    ) -> str:
        """Route to Kitten / VoxCPM / OmniVoice / ElevenLabs / Edge based on voice id.

        When ``allow_expression_tags`` is True (default), inline cues like
        ``[laugh]`` / ``[sigh]`` / ``[excited]`` are expanded before speaking.
        ``performance`` (style + intensity from the planner) becomes each
        engine's own controls; the text is spoken unchanged.
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
                    performance=performance,
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
            control=control,
            performance=performance,
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
        control: Any = None,
        performance: dict[str, Any] | None = None,
    ) -> str:
        """Engine dispatch without expression-tag expansion."""
        delivery: dict[str, Any] = {}
        if performance:
            from claynext.models.character_intel.expression_mapper import map_delivery

            delivery = map_delivery(voice_id, performance, has_reference=bool(reference_wav))
        perf_speed = float(delivery.get("speed") or 1.0)
        perf_pitch = float(delivery.get("pitch_hz") or 0.0)
        perf_volume = float(delivery.get("volume_pct") or 0.0)
        style_prompt = str(delivery.get("style_prompt") or "")
        if TTSEngine._is_clone_voice(voice_id):
            if reference_wav and os.path.isfile(reference_wav):
                try:
                    return TTSEngine.synthesize_voxcpm(
                        text,
                        voice_id,
                        output_path,
                        model_name=model_name or TTSEngine.VOXCPM_DEFAULT_MODEL,
                        reference_wav=reference_wav,
                        style_prompt=style_prompt,
                        progress_callback=progress_callback,
                    )
                except Exception:
                    pass  # Fall back to tone-matched neural synthesis
            # Tone-matched neural voice:
            # Pick base neural voice according to detected pitch/gender
            fallback = "km-KH-PisethNeural" if pitch <= 0 else "km-KH-SreymomNeural"
            res_path = TTSEngine.synthesize_edge(
                text,
                fallback,
                output_path,
                speed=speed * perf_speed,
                pitch=pitch + perf_pitch,
                volume=perf_volume,
                progress_callback=progress_callback,
            )
            if reference_wav and os.path.isfile(reference_wav):
                try:
                    from claynext.models.voice_clone import match_timbre_eq
                    match_timbre_eq(res_path, reference_wav, res_path)
                except Exception:
                    pass
            return res_path

        if TTSEngine._is_voxcpm_voice(voice_id):
            return TTSEngine.synthesize_voxcpm(
                text,
                voice_id,
                output_path,
                model_name=model_name or TTSEngine.VOXCPM_DEFAULT_MODEL,
                reference_wav=reference_wav,
                style_prompt=style_prompt,
                progress_callback=progress_callback,
            )
        if TTSEngine._is_omnivoice_voice(voice_id):
            return TTSEngine.synthesize_omnivoice(
                text,
                voice_id,
                output_path,
                speed=speed * perf_speed,
                model_name=model_name or TTSEngine.OMNIVOICE_DEFAULT_MODEL,
                reference_wav=reference_wav,
                instruct_extra=str(delivery.get("instruct_extra") or ""),
                progress_callback=progress_callback,
            )
        if TTSEngine._is_sglang_voice(voice_id):
            return TTSEngine.synthesize_sglang(
                text,
                voice_id,
                output_path,
                progress_callback=progress_callback,
                control=control,
            )
        if TTSEngine._is_eleven_voice(voice_id):
            eleven = delivery.get("eleven") or {}
            return TTSEngine.synthesize_eleven(
                text,
                voice_id,
                output_path,
                speed=speed * perf_speed,
                stability=eleven.get("stability"),
                style=eleven.get("style"),
                progress_callback=progress_callback,
            )
        if TTSEngine._is_kitten_voice(voice_id):
            return TTSEngine.synthesize_kitten(
                text,
                voice_id,
                output_path,
                speed=speed * perf_speed,
                model_name=model_name or "KittenML/kitten-tts-nano-0.8-fp32",
                progress_callback=progress_callback,
            )
        return TTSEngine.synthesize_edge(
            text,
            voice_id,
            output_path,
            speed=speed * perf_speed,
            pitch=pitch + perf_pitch,
            volume=perf_volume,
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
        """Lazy-load a VoxCPM model (optional dependency: the voxcpm extra)."""
        if not TTSEngine.voxcpm_available():
            from claynext.models.features import dev_environment_sync_command

            raise RuntimeError(
                "VoxCPM2 is not installed.\n"
                f"Install the development extras:\n{dev_environment_sync_command()}\n"
                "Needs the voxcpm 2 package and PyTorch ≥ 2.5 "
                "(Apple Silicon, Windows, or Linux). "
                "The speech checkpoint is openbmb/VoxCPM2."
            )
        repo = (model_name or TTSEngine.VOXCPM_DEFAULT_MODEL).strip() or TTSEngine.VOXCPM_DEFAULT_MODEL
        with _voxcpm_lock:
            if repo in _voxcpm_models:
                return _voxcpm_models[repo]
            if progress_callback:
                progress_callback(20, f"Loading VoxCPM2 ({repo})… first run downloads weights")
            from claynext.utils.paths import MODELS_DIR
            from voxcpm import VoxCPM

            load_kwargs = {
                "load_denoiser": False,
                "cache_dir": str(MODELS_DIR),
                **_voxcpm_runtime(),
            }
            model = VoxCPM.from_pretrained(repo, **_filter_call(VoxCPM.from_pretrained, load_kwargs))
            _voxcpm_models[repo] = model
            if progress_callback:
                progress_callback(45, "VoxCPM2 ready")
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
        style_prompt: str = "",
        progress_callback: Callable | None = None,
    ) -> str:
        """Synthesize with VoxCPM Voice Design (or optional reference clone).

        ``style_prompt`` (e.g. "shouting with a raised voice") joins the
        parenthesised design; with a reference clone it is the whole prefix.
        """
        raw = (text or "").strip()
        if not raw:
            raise RuntimeError("No text to speak.")

        meta = TTSEngine._voxcpm_voice_meta(voice_id)
        design = "" if reference_wav else str(meta.get("design") or "").strip()
        style = str(style_prompt or "").strip()
        prefix = ", ".join(part for part in (design, style) if part)
        speak = f"({prefix}){raw}" if prefix else raw
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

        from claynext.utils.library_progress import library_stage

        with library_stage("Speaking"):
            wav = _call_voxcpm(model, **kwargs)
        import soundfile as sf

        rate = int(getattr(getattr(model, "tts_model", None), "sample_rate", None) or 48000)
        sf.write(wav_out, wav, rate)

        if output_path.lower().endswith(".mp3"):
            if progress_callback:
                progress_callback(85, "Encoding to MP3…")
            from claynext.adapters.ffmpeg_adapter import run_ffmpeg

            ok = run_ffmpeg([
                "-y", "-i", wav_out,
                "-codec:a", "libmp3lame", "-q:a", "2",
                output_path,
            ])
            if not ok or not os.path.isfile(output_path):
                raise RuntimeError("Failed to encode VoxCPM speech to MP3.")
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
    def get_omnivoice_model(
        model_name: str = OMNIVOICE_DEFAULT_MODEL,
        progress_callback: Callable | None = None,
    ) -> Any:
        """Lazy-load OmniVoice (optional dependency: the omnivoice extra)."""
        if not TTSEngine.omnivoice_available():
            from claynext.models.features import dev_environment_sync_command

            raise RuntimeError(
                "OmniVoice is not installed.\n"
                f"Install the development extras:\n{dev_environment_sync_command()}\n"
                "Needs the omnivoice package and PyTorch ≥ 2.4 "
                "(Apple Silicon, Windows, or Linux). "
                "The speech checkpoint is k2-fsa/OmniVoice."
            )
        repo = (model_name or TTSEngine.OMNIVOICE_DEFAULT_MODEL).strip() or TTSEngine.OMNIVOICE_DEFAULT_MODEL
        with _omnivoice_lock:
            if repo in _omnivoice_models:
                return _omnivoice_models[repo]
            if progress_callback:
                progress_callback(20, f"Loading OmniVoice ({repo})… first run downloads weights")
            from claynext.models.hf_hub import get_local_model_path
            from claynext.utils.paths import MODELS_DIR
            from omnivoice import OmniVoice

            source = get_local_model_path(repo) or repo
            load_kwargs = {
                "cache_dir": str(MODELS_DIR),
                **_omnivoice_runtime(),
            }
            model = OmniVoice.from_pretrained(source, **_filter_call(OmniVoice.from_pretrained, load_kwargs))
            _omnivoice_models[repo] = model
            if progress_callback:
                progress_callback(45, "OmniVoice ready")
            return model

    @staticmethod
    def synthesize_omnivoice(
        text: str,
        voice_id: str,
        output_path: str,
        *,
        speed: float = 1.0,
        model_name: str = OMNIVOICE_DEFAULT_MODEL,
        reference_wav: str = "",
        num_step: int = 16,
        instruct_extra: str = "",
        progress_callback: Callable | None = None,
    ) -> str:
        """Synthesize with k2-fsa/OmniVoice voice design, or a reference clone."""
        raw = (text or "").strip()
        if not raw:
            raise RuntimeError("No text to speak.")

        meta = TTSEngine._omnivoice_voice_meta(voice_id)
        instruct = str(meta.get("instruct") or "").strip()
        extra = str(instruct_extra or "").strip()
        if extra and extra not in instruct:
            instruct = f"{instruct}, {extra}" if instruct else extra
        label = meta.get("name") or voice_id

        if progress_callback:
            progress_callback(25, f"Synthesizing with OmniVoice [{label}]…")

        model = TTSEngine.get_omnivoice_model(
            model_name or TTSEngine.OMNIVOICE_DEFAULT_MODEL,
            progress_callback,
        )
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        wav_out = str(target.with_suffix(".wav"))

        if progress_callback:
            progress_callback(55, "Generating speech (OmniVoice)…")

        kwargs: dict[str, Any] = {
            "text": raw,
            "num_step": int(num_step),
            "speed": float(speed) if speed and speed > 0 else 1.0,
        }
        if reference_wav and os.path.isfile(reference_wav):
            kwargs["ref_audio"] = reference_wav
        elif instruct:
            kwargs["instruct"] = instruct

        call = _filter_call(model.generate, kwargs)
        wav = model.generate(**call)
        if isinstance(wav, (list, tuple)):
            wav = wav[0]
        if hasattr(wav, "detach"):
            wav = wav.detach().cpu().numpy()

        import soundfile as sf

        sf.write(wav_out, wav, TTSEngine.OMNIVOICE_SAMPLE_RATE)

        if output_path.lower().endswith(".mp3"):
            if progress_callback:
                progress_callback(85, "Encoding to MP3…")
            from claynext.adapters.ffmpeg_adapter import run_ffmpeg

            ok = run_ffmpeg([
                "-y", "-i", wav_out,
                "-codec:a", "libmp3lame", "-q:a", "2",
                output_path,
            ])
            if not ok or not os.path.isfile(output_path):
                raise RuntimeError("Failed to encode OmniVoice speech to MP3.")
            if os.path.exists(wav_out) and wav_out != output_path:
                try:
                    os.remove(wav_out)
                except Exception:
                    pass
            actual_path = output_path
        else:
            actual_path = wav_out

        if progress_callback:
            progress_callback(100, f"OmniVoice speech ready [{label}]")
        return actual_path

    @staticmethod
    def synthesize_sglang(
        text: str,
        voice_id: str,
        output_path: str,
        progress_callback: Callable | None = None,
        control: Any = None,
    ) -> str:
        """Speak one line on the SGLang-Omni server. The dub mix still places it."""
        raw = (text or "").strip()
        if not raw:
            raise RuntimeError("No text to speak.")
        voice = voice_id.split(":", 1)[1] if ":" in (voice_id or "") else "female"
        for item in TTSEngine.SGLANG_VOICES:
            if item["id"] == voice_id:
                voice = str(item.get("voice") or voice)
                break
        if progress_callback:
            progress_callback(30, f"Synthesizing with SGLang-Omni [{voice}]…")
        from claynext.models.sglang_omni import synthesize as sglang_speak

        path = sglang_speak(raw, output_path, voice=voice, control=control)
        if progress_callback:
            progress_callback(100, "SGLang-Omni speech ready")
        return path

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

        # If user explicitly requested .mp3, convert via FFmpeg adapter
        if output_path.lower().endswith(".mp3"):
            if progress_callback:
                progress_callback(85, "Encoding to MP3…")
            from claynext.adapters.ffmpeg_adapter import run_ffmpeg

            ok = run_ffmpeg([
                "-y", "-i", wav_out,
                "-codec:a", "libmp3lame", "-q:a", "2",
                output_path,
            ])
            if not ok or not os.path.isfile(output_path):
                raise RuntimeError("Failed to encode KittenTTS speech to MP3.")
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
        volume: float = 0.0,
    ) -> str:
        raw = (text or "").strip()
        if not raw:
            raise RuntimeError("No text to speak.")
        if not TTSEngine._is_edge_voice(voice_id):
            raise RuntimeError(f"Voice is not an Edge neural voice: {voice_id}")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        rate_str = f"{int(round((speed - 1.0) * 100)):+d}%"
        pitch_str = f"{int(round(pitch)):+d}Hz"
        volume_str = f"{int(round(max(-90.0, min(90.0, volume)))):+d}%"
        _ensure_edge_tts_endpoint()
        if progress_callback:
            progress_callback(40, "Streaming Edge TTS…")

        async def _run_edge():
            communicate = edge_tts.Communicate(
                raw, voice=voice_id, rate=rate_str, pitch=pitch_str, volume=volume_str,
            )
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
    def synthesize_eleven(
        text: str,
        voice_id: str,
        output_path: str,
        speed: float = 1.0,
        progress_callback: Callable | None = None,
        stability: float | None = None,
        style: float | None = None,
    ) -> str:
        """Speak with elevenlabs.io. The key lives in Settings → API Keys, or ELEVENLABS_API_KEY."""
        import json
        import urllib.error
        import urllib.request

        from claynext.models.llm_keys import RateLimitError, get_key_pool

        raw = (text or "").strip()
        if not raw:
            raise RuntimeError("No text to speak.")
        if not TTSEngine._is_eleven_voice(voice_id):
            raise RuntimeError(f"Voice is not an ElevenLabs voice: {voice_id}")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        api_voice = TTSEngine._eleven_api_id(voice_id)
        pace = max(0.25, min(4.0, float(speed or 1.0)))
        if progress_callback:
            progress_callback(40, "Speaking with ElevenLabs…")

        def _call(secret: str) -> bytes:
            url = (
                "https://api.elevenlabs.io/v1/text-to-speech/"
                f"{api_voice}?output_format=mp3_44100_128"
            )
            body = {
                "text": raw,
                "model_id": TTSEngine.ELEVEN_MODEL,
                "voice_settings": {
                    "stability": 0.45 if stability is None else max(0.0, min(1.0, float(stability))),
                    "similarity_boost": 0.75,
                    "style": 0.0 if style is None else max(0.0, min(1.0, float(style))),
                    "speed": pace,
                    "use_speaker_boost": True,
                },
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "xi-api-key": secret,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
                if exc.code == 429:
                    raise RateLimitError(detail or "ElevenLabs rate limit")
                if exc.code == 402:
                    raise RuntimeError(
                        "This ElevenLabs voice needs a paid plan. "
                        "Preview the voices on your account instead."
                    )
                if exc.code in {401, 403}:
                    raise RuntimeError(
                        "ElevenLabs rejected the API key. "
                        "Add a key in Settings → API Keys → ElevenLabs."
                    )
                raise RuntimeError(f"ElevenLabs TTS failed ({exc.code}). {detail}") from exc

        audio = get_key_pool().call_with_rotation(
            "elevenlabs", _call, progress=progress_callback,
        )
        if not audio:
            raise RuntimeError("ElevenLabs returned empty audio.")
        Path(output_path).write_bytes(audio)
        if progress_callback:
            progress_callback(100, "ElevenLabs speech ready")
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
            from claynext.adapters.ffmpeg_adapter import get_ffmpeg_adapter

            dur = get_ffmpeg_adapter().duration(file_path)
            if dur and dur > 0:
                return float(dur)
        except Exception:
            pass
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
        """Synthesize text with KittenTTS, VoxCPM, OmniVoice, ElevenLabs, or Edge TTS."""
        if progress_callback:
            progress_callback(10, f"Connecting to {provider} voice '{voice_id}'…")

        use_wav = (
            TTSEngine._is_kitten_voice(voice_id)
            or TTSEngine._is_voxcpm_voice(voice_id)
            or TTSEngine._is_omnivoice_voice(voice_id)
            or TTSEngine._is_sglang_voice(voice_id)
            or "Kitten" in (provider or "")
            or "VoxCPM" in (provider or "")
            or "OmniVoice" in (provider or "")
            or "SGLang" in (provider or "")
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

        if TTSEngine._is_omnivoice_voice(voice_id) or "OmniVoice" in (provider or ""):
            try:
                omni_model = model_name if str(model_name).startswith("k2-fsa/") else TTSEngine.OMNIVOICE_DEFAULT_MODEL
                actual_path = TTSEngine.synthesize_omnivoice(
                    text,
                    voice_id,
                    output_path,
                    speed=speed,
                    model_name=omni_model,
                    reference_wav=reference_wav,
                    progress_callback=progress_callback,
                )
                duration = TTSEngine._probe_duration(actual_path)
                peaks = TTSEngine._extract_peaks(actual_path)
                return {
                    "text": text,
                    "duration": duration,
                    "sample_rate": TTSEngine.OMNIVOICE_SAMPLE_RATE,
                    "wave_peaks": peaks,
                    "file_path": actual_path,
                }
            except Exception as exc:
                if progress_callback:
                    progress_callback(38, f"OmniVoice error: {exc} — trying other engines…")
                if TTSEngine._is_omnivoice_voice(voice_id):
                    raise

        if TTSEngine._is_sglang_voice(voice_id) or "SGLang" in (provider or ""):
            try:
                actual_path = TTSEngine.synthesize_sglang(
                    text,
                    voice_id if TTSEngine._is_sglang_voice(voice_id) else TTSEngine.SGLANG_VOICES[0]["id"],
                    output_path,
                    progress_callback=progress_callback,
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
                    progress_callback(40, f"SGLang-Omni error: {exc}")
                if TTSEngine._is_sglang_voice(voice_id):
                    raise

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

        # 3. ElevenLabs online synthesis
        if TTSEngine._is_eleven_voice(voice_id) or "ElevenLabs" in (provider or ""):
            try:
                eleven_voice = voice_id if TTSEngine._is_eleven_voice(voice_id) else TTSEngine.ELEVEN_VOICES[0]["id"]
                actual_path = TTSEngine.synthesize_eleven(
                    text, eleven_voice, output_path, speed=speed, progress_callback=progress_callback,
                )
                duration = TTSEngine._probe_duration(actual_path)
                peaks = TTSEngine._extract_peaks(actual_path)
                return {
                    "text": text,
                    "duration": duration,
                    "sample_rate": 44100,
                    "wave_peaks": peaks,
                    "file_path": actual_path,
                }
            except Exception as exc:
                if progress_callback:
                    progress_callback(55, f"ElevenLabs unavailable: {exc}")
                if TTSEngine._is_eleven_voice(voice_id):
                    raise

        # 4. Microsoft Edge TTS online synthesis
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

        # 5. Fallback tone synthesizer
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

