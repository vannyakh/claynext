"""
Jela Hugging Face Model Hub Manager.
Provides discovery, download/pull with progress tracking, local caching, and status tracking
for Translation, TTS, and ASR models from Hugging Face.
"""
from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from jela.core.llm_keys import get_key_pool
from jela.utils.config import MODELS_DIR

_download_lock = threading.Lock()

# Curated registry of Hugging Face models for Jela Studio
HF_MODEL_REGISTRY: list[dict[str, Any]] = [
    # ─── Translation (Offline NMT) ──────────────────────────────
    {
        "id": "JustFrederik/nllb-200-distilled-600M-ct2-int8",
        "name": "NLLB-200 (600M INT8 · CTranslate2)",
        "category": "translate",
        "size_label": "~620 MB",
        "description": "200 languages (Khmer, Chinese, Vietnamese, English, etc.). Fast CPU INT8 offline translation.",
        "backend": "ctranslate2",
        "essential_file": "model.bin",
    },
    {
        "id": "facebook/nllb-200-distilled-600M",
        "name": "NLLB-200 (600M · Transformers)",
        "category": "translate",
        "size_label": "~2.4 GB",
        "description": "Meta NLLB-200 standard seq2seq translation checkpoint for 200 languages.",
        "backend": "transformers",
        "essential_file": "sentencepiece.bpe.model",
    },
    # ─── TTS (Neural Speech Synthesis) ─────────────────────────
    {
        "id": "KittenML/kitten-tts-nano-0.8-fp32",
        "name": "Kitten Nano (15M FP32 · Ultra-Fast)",
        "category": "tts",
        "size_label": "~60 MB",
        "description": "Ultra-lightweight 15M ONNX neural speech model. 8 built-in voices. Runs smoothly on any CPU.",
        "backend": "kittentts",
        "essential_file": "config.json",
    },
    {
        "id": "KittenML/kitten-tts-nano-0.8-int8",
        "name": "Kitten Nano (15M INT8 · Quantized)",
        "category": "tts",
        "size_label": "~25 MB",
        "description": "Quantized 15M INT8 ONNX neural speech model. Minimal memory footprint.",
        "backend": "kittentts",
        "essential_file": "config.json",
    },
    {
        "id": "KittenML/kitten-tts-micro-0.8",
        "name": "Kitten Micro (40M · Balanced)",
        "category": "tts",
        "size_label": "~160 MB",
        "description": "40M ONNX neural speech model with balanced speed and expressiveness.",
        "backend": "kittentts",
        "essential_file": "config.json",
    },
    {
        "id": "KittenML/kitten-tts-mini-0.8",
        "name": "Kitten Mini (80M · High Quality)",
        "category": "tts",
        "size_label": "~320 MB",
        "description": "80M ONNX neural speech model with rich vocal dynamics and pitch contours.",
        "backend": "kittentts",
        "essential_file": "config.json",
    },
    {
        "id": "openbmb/VoxCPM2",
        "name": "VoxCPM2 (2B · Multilingual 48kHz)",
        "category": "tts",
        "size_label": "~4 GB+",
        "description": "OpenBMB tokenizer-free TTS · 30 languages, voice design & cloning, 48kHz output. Install: uv sync --extra voxcpm",
        "backend": "voxcpm",
        "essential_file": "config.json",
    },
    {
        "id": "openbmb/VoxCPM1.5",
        "name": "VoxCPM1.5 (Balanced · Cloning)",
        "category": "tts",
        "size_label": "~2 GB+",
        "description": "OpenBMB VoxCPM1.5 with high-fidelity voice cloning. Install: uv sync --extra voxcpm",
        "backend": "voxcpm",
        "essential_file": "config.json",
    },
    {
        "id": "openbmb/VoxCPM-0.5B",
        "name": "VoxCPM 0.5B (Lighter)",
        "category": "tts",
        "size_label": "~1 GB+",
        "description": "Smaller VoxCPM checkpoint for faster local synthesis. Install: uv sync --extra voxcpm",
        "backend": "voxcpm",
        "essential_file": "config.json",
    },
    # ─── ASR (Whisper Speech Recognition) ──────────────────────
    {
        "id": "Systran/faster-whisper-tiny",
        "name": "Whisper Tiny (CTranslate2)",
        "category": "asr",
        "size_label": "~75 MB",
        "description": "Fastest Whisper model. Instant CPU transcription.",
        "backend": "ctranslate2",
        "essential_file": "model.bin",
    },
    {
        "id": "Systran/faster-whisper-small",
        "name": "Whisper Small (CTranslate2)",
        "category": "asr",
        "size_label": "~460 MB",
        "description": "Balanced Whisper model. Excellent accuracy for dialogue & subtitles.",
        "backend": "ctranslate2",
        "essential_file": "model.bin",
    },
    {
        "id": "Systran/faster-whisper-medium",
        "name": "Whisper Medium (CTranslate2)",
        "category": "asr",
        "size_label": "~1.5 GB",
        "description": "High accuracy multi-speaker speech transcription.",
        "backend": "ctranslate2",
        "essential_file": "model.bin",
    },
    # ─── Audio stem separation (movie music / dialogue isolation) ──
    {
        "id": "mlx-community/demucs-mlx",
        "name": "Demucs MLX (Apple Silicon · Stems)",
        "category": "audio",
        "size_label": "~160 MB+",
        "description": "HTDemucs music source separation on Apple Silicon (vocals / drums / bass / other). Install: uv sync --extra demucs-mlx. Auto-downloads on first use.",
        "backend": "demucs-mlx",
        "essential_file": "htdemucs.safetensors",
    },
    # ─── Gender (ASR dialogue analysis) ───────────────────────────
    {
        "id": "prithivMLmods/Common-Voice-Gender-Detection",
        "name": "Common-Voice Gender Detection",
        "category": "asr",
        "size_label": "~360 MB",
        "description": "Wav2Vec2 binary gender classifier (female/male) for dubbing ASR analysis. Install: uv sync --extra gender",
        "backend": "transformers",
        "essential_file": "config.json",
    },
]


