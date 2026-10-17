"""
Rust Core Backends Adapter.

Provides direct access to the high-performance native Rust core tools:
1. RustFfmpegAdapter: Fast probing, accurate/fast frame extraction, PCM f32 stream decoding, export transcode, stream-copy demuxing, and audio/video muxing.
2. RustHardwareCodecsAdapter: Detection of system GPUs, NVENC, QSV, AMF, D3D11VA and automatic selection of optimal hardware encoder flags.
3. RustCpuAdapter: SIMD audio stats (Peak, RMS), waveform visualizer downsampling, linear audio resampling, multi-track mixing.
4. RustAiAdapter: VAD energy chunking, Whisper ASR configs, DirectML/CUDA execution provider selection.
5. RustWgpuAdapter: WGPU hardware info, compute shader specifications.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from claynext.models.hardware import CodecProfile, GpuCapability, GpuVendor
from claynext.models.media import (
    AudioStreamInfo,
    DecodedAudioChunk,
    DecodedVideoFrame,
    MediaMetadata,
    MediaType,
    VideoStreamInfo,
)
from claynext.utils.paths import BASE_DIR

logger = logging.getLogger("claynext.adapters.rust")

BACKENDS_DIR = BASE_DIR / "backends"
TARGET_DIR = BASE_DIR / "target" / "debug"
RELEASE_TARGET_DIR = BASE_DIR / "target" / "release"
LEGACY_TARGET_DIR = BACKENDS_DIR / "target" / "debug"
LEGACY_RELEASE_TARGET_DIR = BACKENDS_DIR / "target" / "release"


def _find_binary(bin_name: str) -> Path | None:
    ext = ".exe" if os.name == "nt" else ""
    full_name = f"{bin_name}{ext}"
    dirs: list[Path] = [RELEASE_TARGET_DIR, TARGET_DIR, LEGACY_RELEASE_TARGET_DIR, LEGACY_TARGET_DIR]
    # Honour cargo target override (CI / sandboxed builds).
    cargo_target = os.environ.get("CARGO_TARGET_DIR")
    if cargo_target:
        root = Path(cargo_target)
        dirs = [root / "release", root / "debug", *dirs]
    for candidate_dir in dirs:
        p = candidate_dir / full_name
        if p.is_file():
            return p
    return None


def _ensure_bundled_ffmpeg_env() -> None:
    """Point the Rust FFmpeg backend at imageio-ffmpeg when system PATH has no ffmpeg."""
    if os.environ.get("CLAYNEXT_FFMPEG_PATH"):
        return
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            os.environ["CLAYNEXT_FFMPEG_PATH"] = exe
            # ffprobe is optional; probe falls back to ffmpeg -i when missing.
    except Exception:
        pass


def _run_rust(
    binary: Path,
    args: list[str],
    *,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    _ensure_bundled_ffmpeg_env()
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.run(
        [str(binary), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        creationflags=creationflags,
    )


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
    ) -> DecodedAudioChunk | None:
        binary = _find_binary("claynext-ffmpeg")
        if not binary:
            return None
        try:
            res = _run_rust(
                binary,
                ["decode-audio", str(file_path), str(int(sample_rate)), str(int(channels))],
                timeout=300,
            )
            if res.returncode != 0:
                raise RuntimeError(res.stderr.strip() or "decode-audio failed")
            logger.debug("Rust decode-audio: %s", res.stdout.strip())
            # CLI currently reports stats only; PCM pipe ABI lands later.
            return None
        except Exception as e:
            logger.warning(f"Rust audio decode failed: {e}")
            return None

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
                ]
                if width:
                    args += ["--width", str(int(width))]
                if height:
                    args += ["--height", str(int(height))]
                if start_time_secs is not None:
                    args += ["--start", f"{float(start_time_secs):.3f}"]
                if duration_secs is not None:
                    args += ["--duration", f"{float(duration_secs):.3f}"]
                res = _run_rust(binary, args, timeout=None)
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
            start_time_secs=start_time_secs,
            duration_secs=duration_secs,
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
        start_time_secs: float | None = None,
        duration_secs: float | None = None,
    ) -> bool:
        try:
            import imageio_ffmpeg
        except Exception as e:
            logger.warning("imageio-ffmpeg unavailable for transcode: %s", e)
            return False
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        args: list[str] = [exe, "-y", "-hide_banner", "-loglevel", "error"]
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
            "-ar", str(int(sample_rate)),
            "-ac", str(int(channels)),
            "-movflags", "+faststart",
            str(output_path),
        ]
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            subprocess.run(args, check=True, capture_output=True, creationflags=creationflags)
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


class RustHardwareCodecsAdapter:
    """Interfaces with `backends/hardware-codecs` (claynext-codecs)."""

    @classmethod
    def is_available(cls) -> bool:
        return _find_binary("claynext-codecs") is not None

    @classmethod
    def detect_gpus(cls) -> list[GpuCapability]:
        binary = _find_binary("claynext-codecs")
        if not binary:
            return []
        try:
            res = subprocess.run(
                [str(binary), "detect"], capture_output=True, text=True, check=True
            )
            raw_list = json.loads(res.stdout)
            gpus = []
            for item in raw_list:
                vendor_str = str(item.get("vendor") or "unknown").lower()
                vendor = GpuVendor.UNKNOWN
                for v in GpuVendor:
                    if v.value == vendor_str:
                        vendor = v
                        break
                gpus.append(
                    GpuCapability(
                        name=str(item.get("name") or "Unknown GPU"),
                        vendor=vendor,
                        driver_version=item.get("driver_version"),
                        supports_nvenc=bool(item.get("supports_nvenc")),
                        supports_nvdec=bool(item.get("supports_nvdec")),
                        supports_qsv=bool(item.get("supports_qsv")),
                        supports_amf=bool(item.get("supports_amf")),
                        supports_d3d11va=bool(item.get("supports_d3d11va")),
                    )
                )
            return gpus
        except Exception as e:
            logger.warning(f"Rust GPU detection failed: {e}")
            return []

    @classmethod
    def get_optimal_encoder_args(cls, prefer_hevc: bool = False) -> list[str]:
        binary = _find_binary("claynext-codecs")
        if binary:
            try:
                flag = "--hevc" if prefer_hevc else "--h264"
                res = subprocess.run(
                    [str(binary), "ffmpeg-args", flag],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                args = res.stdout.strip().split()
                # Skip hevc_mf — Windows often has no HEVC Media Foundation encoder.
                if args and "hevc_mf" not in args:
                    return args
            except Exception as e:
                logger.warning(f"Rust optimal encoder query failed: {e}")

        # Software fallback (H.264 by default — widest Windows playback support)
        codec = "libx265" if prefer_hevc else "libx264"
        return ["-c:v", codec, "-crf", "20", "-preset", "faster"]


class RustCpuAdapter:
    """Interfaces with `backends/cpu` (claynext-cpu)."""

    @classmethod
    def is_available(cls) -> bool:
        return _find_binary("claynext-cpu") is not None

    @classmethod
    def run_benchmark(cls) -> str:
        binary = _find_binary("claynext-cpu")
        if not binary:
            return "Rust claynext-cpu binary not available"
        try:
            res = _run_rust(binary, ["benchmark"], timeout=120)
            if res.returncode != 0:
                return f"CPU benchmark failed: {res.stderr.strip()}"
            return res.stdout.strip()
        except Exception as e:
            return f"CPU benchmark failed: {e}"

    @classmethod
    def downsample_waveform(
        cls,
        raw_pcm_f32: bytes,
        target_bins: int = 2000,
    ) -> list[dict[str, float]]:
        """
        Peak/RMS bins for timeline waveform painting.
        Uses claynext-cpu when present; otherwise a fast Python downsample.
        """
        bins = max(1, int(target_bins))
        if not raw_pcm_f32:
            return [{"min": 0.0, "max": 0.0, "rms": 0.0} for _ in range(bins)]

        binary = _find_binary("claynext-cpu")
        if binary:
            try:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".f32", delete=False) as tmp:
                    tmp.write(raw_pcm_f32)
                    tmp_path = tmp.name
                try:
                    res = _run_rust(
                        binary,
                        ["waveform", tmp_path, str(bins)],
                        timeout=60,
                    )
                    if res.returncode == 0 and res.stdout.strip():
                        data = json.loads(res.stdout)
                        if isinstance(data, list) and data:
                            return data
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
            except Exception as e:
                logger.debug("Rust waveform downsample failed, using Python: %s", e)

        import array
        import math

        samples = array.array("f")
        samples.frombytes(raw_pcm_f32)
        n = len(samples)
        if n == 0:
            return [{"min": 0.0, "max": 0.0, "rms": 0.0} for _ in range(bins)]
        out: list[dict[str, float]] = []
        for i in range(bins):
            a = (i * n) // bins
            b = max(a + 1, ((i + 1) * n) // bins)
            chunk = samples[a:b]
            lo = min(chunk)
            hi = max(chunk)
            acc = sum(s * s for s in chunk)
            rms = math.sqrt(acc / len(chunk)) if chunk else 0.0
            out.append({"min": float(lo), "max": float(hi), "rms": float(rms)})
        return out


class RustAiAdapter:
    """Interfaces with `backends/ai-runtime` (claynext-ai) and `crates/editor-ai`."""

    @classmethod
    def get_device_config(cls) -> dict[str, Any]:
        binary = _find_binary("claynext-ai")
        if binary:
            try:
                res = subprocess.run(
                    [str(binary), "device"], capture_output=True, text=True, check=True
                )
                return json.loads(res.stdout)
            except Exception as e:
                logger.warning(f"Rust AI device config failed: {e}")
        return {"provider": "DirectML", "device_id": 0, "num_threads": 4, "enable_fp16": True}

    @classmethod
    def vad_chunk(cls) -> list[dict[str, Any]]:
        binary = _find_binary("claynext-ai")
        if binary:
            try:
                res = subprocess.run(
                    [str(binary), "vad-sim"], capture_output=True, text=True, check=True
                )
                return json.loads(res.stdout)
            except Exception as e:
                logger.warning(f"Rust AI vad-sim failed: {e}")
        return []

    @classmethod
    def parse_retry_after(cls, status: int, header: str | None = None, body: str = "") -> tuple[bool, float]:
        binary = _find_binary("claynext-ai")
        if binary:
            try:
                args = [str(binary), "llm-parse-retry", str(status), header or "", body or ""]
                res = subprocess.run(args, capture_output=True, text=True, check=True)
                data = json.loads(res.stdout.strip())
                return bool(data.get("is_rate_limit", False)), float(data.get("retry_after_secs", 20.0))
            except Exception as e:
                logger.debug(f"Rust parse-retry failed, falling back: {e}")
        # Python fallback
        limited = status == 429 or "rate limit" in body.lower() or "resource_exhausted" in body.lower()
        return limited, 20.0

    @classmethod
    def acquire_llm_key(cls, keys: list[dict[str, Any]], provider: str) -> dict[str, Any] | None:
        binary = _find_binary("claynext-ai")
        if binary:
            try:
                keys_json = json.dumps(keys)
                res = subprocess.run(
                    [str(binary), "llm-acquire", keys_json, provider],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                raw = res.stdout.strip()
                if raw and raw != "null":
                    return json.loads(raw)
            except Exception as e:
                logger.debug(f"Rust acquire-key failed, falling back: {e}")
        return None

    @classmethod
    def soonest_cooldown(cls, keys: list[dict[str, Any]], provider: str) -> float:
        binary = _find_binary("claynext-ai")
        if binary:
            try:
                keys_json = json.dumps(keys)
                res = subprocess.run(
                    [str(binary), "llm-soonest-cooldown", keys_json, provider],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                data = json.loads(res.stdout.strip())
                return float(data.get("soonest_cooldown_secs", 0.0))
            except Exception as e:
                logger.debug(f"Rust soonest-cooldown failed, falling back: {e}")
        return 0.0

    @classmethod
    def parse_expression_tags(cls, text: str) -> list[dict[str, Any]]:
        binary = _find_binary("claynext-ai")
        if binary:
            try:
                res = subprocess.run(
                    [str(binary), "parse-expression-tags", text],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                return json.loads(res.stdout.strip())
            except Exception as e:
                logger.debug(f"Rust parse-expression-tags failed: {e}")
        return []

    @classmethod
    def chunk_subtitles(cls, text: str, max_chars: int = 1500) -> list[dict[str, Any]]:
        binary = _find_binary("claynext-ai")
        if binary:
            try:
                res = subprocess.run(
                    [str(binary), "chunk-subtitles", text, str(max_chars)],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                return json.loads(res.stdout.strip())
            except Exception as e:
                logger.debug(f"Rust chunk-subtitles failed: {e}")
        return []

    @classmethod
    def filter_ocr(cls, boxes: list[dict[str, Any]], min_confidence: float = 0.5) -> list[dict[str, Any]]:
        binary = _find_binary("claynext-ai")
        if binary:
            try:
                res = subprocess.run(
                    [str(binary), "filter-ocr", json.dumps(boxes), str(min_confidence)],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                return json.loads(res.stdout.strip())
            except Exception as e:
                logger.debug(f"Rust filter-ocr failed: {e}")
        return [b for b in boxes if float(b.get("confidence", 0.0)) >= min_confidence]



class RustWgpuAdapter:
    """Interfaces with `backends/wgpu` (claynext-wgpu)."""

    @classmethod
    def get_device_info(cls) -> dict[str, Any]:
        binary = _find_binary("claynext-wgpu")
        if binary:
            try:
                res = subprocess.run(
                    [str(binary), "info"], capture_output=True, text=True, check=True
                )
                return json.loads(res.stdout)
            except Exception as e:
                logger.warning(f"Rust WGPU info failed: {e}")
        return {"backend": "Primary", "preferred_format": "Rgba8Unorm"}


class RustCoreAdapter:
    """Unified access to all native Rust backend capabilities."""

    def __init__(self) -> None:
        self.ffmpeg = RustFfmpegAdapter
        self.codecs = RustHardwareCodecsAdapter
        self.cpu = RustCpuAdapter
        self.ai = RustAiAdapter
        self.wgpu = RustWgpuAdapter

    def probe_media(self, file_path: str | Path) -> dict[str, Any] | None:
        meta = self.ffmpeg.probe(file_path)
        if meta:
            return {
                "filepath": meta.path,
                "duration_seconds": meta.duration_seconds,
                "width": meta.width,
                "height": meta.height,
                "fps": meta.fps,
                "video_codec": meta.video_codec,
                "audio_codec": meta.audio_codec,
            }
        return None

    def extract_pcm_stream(self, media_path: str | Path, sample_rate: int = 44100, channels: int = 2) -> bytes:
        chunk = self.ffmpeg.extract_audio_pcm(media_path, sample_rate=sample_rate, channels=channels)
        return chunk.raw_pcm if chunk else b""

    def transcode_video(
        self,
        input_path: str | Path,
        output_path: str | Path,
        video_codec: str = "libx264",
        crf: int = 21,
        *,
        width: int | None = None,
        height: int | None = None,
        preset: str = "veryfast",
        start_time_secs: float | None = None,
        duration_secs: float | None = None,
        prefer_hardware: bool = False,
        progress_callback: Callable[[float], None] | None = None,
    ) -> bool:
        return self.ffmpeg.transcode_video(
            input_path=input_path,
            output_path=output_path,
            video_codec=video_codec,
            crf=crf,
            width=width,
            height=height,
            preset=preset,
            start_time_secs=start_time_secs,
            duration_secs=duration_secs,
            prefer_hardware=prefer_hardware,
            progress_callback=progress_callback,
        )

    def extract_still(
        self,
        file_path: str | Path,
        output_path: str | Path,
        *,
        timestamp_secs: float = 1.0,
        max_width: int | None = 160,
    ) -> bool:
        return self.ffmpeg.extract_still(
            file_path,
            output_path,
            timestamp_secs=timestamp_secs,
            max_width=max_width,
        )


_rust_core: RustCoreAdapter | None = None


def get_rust_core() -> RustCoreAdapter:
    global _rust_core
    if _rust_core is None:
        _rust_core = RustCoreAdapter()
    return _rust_core

