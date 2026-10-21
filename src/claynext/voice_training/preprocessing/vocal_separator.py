"""Optional vocal isolation: Demucs / stem_separation when available, else FFmpeg mid-side."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger("claynext.voice_training.vocal_separator")

Ping = Callable[[int, str], None] | None


def separate_vocals(
    wav_path: str | Path,
    out_dir: str | Path,
    *,
    progress_callback: Ping = None,
) -> dict[str, str | None]:
    """
    Return ``{backend, vocals, bed}`` paths. Never requires new torch installs.
    Falls back to copying the input as 'vocals' when no stem tool is present.
    """
    src = Path(wav_path)
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    vocals_out = root / "vocals.wav"
    bed_out = root / "bed.wav"

    try:
        from claynext.models.stem_separation import separate_movie_stems

        result = separate_movie_stems(
            str(src), out_dir=root / "stems", progress_callback=progress_callback
        )
        if result.get("vocals"):
            return {
                "backend": str(result.get("backend") or "demucs"),
                "vocals": str(result["vocals"]),
                "bed": result.get("bed"),
            }
    except Exception as exc:
        logger.debug("Demucs stem separation unavailable: %s", exc)

    # FFmpeg mid-side approximation for stereo dialogue emphasis.
    try:
        from claynext.adapters.ffmpeg_service import run_ffmpeg

        if progress_callback:
            progress_callback(40, "FFmpeg mid-side vocal approx…")
        proc = run_ffmpeg(
            [
                "-y", "-i", str(src),
                "-af", "pan=mono|c0=0.5*c0+-0.5*c1,highpass=f=100,lowpass=f=8000",
                str(vocals_out),
            ],
            timeout=300,
        )
        if proc.returncode == 0 and vocals_out.is_file():
            # Bed ≈ residual; copy original as bed placeholder.
            import shutil

            shutil.copy2(src, bed_out)
            return {"backend": "ffmpeg_midside", "vocals": str(vocals_out), "bed": str(bed_out)}
    except Exception as exc:
        logger.debug("FFmpeg mid-side failed: %s", exc)

    import shutil

    shutil.copy2(src, vocals_out)
    return {"backend": "passthrough", "vocals": str(vocals_out), "bed": None}