def _hf_token() -> Optional[str]:
    """Retrieve Hugging Face token if configured in key pool or environment."""
    keys = get_key_pool().secrets("huggingface")
    if keys:
        return keys[0]
    return os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")


def get_model_meta(repo_id: str) -> Optional[dict[str, Any]]:
    """Return model metadata from registry, or generate default entry for custom repo."""
    for item in HF_MODEL_REGISTRY:
        if item["id"].lower() == repo_id.lower():
            return item
    return None


def get_model_registry(category: Optional[str] = None) -> list[dict[str, Any]]:
    """Return model entries, optionally filtered by category ('translate', 'tts', 'asr')."""
    out = []
    for item in HF_MODEL_REGISTRY:
        if category and item["category"] != category:
            continue
        entry = dict(item)
        entry["is_downloaded"] = is_model_downloaded(item["id"])
        out.append(entry)
    return out


def _candidate_cache_dirs(repo_id: str) -> list[Path]:
    """List directory locations where this Hugging Face model might reside."""
    norm_name = repo_id.replace("/", "--")
    hf_folder_name = f"models--{norm_name}"

    candidates: list[Path] = [
        # 1. Project models directory (data/models/models--owner--repo)
        MODELS_DIR / hf_folder_name,
        # 2. Project models directory direct subfolder (data/models/repo)
        MODELS_DIR / repo_id.split("/")[-1],
        MODELS_DIR / repo_id,
        # 3. Default user Hugging Face cache directory (~/.cache/huggingface/hub/models--owner--repo)
        Path.home() / ".cache" / "huggingface" / "hub" / hf_folder_name,
    ]
    return candidates


def is_model_downloaded(repo_id: str) -> bool:
    """Check if the Hugging Face model is already downloaded locally."""
    meta = get_model_meta(repo_id)
    essential = (meta or {}).get("essential_file")

    for cand in _candidate_cache_dirs(repo_id):
        if not cand.is_dir():
            continue

        # Look in snapshots if present (standard HF hub layout)
        snapshots = cand / "snapshots"
        if snapshots.is_dir():
            snaps = [s for s in snapshots.iterdir() if s.is_dir()]
            if snaps:
                latest = snaps[0]
                if essential:
                    if (latest / essential).is_file():
                        return True
                else:
                    if any(latest.iterdir()):
                        return True

        # Check direct directory
        if essential:
            if (cand / essential).is_file():
                return True
        else:
            if any(cand.iterdir()):
                return True

    return False


def get_local_model_path(repo_id: str) -> Optional[str]:
    """
    Return the resolved local filesystem directory path for a downloaded model.
    Returns None if not downloaded.
    """
    meta = get_model_meta(repo_id)
    essential = (meta or {}).get("essential_file")

    for cand in _candidate_cache_dirs(repo_id):
        if not cand.is_dir():
            continue

        snapshots = cand / "snapshots"
        if snapshots.is_dir():
            snaps = [s for s in snapshots.iterdir() if s.is_dir()]
            if snaps:
                latest = snaps[0]
                if essential:
                    if (latest / essential).is_file():
                        return str(latest)
                else:
                    return str(latest)

        if essential:
            if (cand / essential).is_file():
                return str(cand)
        elif any(cand.iterdir()):
            return str(cand)

    return None


def pull_model(
    repo_id: str,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> str:
    """
    Download/pull a model from Hugging Face into data/models.
    Reports progress via progress_callback(percentage, message).
    Returns the resolved local model path on success.
    """
    from huggingface_hub import snapshot_download

    token = _hf_token()
    meta = get_model_meta(repo_id)
    display_name = meta["name"] if meta else repo_id

    if progress_callback:
        progress_callback(5, f"Connecting to Hugging Face for {display_name}…")

    with _download_lock:
        # Check if already present
        cached = get_local_model_path(repo_id)
        if cached:
            if progress_callback:
                progress_callback(100, f"{display_name} is already available.")
            return cached

        if progress_callback:
            progress_callback(20, f"Downloading {display_name} weights from Hugging Face…")

        try:
            local_path = snapshot_download(
                repo_id=repo_id,
                cache_dir=str(MODELS_DIR),
                token=token,
            )
            if progress_callback:
                progress_callback(100, f"Downloaded {display_name} successfully!")
            return str(local_path)
        except Exception as e:
            if progress_callback:
                progress_callback(0, f"Failed to download {display_name}: {e}")
            raise RuntimeError(f"Could not pull Hugging Face model '{repo_id}': {e}") from e


def delete_local_model(repo_id: str) -> bool:
    """Remove local cache of a model from data/models."""
    norm_name = repo_id.replace("/", "--")
    target = MODELS_DIR / f"models--{norm_name}"
    if target.is_dir():
        try:
            shutil.rmtree(target)
            return True
        except OSError:
            return False
    return False
