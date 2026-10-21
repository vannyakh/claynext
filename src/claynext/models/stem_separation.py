"""
Movie vocal / music stem separation for dubbing mix beds.

Backends (first available wins):
  1. demucs-mlx — Apple Silicon MLX port
  2. demucs     — Meta Demucs / htdemucs
  3. audio-separator — UVR vocal / instrumental (https://github.com/nomadkaraoke/python-audio-separator)

Install:
  uv sync --extra demucs-mlx        # macOS arm64
  uv sync --extra demucs            # PyTorch Demucs (not Intel macOS)
  # audio-separator is not an extra yet: it needs torch>=2.13, and the
  # demucs extra pins torch==2.8. Intel macOS has no torch wheel at all.
"""
from __future__ import annotations

import hashlib
import os
import platform
from pathlib import Path
from typing import Callable

Ping = Callable[[int, str], None] | None

DEFAULT_MODEL = "htdemucs"
# ONNX MDX model: Instrumental (effects + music) and Vocals. Weights land in data/models.
SEPARATOR_MODEL = "UVR-MDX-NET-Inst_HQ_3.onnx"
VOCAL_KEYS = frozenset({"vocals", "vocal"})


def demucs_mlx_supported() -> bool:
    """True when the host can run the MLX Demucs port."""
    return platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"}


def separator_available() -> bool:
    """True when python-audio-separator can be imported."""
    try:
        from audio_separator.separator import Separator  # noqa: F401
        return True
    except Exception:
        return False


def backend_available() -> str | None:
    """Return ``mlx``, ``torch``, ``separator``, or ``None``."""
    if demucs_mlx_supported():
        try:
            import demucs_mlx  # noqa: F401
            return "mlx"
        except Exception:
            pass
    try:
        import demucs.api  # noqa: F401
        return "torch"
    except Exception:
        return None
    if separator_available():
        return "separator"
    return None


def _media_key(media_path: str, model: str, backend: str) -> str:
    stat = os.stat(media_path)
    raw = f"{os.path.abspath(media_path)}|{stat.st_size}|{int(stat.st_mtime)}|{model}|{backend}|v2"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _cache_dir(key: str) -> Path:
    from claynext.utils.paths import CACHE_DIR

    root = Path(CACHE_DIR) / "stems" / key
    root.mkdir(parents=True, exist_ok=True)
    return root


def _to_numpy(audio):
    """Normalize a stem to float32 channels-first stereo ``(2, T)``."""
    import numpy as np

    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    elif hasattr(audio, "__array__"):
        audio = np.asarray(audio)
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr[None, :]
    if arr.ndim != 2:
        raise ValueError(f"Unexpected stem shape: {arr.shape}")
    # Prefer channels-first (C, T); demucs / demucs-mlx both use that.
    if arr.shape[0] > 8 and arr.shape[0] > arr.shape[1]:
        arr = arr.T
    if arr.shape[0] == 1:
        arr = np.repeat(arr, 2, axis=0)
    return arr[:2]


def _write_wav(path: Path, audio, sample_rate: int) -> None:
    import wave
    import numpy as np

    arr = _to_numpy(audio)
    # (C, T) → (T, C)
    frames = np.clip(arr.T, -1.0, 1.0)
    pcm = (frames * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with wave.open(str(tmp), "wb") as wf:
        wf.setnchannels(pcm.shape[1])
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm.tobytes())
    tmp.replace(path)


