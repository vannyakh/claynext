"""
Video thumbnail generation and disk cache for the media library / preview.
Uses the bundled imageio-ffmpeg binary.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush

from claynext.adapters.ffmpeg_adapter import probe_duration
from claynext.utils.config import THUMB_DIR

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


@lru_cache(maxsize=1)
def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def thumb_path_for(media_path: str, width: int = 160) -> Path:
    abs_path = os.path.abspath(media_path)
    key = hashlib.sha1(f"{abs_path}|{width}|{os.path.getmtime(abs_path) if os.path.isfile(abs_path) else 0}".encode()).hexdigest()
    return THUMB_DIR / f"{key}.jpg"


def ensure_thumbnail(media_path: str, width: int = 160) -> str | None:
    """
    Extract a JPEG frame near 1s (or start) and cache it.
    Prefers claynext-ffmpeg still extract; falls back to bundled FFmpeg.
    """
    if not media_path or not os.path.isfile(media_path):
        return None
    ext = os.path.splitext(media_path)[1].lower()
    if ext not in VIDEO_EXTS:
        return None

    out = thumb_path_for(media_path, width)
    if out.is_file() and out.stat().st_size > 0:
        return str(out)

    abs_path = os.path.abspath(media_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        from claynext.adapters.ffmpeg_adapter import get_ffmpeg_adapter

        if get_ffmpeg_adapter().extract_still(
            abs_path, out, timestamp_secs=1.0, max_width=width
        ):
            return str(out)
    except Exception:
        pass

    from claynext.adapters.ffmpeg_adapter import run_ffmpeg

    def _still_at(ss: str) -> bool:
        ok = run_ffmpeg([
            "-ss", ss,
            "-i", abs_path,
            "-frames:v", "1",
            "-vf", f"scale={width}:-1:force_original_aspect_ratio=decrease",
            "-q:v", "4",
            "-y",
            str(out),
        ])
        return bool(ok and out.is_file() and out.stat().st_size > 0)

    try:
        if _still_at("1"):
            return str(out)
    except Exception:
        pass
    # Retry from start for very short clips
    try:
        if _still_at("0"):
            return str(out)
    except Exception:
        pass
    return None


def pixmap_for(media_path: str, size: QSize | None = None) -> QPixmap:
    """Load a cached thumbnail as QPixmap (empty on miss)."""
    ext = os.path.splitext(media_path or "")[1].lower()
    if ext in IMAGE_EXTS and os.path.isfile(media_path):
        pix = QPixmap(media_path)
    else:
        path = ensure_thumbnail(media_path)
        if not path:
            return QPixmap()
        pix = QPixmap(path)
    if pix.isNull():
        return QPixmap()
    if size and not size.isEmpty():
        return pix.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
    return pix


def extract_filmstrip(
    media_path: str,
    count: int = 24,
    height: int = 40,
    progress_callback=None,
) -> list[str]:
    """Extract evenly spaced JPEG frames for a timeline filmstrip."""
    if not media_path or not os.path.isfile(media_path):
        return []
    ext = os.path.splitext(media_path)[1].lower()
    if ext not in VIDEO_EXTS:
        return []
    n = max(4, min(48, int(count or 24)))
    abs_path = os.path.abspath(media_path)
    mtime = os.path.getmtime(abs_path)
    key = hashlib.sha1(f"{abs_path}|strip|{n}|{height}|{mtime}".encode()).hexdigest()[:16]
    out_dir = THUMB_DIR / "strips" / key
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = sorted(str(p) for p in out_dir.glob("f_*.jpg") if p.stat().st_size > 0)
    if len(frames) >= max(3, n // 2):
        return frames
    if progress_callback:
        progress_callback(10, "Extracting timeline footage…")
    dur = probe_duration(abs_path) or 10.0
    interval = max(0.25, dur / n)
    pattern = str(out_dir / "f_%03d.jpg")
    cmd = [
        _ffmpeg_exe(),
        "-hide_banner",
        "-loglevel", "error",
        "-i", abs_path,
        "-vf", f"fps=1/{interval:.3f},scale=-2:{int(height)}:force_original_aspect_ratio=decrease",
        "-frames:v", str(n),
        "-q:v", "5",
        "-y",
        pattern,
    ]
    try:
        subprocess.run(cmd, check=True, timeout=90, capture_output=True)
    except Exception:
        cmd = [
            _ffmpeg_exe(),
            "-hide_banner",
            "-loglevel", "error",
            "-i", abs_path,
            "-vf", f"fps=0.5,scale=-2:{int(height)}",
            "-frames:v", str(n),
            "-q:v", "5",
            "-y",
            pattern,
        ]
        try:
            subprocess.run(cmd, check=True, timeout=90, capture_output=True)
        except Exception:
            return frames
    frames = sorted(str(p) for p in out_dir.glob("f_*.jpg") if p.stat().st_size > 0)
    if progress_callback:
        progress_callback(100, f"{len(frames)} footage frames")
    return frames


def icon_for(media_path: str, size: int = 64) -> QIcon:
    """Thumbnail wrapped as QIcon with rounded dark letterbox."""
    target = QSize(size, size)
    src = pixmap_for(media_path, target)
    if src.isNull():
        return QIcon()

    canvas = QPixmap(target)
    canvas.fill(QColor("#0b1016"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # Center-crop into square
    x = max(0, (src.width() - size) // 2)
    y = max(0, (src.height() - size) // 2)
    cropped = src.copy(x, y, min(size, src.width()), min(size, src.height()))
    painter.drawPixmap(0, 0, cropped.scaled(target, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation))

    # Subtle bottom shade
    painter.fillRect(0, size - 14, size, 14, QBrush(QColor(0, 0, 0, 90)))
    painter.end()
    return QIcon(canvas)

