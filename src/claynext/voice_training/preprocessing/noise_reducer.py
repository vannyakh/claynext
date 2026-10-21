"""Optional light noise reduction (no new heavy deps)."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger("claynext.voice_training.noise_reducer")


def reduce_noise(wav_path: str | Path, output_path: str | Path | None = None) -> Path:
    """
    Apply a gentle highpass + afftdn when FFmpeg is available; otherwise copy.
    """
    src = Path(wav_path)
    dst = Path(output_path) if output_path else src.with_name(src.stem + "_denoise.wav")
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        from claynext.adapters.ffmpeg_service import run_ffmpeg

        proc = run_ffmpeg(
            ["-y", "-i", str(src), "-af", "highpass=f=80,afftdn=nr=12:nf=-25", str(dst)],
            timeout=300,
        )
        if proc.returncode == 0 and dst.is_file():
            return dst
    except Exception as exc:
        logger.debug("Noise reduce skipped: %s", exc)
    shutil.copy2(src, dst)
    return dst
