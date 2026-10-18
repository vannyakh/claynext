"""Bridge to backends/ffmpeg (claynext-ffmpeg)."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from claynext.adapters.rust_bridge.codecs import RustHardwareCodecsAdapter
from claynext.adapters.rust_bridge.process import _find_binary, _run_rust, _run_rust_stream
from claynext.models.media import (
    AudioStreamInfo,
    DecodedAudioChunk,
    DecodedVideoFrame,
    MediaMetadata,
    MediaType,
    VideoStreamInfo,
)

logger = logging.getLogger("claynext.adapters.rust")


def _ffmpeg_out_time(line: str) -> float | None:
    text = (line or "").strip()
    if text.startswith("out_time_us=") or text.startswith("out_time_ms="):
        raw = text.split("=", 1)[1].strip()
        try:
            return int(raw) / 1_000_000.0
        except ValueError:
            return None
    if text.startswith("out_time="):
        parts = text.split("=", 1)[1].strip().split(":")
        if len(parts) != 3:
            return None
        try:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except ValueError:
            return None
    return None


def _media_duration_seconds(exe: str, path: Path) -> float:
    try:
        proc = subprocess.run(
            [exe, "-hide_banner", "-i", str(path)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
        )
    except Exception:
        return 0.0
    text = (proc.stderr or "") + (proc.stdout or "")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        return 0.0
    return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))


def _parse_progress_event(line: str) -> tuple[float, str] | None:
    text = (line or "").strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("event") != "progress":
        return None
    try:
        pct = float(data.get("pct") or 0.0)
    except (TypeError, ValueError):
        pct = 0.0
    return max(0.0, min(100.0, pct)), str(data.get("message") or "")


class RustFfmpegAdapter:
    """Interfaces with `backends/ffmpeg` (claynext-ffmpeg)."""

    @classmethod
    def is_available(cls) -> bool:
        return _find_binary("claynext-ffmpeg") is not None

    @classmethod
    def probe(cls, file_path: str | Path) -> MediaMetadata | None:
        binary = _find_binary("claynext-ffmpeg")
        if not binary:
            return None
        try:
            res = _run_rust(binary, ["probe", str(file_path)], timeout=60)
            if res.returncode != 0:
                raise RuntimeError(res.stderr.strip() or "probe failed")
            raw = json.loads(res.stdout)
            return cls._parse_metadata(raw)
        except Exception as e:
            logger.warning(f"Rust probe failed on {file_path}: {e}")
            return None

    @classmethod
    def extract_frame_rgba(
        cls,
        file_path: str | Path,
        timestamp_secs: float,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> DecodedVideoFrame | None:
        """Probe-level frame extract (CLI logs dims). Prefer extract_still for previews."""
        binary = _find_binary("claynext-ffmpeg")
        if not binary:
            return None
        try:
            args = ["extract-frame", str(file_path), f"{timestamp_secs:.3f}"]
            if width:
                args.append(str(int(width)))
            if height:
                args.append(str(int(height)))
            res = _run_rust(binary, args, timeout=60)
            if res.returncode != 0:
                raise RuntimeError(res.stderr.strip() or "extract-frame failed")
            logger.debug("Rust extract-frame: %s", res.stdout.strip())
            return None
        except Exception as e:
            logger.warning(f"Rust frame extraction failed: {e}")
            return None

    @classmethod
    def extract_still(
        cls,
        file_path: str | Path,
        output_path: str | Path,
        *,
        timestamp_secs: float = 1.0,
        max_width: int | None = 160,
    ) -> bool:
        """Write a JPEG/PNG still via claynext-ffmpeg (thumbnails / posters)."""
        binary = _find_binary("claynext-ffmpeg")
        if not binary:
            return False
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            args = [
                "extract-still",
                str(file_path),
                str(out),
                f"{float(timestamp_secs):.3f}",
            ]
            if max_width:
                args.append(str(int(max_width)))
            res = _run_rust(binary, args, timeout=30)
            if res.returncode == 0 and out.is_file() and out.stat().st_size > 0:
                return True
            # Short clips: retry from t=0
            if timestamp_secs > 0:
                args[3] = "0.000"
                res = _run_rust(binary, args, timeout=30)
                return res.returncode == 0 and out.is_file() and out.stat().st_size > 0
            return False
        except Exception as e:
            logger.warning("Rust still extraction failed: %s", e)
            return False

    @classmethod
    def decode_audio_pcm_f32(
        cls,
        file_path: str | Path,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
        max_samples: int = 0,
    ) -> DecodedAudioChunk | None:
        """Decode media to PCM f32 via claynext-ffmpeg (writes temp .f32 then loads)."""
        binary = _find_binary("claynext-ffmpeg")
        if not binary:
            return None
        import tempfile

        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".f32", delete=False) as tmp:
                tmp_path = tmp.name
            res = _run_rust(
                binary,
                [
                    "decode-audio",
                    str(file_path),
                    str(int(sample_rate)),
                    str(int(channels)),
                    tmp_path,
                ],
                timeout=300,
            )
            if res.returncode != 0:
                raise RuntimeError(res.stderr.strip() or "decode-audio failed")
            raw = Path(tmp_path).read_bytes() if tmp_path else b""
            if not raw:
                return None
            meta: dict[str, Any] = {}
            try:
                meta = json.loads((res.stdout or "").strip() or "{}")
            except Exception:
                meta = {}
            rate = int(meta.get("sample_rate") or sample_rate)
            ch = int(meta.get("channels") or channels)
            # Optionally load a preview of float samples for callers that need them.
            samples: list[float] = []
            if max_samples > 0:
                import array

                arr = array.array("f")
                arr.frombytes(raw[: min(len(raw), max_samples * 4)])
                samples = list(arr)
            return DecodedAudioChunk(
                sample_rate=rate,
                channels=ch,
                pts=0.0,
                samples=samples,
                raw_pcm=raw,
            )
        except Exception as e:
            logger.warning(f"Rust audio decode failed: {e}")
            return None
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @classmethod
    def demux_audio(
        cls,
        media_path: str | Path,
        output_wav: str | Path,
        *,
        sample_rate: int = 48000,
        channels: int = 2,
    ) -> bool:
        """Extract PCM WAV via claynext-ffmpeg demux-audio."""
        binary = _find_binary("claynext-ffmpeg")
        if not binary:
            return False
        out = Path(output_wav)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            res = _run_rust(
                binary,
                [
                    "demux-audio",
                    str(media_path),
                    str(out),
                    str(int(sample_rate)),
                    str(int(channels)),
                ],
                timeout=600,
            )
            return res.returncode == 0 and out.is_file() and out.stat().st_size > 0
        except Exception as e:
            logger.warning("Rust demux-audio failed: %s", e)
            return False

    @classmethod
    def mux_video_audio(
        cls, video_path: str | Path, audio_path: str | Path, output_path: str | Path
    ) -> bool:
        binary = _find_binary("claynext-ffmpeg")
        if not binary:
            return False
        try:
            res = _run_rust(
                binary,
                ["mux", str(video_path), str(audio_path), str(output_path)],
                timeout=600,
            )
            return res.returncode == 0 and Path(output_path).is_file()
        except Exception as e:
            logger.warning(f"Rust mux failed: {e}")
            return False

    @classmethod
    def mux_with_progress(
        cls,
        video_path: str | Path,
        audio_path: str | Path,
        output_path: str | Path,
        *,
        reencode: bool = False,
        audio_bitrate: str = "256k",
        video_filter: str = "",
        crf: int = 18,
        preset: str = "medium",
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> None:
        """Mux (and optionally re-encode) through claynext-ffmpeg, streaming encode percent.

        Raises FileNotFoundError when the binary is missing, RuntimeError when encode fails.
        """
        binary = _find_binary("claynext-ffmpeg")
        if not binary:
            raise FileNotFoundError("claynext-ffmpeg")
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        digits = "".join(ch for ch in str(audio_bitrate) if ch.isdigit())
        kbps = int(digits or "256")
        args = [
            "mux",
            str(video_path),
            str(audio_path),
            str(out),
            "--audio-bitrate",
            str(kbps),
        ]
        if reencode or video_filter:
            args += ["--reencode", "--crf", str(int(crf)), "--preset", preset or "medium"]
        if video_filter:
            args += ["--vf", video_filter]

        def _on_line(line: str) -> None:
            parsed = _parse_progress_event(line)
            if parsed and progress_callback:
                progress_callback(parsed[0], parsed[1])

        res = _run_rust_stream(binary, args, _on_line, timeout=None)
        if res.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
            err = (res.stderr or res.stdout or "").strip()
            raise RuntimeError(err or "Failed to mux dubbed video.")

    @classmethod
    def transcode_video(
        cls,
        input_path: str | Path,
        output_path: str | Path,
        video_codec: str = "libx264",
        crf: int = 21,
        *,
        width: int | None = None,
        height: int | None = None,
        preset: str = "veryfast",
        audio_codec: str = "aac",
        sample_rate: int = 44100,
        channels: int = 2,
        audio_bitrate_kbps: int = 192,
        start_time_secs: float | None = None,
        duration_secs: float | None = None,
        prefer_hardware: bool = False,
        progress_callback: Callable[[float], None] | None = None,
    ) -> bool:
        """
        Transcode / trim / scale for edit export and Qt-safe preview proxies.
        Prefers claynext-ffmpeg; falls back to bundled imageio-ffmpeg.
        """
        inp = Path(input_path)
        out = Path(output_path)
        if not inp.is_file():
            return False
        out.parent.mkdir(parents=True, exist_ok=True)
        if progress_callback:
            progress_callback(0.0)

        codec = (video_codec or "libx264").strip()
        # Stream-copy is not a Qt-safe playback convert — force a real encode.
        if codec in {"", "copy", "auto"}:
            codec = "libx264"

        if prefer_hardware and codec == "libx264":
            hw = RustHardwareCodecsAdapter.get_optimal_encoder_args(prefer_hevc=False)
            for i, a in enumerate(hw):
                if a == "-c:v" and i + 1 < len(hw):
                    candidate = hw[i + 1]
                    # Keep H.264 family for widest Qt playback support.
                    if "264" in candidate or candidate.endswith("_mf"):
                        codec = candidate
                    break

        binary = _find_binary("claynext-ffmpeg")
        if binary:
            try:
                args = [
                    "export",
                    str(inp),
                    str(out),
                    "--codec", codec,
                    "--crf", str(int(crf)),
                    "--preset", preset or "veryfast",
                    "--sample-rate", str(int(sample_rate)),
                    "--channels", str(int(channels)),
                    "--audio-bitrate", str(int(audio_bitrate_kbps)),
                ]
                if width:
                    args += ["--width", str(int(width))]
                if height:
                    args += ["--height", str(int(height))]
                if start_time_secs is not None:
                    args += ["--start", f"{float(start_time_secs):.3f}"]
                if duration_secs is not None:
                    args += ["--duration", f"{float(duration_secs):.3f}"]

                def _on_line(line: str) -> None:
                    parsed = _parse_progress_event(line)
                    if parsed and progress_callback:
                        progress_callback(float(parsed[0]))

                res = _run_rust_stream(binary, args, _on_line, timeout=None)
                if res.returncode == 0 and out.is_file() and out.stat().st_size > 0:
                    if progress_callback:
                        progress_callback(100.0)
                    return True
                logger.warning(
                    "Rust export failed (rc=%s): %s",
                    res.returncode,
                    (res.stderr or res.stdout or "").strip()[:400],
                )
            except Exception as e:
                logger.warning("Rust export failed, falling back to imageio-ffmpeg: %s", e)

        ok = cls._transcode_via_imageio(
            inp,
            out,
            video_codec=codec if "264" in codec or codec.startswith("libx") else "libx264",
            crf=crf,
            width=width,
            height=height,
            preset=preset,
            audio_codec=audio_codec,
            sample_rate=sample_rate,
            channels=channels,
            audio_bitrate_kbps=audio_bitrate_kbps,
            start_time_secs=start_time_secs,
            duration_secs=duration_secs,
            progress_callback=progress_callback,
        )
        if ok and progress_callback:
            progress_callback(100.0)
        return ok

    @staticmethod
    def _transcode_via_imageio(
        input_path: Path,
        output_path: Path,
        *,
        video_codec: str,
        crf: int,
        width: int | None,
        height: int | None,
        preset: str = "veryfast",
        audio_codec: str,
        sample_rate: int,
        channels: int,
        audio_bitrate_kbps: int = 192,
        start_time_secs: float | None = None,
        duration_secs: float | None = None,
        progress_callback: Callable[[float], None] | None = None,
    ) -> bool:
        try:
            import imageio_ffmpeg
        except Exception as e:
            logger.warning("imageio-ffmpeg unavailable for transcode: %s", e)
            return False
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        args: list[str] = [
            exe, "-y", "-hide_banner", "-nostats", "-loglevel", "error",
            "-stats_period", "0.016", "-progress", "pipe:1",
        ]
        if start_time_secs is not None:
            args += ["-ss", f"{float(start_time_secs):.3f}"]
        args += ["-i", str(input_path)]
        if duration_secs is not None:
            args += ["-t", f"{float(duration_secs):.3f}"]
        args += [
            "-c:v", video_codec,
            "-preset", preset or "veryfast",
            "-crf", str(int(crf)),
            "-pix_fmt", "yuv420p",
        ]
        if width and height:
            args += ["-vf", f"scale={int(width)}:{int(height)}"]
        elif height:
            args += ["-vf", f"scale=-2:{int(height)}"]
        elif width:
            args += ["-vf", f"scale={int(width)}:-2"]
        args += [
            "-c:a", audio_codec or "aac",
            "-b:a", f"{int(audio_bitrate_kbps)}k",
            "-ar", str(int(sample_rate)),
            "-ac", str(int(channels)),
            "-movflags", "+faststart",
            str(output_path),
        ]
        duration = float(duration_secs or 0.0)
        if duration <= 0:
            duration = _media_duration_seconds(exe, input_path)
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
            err_parts: list[str] = []

            def _drain() -> None:
                if proc.stderr is not None:
                    err_parts.append(proc.stderr.read())

            thread = threading.Thread(target=_drain, daemon=True)
            thread.start()
            if proc.stdout is not None:
                for line in proc.stdout:
                    parsed = _ffmpeg_out_time(line)
                    if parsed is None or duration <= 0 or not progress_callback:
                        continue
                    progress_callback(min(99.0, parsed / duration * 100.0))
            proc.wait()
            thread.join(timeout=2)
            if proc.returncode != 0:
                logger.warning("imageio-ffmpeg transcode failed: %s", "".join(err_parts)[:400])
                return False
            return output_path.is_file() and output_path.stat().st_size > 0
        except Exception as e:
            logger.warning("imageio-ffmpeg transcode failed: %s", e)
            return False

    @classmethod
    def extract_audio_pcm(
        cls,
        file_path: str | Path,
        sample_rate: int = 44100,
        channels: int = 2,
    ) -> DecodedAudioChunk | None:
        """Alias used by RustCoreAdapter — delegates to decode_audio_pcm_f32."""
        return cls.decode_audio_pcm_f32(file_path, sample_rate=sample_rate, channels=channels)

    @staticmethod
    def _parse_metadata(raw: dict[str, Any]) -> MediaMetadata:
        path = str(raw.get("filepath") or "")
        format_name = str(raw.get("format_name") or "")
        duration = float(raw.get("duration_seconds") or 0.0)
        size_bytes = int(raw.get("size_bytes") or 0)
        bit_rate = int(raw.get("bit_rate") or 0)

        v_stream: VideoStreamInfo | None = None
        a_stream: AudioStreamInfo | None = None
        media_type = MediaType.UNKNOWN

        for s in raw.get("streams", []):
            st_type = str(s.get("codec_type") or "").lower()
            details = s.get("stream_details") or {}
            kind = details.get("kind")

            if st_type == "video" or kind == "Video":
                media_type = MediaType.VIDEO
                v_stream = VideoStreamInfo(
                    width=int(details.get("width") or 0),
                    height=int(details.get("height") or 0),
                    codec=str(s.get("codec_name") or ""),
                    pixel_format=str(details.get("pixel_format") or "yuv420p"),
                    bit_rate=int(details.get("bit_rate") or 0),
                    rotation=int(details.get("rotation_degrees") or 0),
                    is_vfr=bool(details.get("is_vfr") or False),
                )
            elif st_type == "audio" or kind == "Audio":
                if media_type != MediaType.VIDEO:
                    media_type = MediaType.AUDIO
                a_stream = AudioStreamInfo(
                    sample_rate=int(details.get("sample_rate") or 44100),
                    channels=int(details.get("channels") or 2),
                    codec=str(s.get("codec_name") or ""),
                    bit_rate=int(details.get("bit_rate") or 0),
                    channel_layout=str(details.get("channel_layout") or "stereo"),
                )

        return MediaMetadata(
            path=path,
            media_type=media_type,
            format_name=format_name,
            duration=duration,
            file_size_bytes=size_bytes,
            bit_rate=bit_rate,
            video_stream=v_stream,
            audio_stream=a_stream,
        )


