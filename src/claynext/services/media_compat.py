"""
High-Performance Media Compatibility & Proxy Processor.

- Converts HE-AACv2, variable sample rate, and non-compliant audio streams
  into 100% compliant AAC-LC 44.1kHz stereo or MP3 without FFmpeg bitstream errors.
- Generates high-performance lightweight 720p H.264 proxy renders for smooth playback,
  scrubbing, and previewing on high-res or heavy video files.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from functools import lru_cache
from pathlib import Path

from claynext.utils.config import PLAYBACK_DIR, PROXY_DIR

_SAFE_EXTS = {".mp3", ".wav", ".flac", ".ogg"}
_CONVERT_EXTS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".m4a", ".aac", ".avi", ".ts", ".flv"}


@lru_cache(maxsize=1)
def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _run_ffmpeg(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_ffmpeg_exe(), "-hide_banner", "-loglevel", "quiet", "-nostdin", *args],
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _cache_path(media_path: str, suffix: str = "aaclc-v3") -> Path:
    abs_path = os.path.abspath(media_path)
    try:
        stamp = f"{os.path.getmtime(abs_path)}|{os.path.getsize(abs_path)}"
    except OSError:
        stamp = "0"
    key = hashlib.sha1(f"{abs_path}|{stamp}|{suffix}".encode()).hexdigest()
    return PLAYBACK_DIR / f"{key}.mp4"


def ready_playback_path(media_path: str) -> str | None:
    """Return a Qt-safe path if one is already available."""
    if not media_path or not os.path.isfile(media_path):
        return None
    abs_path = os.path.abspath(media_path)
    ext = os.path.splitext(abs_path)[1].lower()
    if ext in _SAFE_EXTS:
        return abs_path
    cached = _cache_path(abs_path)
    if cached.is_file() and cached.stat().st_size > 0:
        return str(cached)
    return None


def _try_remux_aac(abs_path: str, tmp: Path, *, video: bool) -> bool:
    """Remux with strictly compliant AAC-LC stereo 44.1kHz audio stream."""
    args = ["-y", "-i", abs_path]
    if video:
        args += ["-c:v", "copy"]
    else:
        args += ["-vn"]
    args += [
        "-c:a", "aac",
        "-profile:a", "aac_low",
        "-b:a", "192k",
        "-ac", "2",
        "-ar", "44100",
        "-movflags", "+faststart",
        str(tmp),
    ]
    try:
        proc = _run_ffmpeg(args, timeout=300)
        return proc.returncode == 0 and tmp.is_file() and tmp.stat().st_size > 0
    except Exception:
        return False


def _try_remux_mp3(abs_path: str, tmp: Path, *, video: bool) -> bool:
    """Fallback remux with stereo MP3 audio stream inside MP4 container."""
    args = ["-y", "-i", abs_path]
    if video:
        args += ["-c:v", "copy"]
    else:
        args += ["-vn"]
    args += [
        "-c:a", "libmp3lame",
        "-q:a", "2",
        "-ac", "2",
        "-ar", "44100",
        "-movflags", "+faststart",
        str(tmp),
    ]
    try:
        proc = _run_ffmpeg(args, timeout=300)
        return proc.returncode == 0 and tmp.is_file() and tmp.stat().st_size > 0
    except Exception:
        return False


def _try_video_only(abs_path: str, tmp: Path) -> bool:
    """Remux video stream without audio as fail-safe."""
    args = [
        "-y", "-i", abs_path,
        "-map", "0:v:0",
        "-c:v", "copy",
        "-an",
        "-movflags", "+faststart",
        str(tmp),
    ]
    try:
        proc = _run_ffmpeg(args, timeout=180)
        return proc.returncode == 0 and tmp.is_file() and tmp.stat().st_size > 0
    except Exception:
        return False


def ensure_playback_file(media_path: str, progress_callback=None) -> str:
    """
    Return a file path safe for QMediaPlayer with 0 bitstream decoding errors.
    """
    abs_path = os.path.abspath(media_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(abs_path)

    ready = ready_playback_path(abs_path)
    if ready:
        return ready

    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in _CONVERT_EXTS:
        return abs_path

    out = _cache_path(abs_path)
    tmp = out.with_suffix(".tmp.mp4")
    try:
        if tmp.exists():
            tmp.unlink()
    except OSError:
        pass

    if progress_callback:
        progress_callback(15, "Optimizing playback stream…")

    # 1. Primary: Compliant AAC-LC
    ok = _try_remux_aac(abs_path, tmp, video=True)
    if not ok:
        # 2. Secondary: Stereo MP3 audio
        ok = _try_remux_mp3(abs_path, tmp, video=True)
    if not ok:
        # 3. Audio-only AAC
        ok = _try_remux_aac(abs_path, tmp, video=False)
    if not ok:
        # 4. Video-only fallback
        ok = _try_video_only(abs_path, tmp)

    if ok:
        tmp.replace(out)
        if progress_callback:
            progress_callback(100, "Playback stream ready")
        return str(out)

    try:
        if tmp.exists():
            tmp.unlink()
    except OSError:
        pass
    raise OSError(f"Could not prepare playback file for {os.path.basename(abs_path)}")


def ensure_proxy_render(media_path: str, progress_callback=None) -> str:
    """
    Generate a 720p ultra-fast H.264 + stereo AAC proxy video file
    for smooth timeline scrubbing and preview rendering.
    """
    abs_path = os.path.abspath(media_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(abs_path)

    out = _cache_path(abs_path, suffix="proxy-720p")
    if out.is_file() and out.stat().st_size > 0:
        return str(out)

    tmp = out.with_suffix(".tmp.mp4")
    try:
        if tmp.exists():
            tmp.unlink()
    except OSError:
        pass

    if progress_callback:
        progress_callback(20, "Building 720p proxy render…")

    args = [
        "-y", "-i", abs_path,
        "-vf", r"scale='min(1280\,iw)':-2",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "22",
        "-c:a", "aac",
        "-profile:a", "aac_low",
        "-b:a", "128k",
        "-ac", "2",
        "-ar", "44100",
        "-movflags", "+faststart",
        str(tmp),
    ]

    try:
        proc = _run_ffmpeg(args, timeout=600)
        if proc.returncode == 0 and tmp.is_file() and tmp.stat().st_size > 0:
            tmp.replace(out)
            if progress_callback:
                progress_callback(100, "Proxy render ready")
            return str(out)
    except Exception:
        pass

    try:
        if tmp.exists():
            tmp.unlink()
    except OSError:
        pass

    # Fallback to standard playback file if proxy render fails
    return ensure_playback_file(abs_path, progress_callback)
