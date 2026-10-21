"""
FFmpeg infrastructure adapter.

Coordinates between the native Rust FFmpeg backend and imageio-ffmpeg subprocess fallback.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from claynext.adapters.rust_bridge import RustFfmpegAdapter
from claynext.models.media import AudioStreamInfo, MediaMetadata, MediaType, VideoStreamInfo

logger = logging.getLogger("claynext.adapters.ffmpeg")


def probe_media(file_path: str | Path) -> MediaMetadata:
    """Probe media metadata using Rust core probe, then the bundled ffmpeg banner."""
    p = Path(file_path)
    if not p.is_file():
        return MediaMetadata(path=str(p), media_type=MediaType.UNKNOWN)

    rust_meta = RustFfmpegAdapter.probe(p)
    if rust_meta:
        return rust_meta

    banner = _probe_with_bundled_ffmpeg(p)
    if banner is not None:
        return banner
    return MediaMetadata(path=str(p), media_type=MediaType.UNKNOWN)


_CHANNEL_COUNTS = {
    "mono": 1,
    "stereo": 2,
    "2.1": 3,
    "3.0": 3,
    "4.0": 4,
    "quad": 4,
    "5.0": 5,
    "5.1": 6,
    "6.1": 7,
    "7.1": 8,
}


def _split_banner_fields(payload: str) -> list[str]:
    fields: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in payload:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            fields.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        fields.append(tail)
    return fields


def _first_token(field: str) -> str:
    raw = field.strip()
    if not raw:
        return ""
    return raw.split()[0].split("(")[0]


def _channel_count(label: str) -> int:
    head = label.strip().lower().split("(")[0].strip()
    if head in _CHANNEL_COUNTS:
        return _CHANNEL_COUNTS[head]
    match = re.match(r"(\d+)\s+channels?\b", head)
    if match:
        return int(match.group(1))
    return 2


def _is_channel_field(field: str) -> bool:
    head = field.strip().lower().split("(")[0].strip()
    if head in _CHANNEL_COUNTS or "channel" in head:
        return True
    return False


def metadata_from_ffmpeg_banner(path: str | Path, text: str) -> MediaMetadata | None:
    """Build metadata from an `ffmpeg -i` banner. ffmpeg exits 1 when used this way."""
    if "Duration:" not in text and "Stream #" not in text:
        return None
    p = Path(path)
    try:
        size = p.stat().st_size if p.is_file() else 0
    except OSError:
        size = 0

    format_name = ""
    fmt = re.search(r"Input #\d+,\s*(.+?),\s*from\s+", text)
    if fmt:
        format_name = fmt.group(1).strip()

    duration = 0.0
    dur = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if dur:
        duration = int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3))

    bit_rate = 0
    br = re.search(r"bitrate:\s*(\d+(?:\.\d+)?)\s*kb/s", text)
    if br:
        bit_rate = int(float(br.group(1)) * 1000)

    video: VideoStreamInfo | None = None
    audio: AudioStreamInfo | None = None
    media_type = MediaType.UNKNOWN
    for match in re.finditer(
        r"Stream #\d+:\d+.*?:\s*(Video|Audio):\s*(.*)",
        text,
        flags=re.IGNORECASE,
    ):
        kind = match.group(1).lower()
        fields = _split_banner_fields(match.group(2))
        if not fields:
            continue
        codec = _first_token(fields[0]) or "unknown"
        if kind == "video" and video is None:
            width = height = 0
            pixel_format = "yuv420p"
            fps = 0.0
            tbr = 0.0
            stream_rate = 0
            for field in fields[1:]:
                size_match = re.search(r"(\d{2,5})x(\d{2,5})", field)
                if size_match and width == 0:
                    width = int(size_match.group(1))
                    height = int(size_match.group(2))
                fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", field)
                if fps_match:
                    fps = float(fps_match.group(1))
                tbr_match = re.search(r"(\d+(?:\.\d+)?)\s*tbr", field)
                if tbr_match:
                    tbr = float(tbr_match.group(1))
                kbps = re.search(r"(\d+(?:\.\d+)?)\s*kb/s", field)
                if kbps:
                    stream_rate = int(float(kbps.group(1)) * 1000)
                token = _first_token(field).lower()
                if token.startswith(("yuv", "rgb", "bgr", "gray", "gbr", "nv", "pal", "mono", "ya")):
                    pixel_format = token
            media_type = MediaType.VIDEO
            video = VideoStreamInfo(
                width=width,
                height=height,
                codec=codec,
                pixel_format=pixel_format,
                frame_rate=fps or tbr or 0.0,
                bit_rate=stream_rate,
                duration=duration,
                is_vfr=bool(fps and tbr and abs(fps - tbr) > 0.1),
            )
        elif kind == "audio" and audio is None:
            sample_rate = 0
            channels = 2
            layout = "stereo"
            stream_rate = 0
            for field in fields[1:]:
                hz = re.search(r"(\d+)\s*Hz", field)
                if hz:
                    sample_rate = int(hz.group(1))
                kbps = re.search(r"(\d+(?:\.\d+)?)\s*kb/s", field)
                if kbps:
                    stream_rate = int(float(kbps.group(1)) * 1000)
                if _is_channel_field(field):
                    layout = field.strip()
                    channels = _channel_count(field)
            if media_type != MediaType.VIDEO:
                media_type = MediaType.AUDIO
            audio = AudioStreamInfo(
                sample_rate=sample_rate or 44100,
                channels=channels,
                codec=codec,
                bit_rate=stream_rate,
                duration=duration,
                channel_layout=layout,
            )

    rotate = re.search(r"rotate\s*:\s*(-?\d+)", text)
    if video is not None and rotate:
        video.rotation = int(rotate.group(1))

    if duration <= 0 and video is None and audio is None:
        return None
    return MediaMetadata(
        path=str(p),
        media_type=media_type,
        format_name=format_name,
        duration=duration,
        file_size_bytes=size,
        bit_rate=bit_rate,
        video_stream=video,
        audio_stream=audio,
    )


def _probe_with_bundled_ffmpeg(path: Path) -> MediaMetadata | None:
    try:
        from claynext.adapters.ffmpeg_service import ffmpeg_exe

        proc = subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-nostdin", "-i", str(path)],
            capture_output=True,
            timeout=30,
            check=False,
            text=True,
            errors="replace",
        )
    except Exception as exc:
        logger.warning("Bundled ffmpeg probe failed on %s: %s", path, exc)
        return None
    text = (proc.stderr or "") + (proc.stdout or "")
    meta = metadata_from_ffmpeg_banner(path, text)
    if meta is None:
        logger.warning("Bundled ffmpeg probe found no streams in %s", path)
    return meta


def _duration_from_banner(file_path: str | Path) -> float:
    """Read Duration: from ffmpeg -i when the probe report has no length."""
    import re

    path = Path(file_path)
    if not path.is_file():
        return 0.0
    try:
        from claynext.adapters.ffmpeg_service import ffmpeg_exe

        proc = subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-i", str(path)],
            capture_output=True,
            timeout=30,
            check=False,
            text=True,
            errors="replace",
        )
    except Exception as exc:
        logger.warning("Duration banner failed on %s: %s", path, exc)
        return 0.0
    text = (proc.stderr or "") + (proc.stdout or "")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        return 0.0
    hours, minutes, seconds = int(match.group(1)), int(match.group(2)), float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def probe_duration(file_path: str | Path) -> float:
    """Return exact duration in seconds from native Rust probe."""
    meta = probe_media(file_path)
    dur = float(getattr(meta, "duration", 0.0) or 0.0) if meta else 0.0
    if dur > 0.05:
        return dur
    return _duration_from_banner(file_path)


class FFmpegResult(subprocess.CompletedProcess):
    """
    CompletedProcess subclass that evaluates to True when returncode == 0,
    supporting both boolean checks (`if ok:`) and subprocess attributes (`proc.returncode`).
    """

    def __bool__(self) -> bool:
        return self.returncode == 0


def run_ffmpeg(args: list[str], timeout: int = 600, **kwargs: Any) -> FFmpegResult:
    """
    Convenience wrapper over ffmpeg_service.run_ffmpeg (bundled binary).
    Accepts timeout and extra keyword arguments, returning an FFmpegResult that acts as
    both a boolean and a CompletedProcess.
    """
    try:
        from claynext.adapters.ffmpeg_service import run_ffmpeg as _run

        argv = list(args)
        if "-y" not in argv:
            argv = ["-y", *argv]
        res = _run(argv, timeout=timeout, **kwargs)
        return FFmpegResult(res.args, res.returncode, res.stdout, res.stderr)
    except Exception as e:
        logger.warning(f"run_ffmpeg error: {e}")
        return FFmpegResult(args, 1, b"", str(e).encode())


class FFmpegAdapter:
    """Orchestrates media probing and stream processing via Rust core."""

    @staticmethod
    def probe(file_path: str | Path) -> MediaMetadata:
        return probe_media(file_path)

    @staticmethod
    def duration(file_path: str | Path) -> float:
        return probe_duration(file_path)

    @staticmethod
    def extract_crop(
        file_path: str | Path,
        output_path: str | Path,
        *,
        timestamp_secs: float = 0.0,
        x: float = 0.0,
        y: float = 0.72,
        w: float = 1.0,
        h: float = 0.2,
    ) -> bool:
        """Playhead crop via claynext-ffmpeg."""
        return RustFfmpegAdapter.extract_crop(
            file_path,
            output_path,
            timestamp_secs=timestamp_secs,
            x=x,
            y=y,
            w=w,
            h=h,
        )

    @staticmethod
    def extract_still(
        file_path: str | Path,
        output_path: str | Path,
        *,
        timestamp_secs: float = 1.0,
        max_width: int | None = 160,
    ) -> bool:
        """Still frame via claynext-ffmpeg."""
        return RustFfmpegAdapter.extract_still(
            file_path,
            output_path,
            timestamp_secs=timestamp_secs,
            max_width=max_width,
        )

    @staticmethod
    def demux_audio(
        media_path: str | Path,
        output_wav: str | Path,
        *,
        sample_rate: int = 48000,
        channels: int = 2,
    ) -> bool:
        """PCM WAV demux via claynext-ffmpeg."""
        return RustFfmpegAdapter.demux_audio(
            media_path, output_wav, sample_rate=sample_rate, channels=channels
        )

    @staticmethod
    def decode_audio_pcm_f32(
        file_path: str | Path,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
    ):
        """PCM f32 decode via claynext-ffmpeg (None if unavailable)."""
        return RustFfmpegAdapter.decode_audio_pcm_f32(
            file_path, sample_rate=sample_rate, channels=channels
        )

    @staticmethod
    def is_rust_available() -> bool:
        return RustFfmpegAdapter.is_available()


_ffmpeg_adapter: FFmpegAdapter | None = None


def get_ffmpeg_adapter() -> FFmpegAdapter:
    global _ffmpeg_adapter
    if _ffmpeg_adapter is None:
        _ffmpeg_adapter = FFmpegAdapter()
    return _ffmpeg_adapter


# Re-export audio and video transcoding utilities from ffmpeg_service
from claynext.adapters.ffmpeg_service import (
    demux_wav,
    dynamic_duck_audio,
    ensure_speech_bed,
    fit_duration,
    master_voiceover_track,
    mix_wavs,
    compose_overlays,
    mux_video,
    overlay_clips,
    volume_wav,
    make_silence,
    concat_videos,
    mix_timeline_audio,
    render_timeline,
)