def _resample_48k(src: Path, dst: Path) -> bool:
    from claynext.adapters.ffmpeg_adapter import run_ffmpeg

    tmp = dst.with_suffix(".part.wav")
    proc = run_ffmpeg(
        ["-y", "-i", str(src), "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(tmp)],
        timeout=900,
    )
    if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(dst)
    return True


def _split_stems(stems: dict) -> tuple[object | None, object | None]:
    """Return (instrumental, vocals) tensors/arrays."""
    vocals = None
    instrumental = None
    for name, tensor in stems.items():
        key = str(name).lower()
        if key in VOCAL_KEYS:
            vocals = tensor
        else:
            chunk = _to_numpy(tensor)
            if instrumental is None:
                instrumental = chunk
            else:
                instrumental = instrumental + chunk
    return instrumental, vocals


def _separate_mlx(wav_path: str, model: str, ping: Ping) -> tuple[dict, int]:
    from demucs_mlx import Separator

    if ping:
        ping(12, f"Demucs MLX · {model} stem separation…")
    sep = Separator(model=model)
    _origin, stems = sep.separate_audio_file(wav_path)
    rate = int(getattr(sep, "samplerate", None) or getattr(sep, "sample_rate", 44100) or 44100)
    return stems, rate


def _separate_uvr(media_path: str, work: Path, ping: Ping) -> tuple[Path | None, Path | None]:
    """Split effects+music from vocals with audio-separator. Returns file paths."""
    from audio_separator.separator import Separator
    from claynext.utils.paths import MODELS_DIR

    model_dir = MODELS_DIR / "audio-separator"
    model_dir.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    if ping:
        ping(12, "Splitting vocals from effects…")
    separator = Separator(
        output_dir=str(work),
        output_format="WAV",
        model_file_dir=str(model_dir),
        sample_rate=48000,
    )
    separator.load_model(model_filename=SEPARATOR_MODEL)
    written = separator.separate(media_path) or []
    vocals: Path | None = None
    instrumental: Path | None = None
    for item in written:
        path = Path(str(item))
        name = path.name.lower()
        if "vocal" in name and "instrument" not in name:
            vocals = path
        elif "instrument" in name or "no_vocal" in name or "karaoke" in name:
            instrumental = path
    return instrumental, vocals


def _separate_torch(wav_path: str, model: str, ping: Ping) -> tuple[dict, int]:
    from demucs.api import Separator, save_audio  # noqa: F401 — save kept for parity

    if ping:
        ping(12, f"Demucs · {model} stem separation…")
    try:
        from claynext.adapters.resources import apply_process_threads

        apply_process_threads()
    except Exception:
        pass
    sep = Separator(model=model)
    _origin, stems = sep.separate_audio_file(Path(wav_path))
    rate = int(getattr(sep, "samplerate", 44100) or 44100)
    return stems, rate


def separate_movie_stems(
    media_path: str,
    *,
    out_dir: str | Path | None = None,
    model: str = DEFAULT_MODEL,
    progress_callback: Ping = None,
    force: bool = False,
) -> dict[str, str | None]:
    """
    Isolate dialogue (vocals) from music / effects for movie audio.

    Returns paths::
        {
          "backend": "mlx" | "torch" | "separator" | None,
          "bed": instrumental WAV @ 48 kHz stereo (or None),
          "vocals": vocal stem WAV @ 48 kHz stereo (or None),
          "model": model name,
        }
    """
    empty = {"backend": None, "bed": None, "vocals": None, "model": model}
    if not media_path or not os.path.isfile(media_path):
        return empty

    backend = backend_available()
    if not backend:
        return empty
    if backend == "separator":
        model = SEPARATOR_MODEL

    key = _media_key(media_path, model, backend)
    root = Path(out_dir) if out_dir else _cache_dir(key)
    root.mkdir(parents=True, exist_ok=True)
    bed_path = root / "bed_48k.wav"
    vocals_path = root / "vocals_48k.wav"

    if (
        not force
        and bed_path.is_file()
        and bed_path.stat().st_size > 0
        and vocals_path.is_file()
        and vocals_path.stat().st_size > 0
    ):
        return {
            "backend": backend,
            "bed": str(bed_path),
            "vocals": str(vocals_path),
            "model": model,
        }

    ping = progress_callback
    if backend == "separator":
        try:
            instrumental_path, vocals_file = _separate_uvr(media_path, root / "uvr", ping)
        except Exception:
            return empty
        if ping:
            ping(40, "Writing isolated music bed and vocal stem…")
        bed_ok = bool(instrumental_path and _resample_48k(instrumental_path, bed_path))
        voc_ok = bool(vocals_file and _resample_48k(vocals_file, vocals_path))
        return {
            "backend": backend,
            "bed": str(bed_path) if bed_ok else None,
            "vocals": str(vocals_path) if voc_ok else None,
            "model": model,
        }

    try:
        if backend == "mlx":
            stems, rate = _separate_mlx(media_path, model, ping)
        else:
            stems, rate = _separate_torch(media_path, model, ping)
    except Exception:
        return empty

    instrumental, vocals = _split_stems(stems)
    if instrumental is None and vocals is None:
        return empty

    if ping:
        ping(40, "Writing isolated music bed and vocal stem…")

    raw_bed = root / "bed_raw.wav"
    raw_vocals = root / "vocals_raw.wav"
    try:
        if instrumental is not None:
            _write_wav(raw_bed, instrumental, rate)
            if not _resample_48k(raw_bed, bed_path):
                return empty
        if vocals is not None:
            _write_wav(raw_vocals, vocals, rate)
            if not _resample_48k(raw_vocals, vocals_path):
                vocals_path.unlink(missing_ok=True)
    finally:
        raw_bed.unlink(missing_ok=True)
        raw_vocals.unlink(missing_ok=True)

    bed_ok = bed_path.is_file() and bed_path.stat().st_size > 0
    voc_ok = vocals_path.is_file() and vocals_path.stat().st_size > 0
    return {
        "backend": backend,
        "bed": str(bed_path) if bed_ok else None,
        "vocals": str(vocals_path) if voc_ok else None,
        "model": model,
    }


def ensure_demucs_speech_bed(
    media_path: str,
    progress_callback: Ping = None,
    *,
    model: str | None = None,
) -> tuple[str, str]:
    """
    Best-effort Demucs bed + vocals.

    Returns ``(bed_path, vocals_path)``; either may be empty string.
    Uses the studio ``demucs_model`` setting when ``model`` is omitted.
    """
    if model is None:
        try:
            from claynext.models.features import demucs_model_name

            model = demucs_model_name()
        except Exception:
            model = DEFAULT_MODEL
    result = separate_movie_stems(
        media_path,
        model=model or DEFAULT_MODEL,
        progress_callback=progress_callback,
    )
    return str(result.get("bed") or ""), str(result.get("vocals") or "")

