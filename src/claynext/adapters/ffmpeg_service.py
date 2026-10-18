"""FFmpeg helpers for dubbing: probe, demux, time-stretch, timeline mix, mux."""
from __future__ import annotations

import os
import re
import subprocess
import threading
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def run_ffmpeg(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", *args],
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _progress_seconds(line: str) -> float | None:
    text = (line or "").strip()
    if text.startswith("out_time_us=") or text.startswith("out_time_ms="):
        raw = text.split("=", 1)[1].strip()
        try:
            return int(raw) / 1_000_000.0
        except ValueError:
            return None
    if text.startswith("out_time="):
        clock = text.split("=", 1)[1].strip()
        parts = clock.split(":")
        if len(parts) != 3:
            return None
        try:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except ValueError:
            return None
    return None


def run_ffmpeg_progress(
    args: list[str],
    *,
    duration_sec: float = 0.0,
    on_fraction=None,
    timeout: int = 3600,
) -> subprocess.CompletedProcess:
    """Run ffmpeg and report encode fraction 0..1 from the `-progress` protocol."""
    cmd = [
        ffmpeg_exe(), "-hide_banner", "-nostdin", "-nostats",
        "-loglevel", "error", "-stats_period", "0.016", "-progress", "pipe:1", *args,
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    err_parts: list[str] = []

    def _drain() -> None:
        if proc.stderr is not None:
            err_parts.append(proc.stderr.read())

    thread = threading.Thread(target=_drain, daemon=True)
    thread.start()
    last = -1.0
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                seconds = _progress_seconds(line)
                if seconds is None or not on_fraction or duration_sec <= 0:
                    continue
                frac = min(0.99, seconds / duration_sec)
                if last >= 0.0 and abs(frac - last) < 0.0004:
                    continue
                last = frac
                on_fraction(frac)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
    finally:
        thread.join(timeout=2)
    code = proc.returncode if proc.returncode is not None else 1
    return subprocess.CompletedProcess(cmd, code, "", "".join(err_parts))


WAVE_RATE = 200  # envelope peaks per second of audio
_WAVE_SAMPLES = 20  # decoded samples per peak (decode rate = WAVE_RATE * _WAVE_SAMPLES)


def extract_wave_envelope(path: str, normalize: bool = True, progress_callback=None):
    """Peak envelope at WAVE_RATE values per second (float32 0..1), streamed so long films stay light.

    normalize=True scales to the loudest passage and lifts quiet speech for display;
    False keeps absolute levels (used to detect silent takes).
    """
    import numpy as np

    if not path or not os.path.isfile(path):
        return np.zeros(0, dtype=np.float32)
    proc = subprocess.Popen(
        [
            ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin",
            "-i", path, "-vn", "-ac", "1", "-ar", str(WAVE_RATE * _WAVE_SAMPLES),
            "-f", "s16le", "-acodec", "pcm_s16le", "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    frame = _WAVE_SAMPLES * 2
    chunk = frame * WAVE_RATE * 10
    parts: list = []
    tail = b""
    try:
        while True:
            data = proc.stdout.read(chunk)
            if not data:
                break
            buf = tail + data
            usable = len(buf) - len(buf) % frame
            tail = buf[usable:]
            if usable:
                block = np.frombuffer(buf[:usable], dtype="<i2").reshape(-1, _WAVE_SAMPLES)
                parts.append(np.abs(block.astype(np.int32)).max(axis=1))
        if len(tail) >= 2:
            last = np.frombuffer(tail[: len(tail) - len(tail) % 2], dtype="<i2")
            parts.append(np.array([np.abs(last.astype(np.int32)).max()]))
    finally:
        proc.stdout.close()
        proc.wait(timeout=30)
    if not parts:
        return np.zeros(0, dtype=np.float32)
    env = np.concatenate(parts).astype(np.float32) / 32768.0
    return normalize_envelope(env) if normalize else env


def normalize_envelope(env):
    """Scale to the loud end (99.5th percentile) and lift quiet passages so speech stays readable."""
    import numpy as np

    if env is None or not len(env):
        return np.zeros(0, dtype=np.float32)
    top = float(np.percentile(env, 99.5)) or float(env.max()) or 1.0
    return np.clip(env / top, 0.0, 1.0).astype(np.float32) ** 0.7


def probe_duration(path: str) -> float:
    """Duration in seconds — prefers Rust claynext-ffmpeg via FFmpegAdapter."""
    if not path or not os.path.isfile(path):
        return 0.0
    try:
        from claynext.adapters.ffmpeg_adapter import get_ffmpeg_adapter

        dur = float(get_ffmpeg_adapter().duration(path) or 0.0)
        if dur > 0:
            return dur
    except Exception:
        pass
    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", path],
        capture_output=True,
        timeout=30,
        check=False,
        text=True,
        errors="replace",
    )
    text = (proc.stderr or "") + (proc.stdout or "")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        return 0.0
    h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
    return h * 3600 + m * 60 + s


def demux_wav(media_path: str, wav_path: str, *, rate: int = 48000, channels: int = 2) -> str:
    """Extract PCM WAV — prefers Rust claynext-ffmpeg demux-audio."""
    Path(wav_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        from claynext.adapters.ffmpeg_adapter import get_ffmpeg_adapter

        if get_ffmpeg_adapter().demux_audio(
            media_path, wav_path, sample_rate=rate, channels=channels
        ):
            return wav_path
    except Exception:
        pass
    proc = run_ffmpeg([
        "-y", "-i", media_path,
        "-vn", "-ac", str(channels), "-ar", str(rate),
        "-c:a", "pcm_s16le",
        wav_path,
    ])
    if proc.returncode != 0 or not os.path.isfile(wav_path) or os.path.getsize(wav_path) == 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or "Could not extract audio.")
    return wav_path


def extract_audio(
    media_path: str,
    out_path: str,
    *,
    rate: int = 48000,
    channels: int = 2,
    bitrate: str = "192k",
) -> str:
    """Split / demux the audio stream from a video (or media) file.

    Format is inferred from ``out_path`` suffix: ``.wav``, ``.mp3``, ``.m4a``/``.aac``.
    """
    src = Path(media_path)
    dst = Path(out_path)
    if not src.is_file():
        raise FileNotFoundError(f"Media not found: {media_path}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    ext = dst.suffix.lower()
    if ext == ".wav":
        return demux_wav(str(src), str(dst), rate=rate, channels=channels)
    if ext == ".mp3":
        codec = ["-c:a", "libmp3lame", "-b:a", bitrate]
    elif ext in {".m4a", ".aac", ".mp4"}:
        # Audio-only m4a/aac container
        if ext == ".mp4":
            dst = dst.with_suffix(".m4a")
        codec = ["-c:a", "aac", "-b:a", bitrate]
    else:
        # Default to WAV when suffix is unknown
        dst = dst.with_suffix(".wav")
        return demux_wav(str(src), str(dst), rate=rate, channels=channels)

    proc = run_ffmpeg([
        "-y", "-i", str(src),
        "-vn", "-ac", str(channels), "-ar", str(rate),
        *codec,
        str(dst),
    ])
    if proc.returncode != 0 or not dst.is_file() or dst.stat().st_size == 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or "Could not extract audio from video.")
    return str(dst)


def make_silence(wav_path: str, duration: float, *, rate: int = 44100) -> str:
    dur = max(0.05, float(duration))
    proc = run_ffmpeg([
        "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r={rate}:cl=stereo:d={dur:.3f}",
        "-c:a", "pcm_s16le",
        wav_path,
    ])
    if proc.returncode != 0 or not os.path.isfile(wav_path):
        raise RuntimeError("Could not create silent timeline.")
    return wav_path


def volume_wav(src: str, dst: str, volume: float) -> str:
    vol = max(0.0, min(2.0, float(volume)))
    proc = run_ffmpeg(["-y", "-i", src, "-filter:a", f"volume={vol}", "-c:a", "pcm_s16le", dst])
    if proc.returncode != 0 or not os.path.isfile(dst):
        raise RuntimeError("Could not scale background audio.")
    return dst


def fit_duration(
    src: str,
    dst: str,
    target_sec: float,
    *,
    min_tempo: float = 0.65,
    max_tempo: float = 1.85,
    pad_or_trim: bool = True,
) -> str:
    current = probe_duration(src)
    target = max(0.10, float(target_sec))
    if current <= 0:
        raise RuntimeError("Could not read TTS clip duration.")
    ratio = current / target

    if 0.96 <= ratio <= 1.04:
        # Pacing already matches character slot; add soft fade guard if trimming
        args = ["-y", "-i", src]
        if pad_or_trim:
            fade_st = max(0.0, target - 0.06)
            args += [
                "-filter:a", f"afade=t=out:st={fade_st:.3f}:d=0.06",
                "-ar", "48000", "-ac", "2",
                "-c:a", "pcm_s16le",
                "-t", f"{target:.3f}",
                dst,
            ]
        else:
            args += ["-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", dst]
        proc = run_ffmpeg(args)
    else:
        # Tempo clamp via DubbingAdapter → Rust align-speed; Python fallback.
        try:
            from claynext.adapters.dubbing import get_dubbing_adapter

            tempo = get_dubbing_adapter().align_speech_speed(
                current, target, min_speed=min_tempo, max_speed=max_tempo
            )
        except Exception:
            tempo = max(min_tempo, min(max_tempo, ratio))
        # Build atempo filter chain (atempo filter accepts values in [0.5, 2.0])
        if tempo > 2.0:
            filters = [f"atempo=2.0", f"atempo={tempo / 2.0:.4f}"]
        elif tempo < 0.5:
            filters = [f"atempo=0.5", f"atempo={tempo / 0.5:.4f}"]
        else:
            filters = [f"atempo={tempo:.4f}"]

        args = ["-y", "-i", src]
        if pad_or_trim:
            fade_st = max(0.0, target - 0.06)
            filters.append(f"afade=t=out:st={fade_st:.3f}:d=0.06")
            args += [
                "-filter:a", ",".join(filters),
                "-ar", "48000", "-ac", "2",
                "-c:a", "pcm_s16le",
                "-t", f"{target:.3f}",
                dst,
            ]
        else:
            args += ["-filter:a", ",".join(filters), "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", dst]
        proc = run_ffmpeg(args)

    if proc.returncode != 0 or not os.path.isfile(dst) or os.path.getsize(dst) == 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or "Time-stretch failed.")
    return dst


def mix_wavs(inputs: list[str], dst: str, *, weights: list[float] | None = None) -> str:
    if not inputs:
        raise RuntimeError("No stems to mix.")
    if len(inputs) == 1:
        proc = run_ffmpeg(["-y", "-i", inputs[0], "-c:a", "pcm_s16le", dst])
    else:
        args: list[str] = ["-y"]
        for path in inputs:
            args += ["-i", path]
        n = len(inputs)
        labels = "".join(f"[{i}:a]" for i in range(n))
        w = weights or [1.0] * n
        wtxt = " ".join(f"{x:.3f}" for x in w)
        filt = f"{labels}amix=inputs={n}:duration=longest:dropout_transition=0:normalize=0:weights={wtxt}[a]"
        args += ["-filter_complex", filt, "-map", "[a]", "-c:a", "pcm_s16le", dst]
        proc = run_ffmpeg(args)
    if proc.returncode != 0 or not os.path.isfile(dst):
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or "Stem mix failed.")
    return dst


def dynamic_duck_audio(
    source_wav: str,
    intervals: list[tuple[float, float]],
    dst_wav: str,
    *,
    duck_vol: float = 0.22,
    fade_in_sec: float = 0.15,
    fade_out_sec: float = 0.20,
    fade_ms: float | None = None,
    pre_roll_sec: float = 0.15,
    post_roll_sec: float = 0.20,
    center_attenuation: float = 0.65,
) -> str:
    """
    Intelligently duck movie background audio ONLY during active dialogue segments.
    Non-dialogue intervals (sound effects, action sequences, music, character screams)
    remain at 100% full original cinema volume.
    During dialogue, smoothly ducks to duck_vol, with center-channel vocal reduction
    to prevent original language bleed-through while keeping stereo sound effects & music audible.
    """
    import wave
    import numpy as np

    if fade_ms is not None:
        sec = max(0.01, float(fade_ms) / 1000.0)
        fade_in_sec = sec
        fade_out_sec = sec

    if not intervals:
        import shutil
        shutil.copyfile(source_wav, dst_wav)
        return dst_wav

    with wave.open(source_wav, "rb") as wf:
        rate = wf.getframerate()
        n_ch = wf.getnchannels()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    samples = np.frombuffer(raw, dtype=np.int16).reshape(-1, n_ch).astype(np.float32)
    total_frames = len(samples)
    gain = np.ones(total_frames, dtype=np.float32)

    # Merge nearby intervals (< 0.35s gap) to prevent rapid volume flutter
    merged: list[list[float]] = []
    for s, e in sorted(intervals, key=lambda x: x[0]):
        s_pad = max(0.0, s - pre_roll_sec)
        e_pad = min(total_frames / rate, e + post_roll_sec)
        if not merged:
            merged.append([s_pad, e_pad])
        else:
            if s_pad - merged[-1][1] <= 0.35:
                merged[-1][1] = max(merged[-1][1], e_pad)
            else:
                merged.append([s_pad, e_pad])

    fade_in_len = max(1, int(fade_in_sec * rate))
    fade_out_len = max(1, int(fade_out_sec * rate))
    target_vol = max(0.05, min(0.60, float(duck_vol)))

    for s, e in merged:
        i_s = int(s * rate)
        i_e = min(total_frames, int(e * rate))
        if i_e <= i_s:
            continue

        # Smooth cosine fade-in into ducking
        i_fade_in_end = min(i_e, i_s + fade_in_len)
        if i_fade_in_end > i_s:
            t = np.linspace(0.0, 1.0, i_fade_in_end - i_s)
            duck_curve = 1.0 - (1.0 - target_vol) * (0.5 - 0.5 * np.cos(np.pi * t))
            gain[i_s:i_fade_in_end] = np.minimum(gain[i_s:i_fade_in_end], duck_curve)

        # Sustained ducking level
        i_fade_out_start = max(i_s, i_e - fade_out_len)
        if i_fade_out_start > i_fade_in_end:
            gain[i_fade_in_end:i_fade_out_start] = np.minimum(gain[i_fade_in_end:i_fade_out_start], target_vol)

        # Smooth cosine fade-out back to 100% full cinema volume
        if i_e > i_fade_out_start:
            t = np.linspace(1.0, 0.0, i_e - i_fade_out_start)
            rise_curve = 1.0 - (1.0 - target_vol) * (0.5 - 0.5 * np.cos(np.pi * t))
            gain[i_fade_out_start:i_e] = np.minimum(gain[i_fade_out_start:i_e], rise_curve)

    # Center-channel dialogue attenuation for stereo tracks
    if n_ch == 2:
        L = samples[:, 0]
        R = samples[:, 1]
        M = 0.5 * (L + R)
        S = 0.5 * (L - R)
        duck_mask = (1.0 - gain)
        center_factor = gain * (1.0 - duck_mask * center_attenuation)
        side_factor = np.clip(gain * (1.0 + duck_mask * 0.25), 0.0, 1.0)
        out_L = center_factor * M + side_factor * S
        out_R = center_factor * M - side_factor * S
        out_samples = np.stack([out_L, out_R], axis=1)
    else:
        out_samples = samples * gain[:, np.newaxis]

    out_int16 = np.clip(out_samples, -32768, 32767).astype(np.int16)
    with wave.open(dst_wav, "wb") as out_wf:
        out_wf.setnchannels(n_ch)
        out_wf.setsampwidth(2)
        out_wf.setframerate(rate)
        out_wf.writeframes(out_int16.tobytes())
    return dst_wav


def master_voiceover_track(
    dialogue_wav: str,
    dst_wav: str,
    *,
    volume_boost: float = 1.25,
) -> str:
    """
    Studio voiceover mastering chain:
    - 80Hz high-pass filter (removes muddy mic rumbles)
    - 3kHz presence EQ (enhances speech clarity and articulation)
    - Dynamic compression/limiting (consistent voiceover level)
    - 11kHz high shelf tame (smooths sibilance)
    """
    filt = (
        "highpass=f=80,"
        "equalizer=f=3000:t=q:w=1.4:g=2.5,"
        "acompressor=threshold=-18dB:ratio=3.0:attack=15:release=120:makeup=2.2dB,"
        f"volume={volume_boost:.2f}"
    )
    proc = run_ffmpeg([
        "-y",
        "-i", dialogue_wav,
        "-af", filt,
        "-ar", "48000",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        dst_wav,
    ])
    if proc.returncode != 0 or not os.path.isfile(dst_wav):
        return dialogue_wav
    return dst_wav


def overlay_clips(
    clips: list[tuple[str, int]],
    duration: float,
    dst: str,
    *,
    batch_size: int = 12,
    work_dir: str | None = None,
) -> str:
    """Place WAV clips on a timeline. Uses fast direct PCM composition, falling back to FFmpeg."""
    if not clips:
        return make_silence(dst, duration)

    # Fast direct PCM timeline composition
    try:
        import wave
        import numpy as np

        rate = 48000
        channels = 2
        total_frames = int(np.ceil(max(0.1, duration) * rate))
        buf = np.zeros((total_frames, channels), dtype=np.int32)

        for path, delay_ms in clips:
            if not os.path.isfile(path):
                continue
            with wave.open(path, "rb") as wf:
                n_ch = wf.getnchannels()
                n_frames = wf.getnframes()
                raw = wf.readframes(n_frames)
            if not raw:
                continue
            samples = np.frombuffer(raw, dtype=np.int16).reshape(-1, n_ch)
            if n_ch == 1 and channels == 2:
                samples = np.repeat(samples, 2, axis=1)
            elif n_ch > channels:
                samples = samples[:, :channels]

            start_f = int(delay_ms * rate / 1000)
            if start_f >= total_frames:
                continue
            end_f = min(total_frames, start_f + len(samples))
            buf[start_f:end_f] += samples[:end_f - start_f]

        clipped = np.clip(buf, -32768, 32767).astype(np.int16)
        with wave.open(dst, "wb") as out_wf:
            out_wf.setnchannels(channels)
            out_wf.setsampwidth(2)
            out_wf.setframerate(rate)
            out_wf.writeframes(clipped.tobytes())
        return dst
    except Exception:
        pass

    # Fallback to FFmpeg adelay + amix batched
    root = Path(work_dir or Path(dst).parent)
    silence = str(root / "_silence.wav")
    make_silence(silence, duration)
    batches: list[str] = []
    for b, start in enumerate(range(0, len(clips), batch_size)):
        chunk = clips[start:start + batch_size]
        out = str(root / f"_dlg_batch_{b:03d}.wav")
        args = ["-y", "-i", silence]
        filters: list[str] = []
        mix_in = ["[0:a]"]
        for i, (path, delay_ms) in enumerate(chunk, start=1):
            args += ["-i", path]
            ms = max(0, int(delay_ms))
            filters.append(f"[{i}:a]adelay={ms}|{ms}[d{i}]")
            mix_in.append(f"[d{i}]")
        n = len(mix_in)
        filters.append(
            f"{''.join(mix_in)}amix=inputs={n}:duration=first:dropout_transition=0:normalize=0[a]"
        )
        args += ["-filter_complex", ";".join(filters), "-map", "[a]", "-c:a", "pcm_s16le", out]
        proc = run_ffmpeg(args, timeout=900)
        if proc.returncode != 0 or not os.path.isfile(out):
            err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(err or "Dialogue overlay failed.")
        batches.append(out)
    if len(batches) == 1:
        Path(batches[0]).replace(dst)
        return dst
    return mix_wavs(batches, dst)


def probe_size(path: str) -> tuple[int, int]:
    info = probe_media(path)
    return int(info.get("width") or 1920), int(info.get("height") or 1080)


def _gcd(a: int, b: int) -> int:
    a, b = abs(int(a)), abs(int(b))
    while b:
        a, b = b, a % b
    return a or 1


def aspect_label(width: int, height: int, dar: str = "") -> str:
    if dar and re.match(r"^\d+:\d+$", dar):
        return dar
    w, h = max(1, int(width)), max(1, int(height))
    ratio = w / h
    for aw, ah in ((16, 9), (9, 16), (4, 3), (3, 4), (1, 1), (21, 9), (4, 5), (2, 3), (3, 2)):
        if abs(ratio - aw / ah) < 0.03:
            return f"{aw}:{ah}"
    g = _gcd(w, h)
    return f"{w // g}:{h // g}"


def probe_media(path: str) -> dict:
    """Parse media metadata using the native Rust core probe when available, with regex fallback."""
    if not path or not os.path.isfile(path):
        return {}

    try:
        from claynext.adapters.ffmpeg_adapter import get_ffmpeg_adapter
        meta = get_ffmpeg_adapter().probe(path)
        if meta and (meta.video_stream or meta.audio_stream):
            w = meta.video_stream.width if meta.video_stream else 0
            h = meta.video_stream.height if meta.video_stream else 0
            info: dict = {
                "path": os.path.abspath(path),
                "name": os.path.basename(path),
                "ext": os.path.splitext(path)[1].lstrip(".").upper() or "—",
                "bytes": meta.file_size_bytes or (os.path.getsize(path) if os.path.isfile(path) else 0),
                "container": meta.format_name,
                "duration": meta.duration,
                "bitrate_kbps": int(meta.bit_rate // 1000) if meta.bit_rate else 0,
            }
            if meta.video_stream:
                info["vcodec"] = meta.video_stream.codec
                info["width"] = w
                info["height"] = h
                info["aspect"] = aspect_label(w, h)
                info["fps"] = meta.video_stream.frame_rate
                info["pix_fmt"] = meta.video_stream.pixel_format
            if meta.audio_stream:
                info["acodec"] = meta.audio_stream.codec
                info["sample_rate"] = meta.audio_stream.sample_rate
                info["channels"] = str(meta.audio_stream.channels)
                info["audio_kbps"] = int(meta.audio_stream.bit_rate // 1000) if meta.audio_stream.bit_rate else 0
            return info
    except Exception:
        pass

    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", path],
        capture_output=True,
        timeout=30,
        check=False,
        text=True,
        errors="replace",
    )
    text = (proc.stderr or "") + (proc.stdout or "")
    info = {
        "path": os.path.abspath(path),
        "name": os.path.basename(path),
        "ext": os.path.splitext(path)[1].lstrip(".").upper() or "—",
        "bytes": os.path.getsize(path),
    }
    container = re.search(r"Input #\d+,\s*([^,]+)", text)
    if container:
        info["container"] = container.group(1).split(",")[0].strip()
    dur = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if dur:
        h, m, s = int(dur.group(1)), int(dur.group(2)), float(dur.group(3))
        info["duration"] = h * 3600 + m * 60 + s
    br = re.search(r"bitrate:\s*(\d+)\s*kb/s", text)
    if br:
        info["bitrate_kbps"] = int(br.group(1))
    video = re.search(
        r"Video:\s*([^,\s(]+)[^,\n]*,.*?(\d{2,5})x(\d{2,5})(?:.*?DAR\s+(\d+:\d+))?",
        text,
        re.IGNORECASE,
    )
    if video:
        info["vcodec"] = video.group(1)
        info["width"] = int(video.group(2))
        info["height"] = int(video.group(3))
        if video.group(4):
            info["dar"] = video.group(4)
        info["aspect"] = aspect_label(info["width"], info["height"], info.get("dar", ""))
    fps = re.search(r"(\d+(?:\.\d+)?)\s*fps", text)
    if fps:
        info["fps"] = float(fps.group(1))
    pix = re.search(r"Video:.*?,\s*([a-z0-9]+)\s*\(", text, re.IGNORECASE)
    if pix:
        info["pix_fmt"] = pix.group(1)
    audio = re.search(
        r"Audio:\s*([^,\s(]+)[^,\n]*,\s*(\d+)\s*Hz,\s*([^,]+)",
        text,
        re.IGNORECASE,
    )
    if audio:
        info["acodec"] = audio.group(1)
        info["sample_rate"] = int(audio.group(2))
        info["channels"] = audio.group(3).strip()
    abr = re.search(r"Audio:.*?(\d+)\s*kb/s", text, re.IGNORECASE)
    if abr:
        info["audio_kbps"] = int(abr.group(1))
    if "width" not in info:
        wh = re.search(r"(\d{2,5})x(\d{2,5})", text)
        if wh:
            info["width"] = int(wh.group(1))
            info["height"] = int(wh.group(2))
            info["aspect"] = aspect_label(info["width"], info["height"])
    return info


def _ts_to_sec(ts: str) -> float:
    try:
        raw = (ts or "").strip().replace(",", ".")
        parts = raw.split(":")
        if len(parts) != 3:
            return 0.0
        h, m = int(parts[0]), int(parts[1])
        return h * 3600 + m * 60 + float(parts[2])
    except Exception:
        return 0.0


def _filter_path(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:").replace("'", r"\'")


def _write_overlay_ass(
    overlays: list[dict],
    segments: list[dict] | None,
    work_dir: str,
    width: int,
    height: int,
) -> str | None:
    from claynext.models.text_style import ASS_STYLES, ass_events, shape_events

    events: list[str] = []
    for item in overlays or []:
        kind = str(item.get("kind") or "text")
        if kind in {"logo", "image"}:
            continue
        clip_start = float(item.get("start_ms") or 0) / 1000.0
        clip_end = float(item.get("end_ms") or 0) / 1000.0 or 36000.0
        if kind == "shape":
            events += shape_events(item, clip_start, clip_end, width, height)
            continue
        live = bool(item.get("live")) and kind == "caption"
        if live and item.get("cues"):
            for cue in item["cues"]:
                fitted = dict(
                    item,
                    box_w=cue.get("box_w") or 0,
                    box_h=cue.get("box_h") or 0,
                    font=cue.get("font") or item.get("font"),
                    metrics=cue.get("metrics") or item.get("metrics"),
                    font_size=cue.get("font_size", item.get("font_size")),
                )
                start, end = float(cue["start_ms"]) / 1000.0, float(cue["end_ms"]) / 1000.0
                events += ass_events(fitted, str(cue.get("text") or ""), start, end, width, height)
            continue
        if live and segments:
            for seg in segments:
                text = str(seg.get("translated_text") or seg.get("text") or "").strip()
                if not text:
                    continue
                start = float(seg.get("start_sec") or 0)
                end = float(seg.get("end_sec") or 0)
                if not start and seg.get("start"):
                    start = _ts_to_sec(str(seg.get("start") or ""))
                if not end and seg.get("end"):
                    end = _ts_to_sec(str(seg.get("end") or ""))
                if end <= start:
                    end = start + 1.5
                start, end = max(start, clip_start), min(end, clip_end)
                if end > start:
                    events += ass_events(dict(item, box_w=0, box_h=0), text, start, end, width, height)
            continue
        events += ass_events(item, str(item.get("text") or ""), clip_start, clip_end, width, height)
    if not events:
        return None
    path = str(Path(work_dir) / "overlays.ass")
    body = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 1\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        + ASS_STYLES + "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        + "\n".join(events)
        + "\n"
    )
    Path(path).write_text(body, encoding="utf-8")
    return path


def compose_overlays(
    video_path: str,
    overlays: list[dict],
    output_path: str,
    *,
    segments: list[dict] | None = None,
    work_dir: str | None = None,
    progress_callback=None,
) -> str:
    """Burn logo / image / text / caption overlays onto a muxed video."""
    rows = list(overlays or [])
    if not rows:
        return video_path
    root = Path(work_dir or Path(output_path).parent)
    root.mkdir(parents=True, exist_ok=True)
    width, height = probe_size(video_path)
    images = [
        it for it in rows
        if str(it.get("kind") or "") in {"logo", "image"} and os.path.isfile(str(it.get("path") or ""))
    ]
    ass_path = _write_overlay_ass(rows, segments, str(root), width, height)
    if not images and not ass_path:
        return video_path
    args: list[str] = ["-y", "-i", video_path]
    for item in images:
        args += ["-i", str(item["path"])]
    filters: list[str] = []
    last = "0:v"
    for i, item in enumerate(images, start=1):
        w = max(16, int(width * float(item.get("w") or 0.14)))
        h = max(16, int(height * float(item.get("h") or 0.14)))
        op = max(0.08, min(1.0, float(item.get("opacity") or 100) / 100.0))
        rot = float(item.get("rotation") or 0.0)
        lab = f"im{i}"
        chain = f"[{i}:v]format=rgba,scale={w}:{h}"
        if abs(rot) > 0.4:
            rad = rot * 3.14159265 / 180.0
            chain += f",rotate={rad}:c=none:ow=rotw(iw):oh=roth(ih)"
        chain += f",colorchannelmixer=aa={op:.3f}[{lab}]"
        filters.append(chain)
        x_expr = f"(main_w*{float(item.get('x') or 0.5):.4f})-(overlay_w/2)"
        y_expr = f"(main_h*{float(item.get('y') or 0.5):.4f})-(overlay_h/2)"
        nxt = f"ov{i}"
        filters.append(f"[{last}][{lab}]overlay=x={x_expr}:y={y_expr}:format=auto[{nxt}]")
        last = nxt
    if ass_path:
        filters.append(f"[{last}]ass='{_filter_path(ass_path)}'[vout]")
        vmap = "[vout]"
    elif last == "0:v":
        vmap = "0:v"
    else:
        vmap = f"[{last}]"
    if filters:
        args += ["-filter_complex", ";".join(filters), "-map", vmap]
    else:
        args += ["-map", "0:v"]
    args += [
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-shortest",
        output_path,
    ]
    duration = probe_duration(video_path)

    def _on_fraction(frac: float) -> None:
        if progress_callback:
            progress_callback(frac * 100.0, "Rendering on-screen text…")

    proc = run_ffmpeg_progress(args, duration_sec=duration, on_fraction=_on_fraction, timeout=1200)
    if proc.returncode != 0 or not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        err = str(proc.stderr or "").strip()
        raise RuntimeError(err or "Overlay compose failed.")
    return output_path


def concat_videos(paths: list[str], output_path: str, progress_callback=None) -> str:
    """Join episode files in order. Stream-copy first, then re-encode if the cuts do not match."""
    sources = [path for path in paths if path and os.path.isfile(path)]
    if len(sources) < 2:
        raise RuntimeError("Choose at least two episodes to merge.")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    list_path = Path(output_path).with_suffix(".concat.txt")
    lines = []
    for path in sources:
        escaped = os.path.abspath(path).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        copied = run_ffmpeg([
            "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-c", "copy", "-movflags", "+faststart", output_path,
        ], timeout=1800)
        if copied.returncode == 0 and os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        encoded = run_ffmpeg([
            "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            output_path,
        ], timeout=3600)
        if encoded.returncode != 0 or not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
            err = (encoded.stderr or copied.stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(err or "Could not merge the episodes.")
        return output_path
    finally:
        list_path.unlink(missing_ok=True)


def ensure_speech_bed(media_path: str, progress_callback=None, *, use_demucs: bool = True) -> str:
    """Cache a speech-free music/effects bed for mix (Demucs when installed, else FFmpeg)."""
    import hashlib
    from claynext.utils.paths import CACHE_DIR

    if not media_path or not os.path.isfile(media_path):
        return ""

    # Prefer Demucs / Demucs-MLX when studio settings allow and a backend is installed.
    if use_demucs:
        try:
            from claynext.models.features import prefer_demucs_bed
            from claynext.models.stem_separation import ensure_demucs_speech_bed

            if prefer_demucs_bed():
                bed, _vocals = ensure_demucs_speech_bed(media_path, progress_callback=progress_callback)
                if bed and os.path.isfile(bed):
                    return bed
        except Exception:
            pass

    stat = os.stat(media_path)
    key = hashlib.sha1(f"{os.path.abspath(media_path)}|{stat.st_size}|{int(stat.st_mtime)}|ffmpeg-v1".encode()).hexdigest()[:16]
    out_dir = Path(CACHE_DIR) / "speech_bed"
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{key}.wav"
    if dst.is_file() and dst.stat().st_size > 0:
        return str(dst)
    if progress_callback:
        progress_callback(20, "Building FFmpeg mid-side music bed…")
    # Mid-side + low/air residual: approximate speech removal without Demucs.
    graph = (
        "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=3[a][b][c];"
        "[a]pan=stereo|c0=0.5*c0-0.5*c1|c1=0.5*c1-0.5*c0[side];"
        "[b]pan=mono|c0=0.5*c0+0.5*c1,lowpass=f=170,pan=stereo|c0=c0|c1=c0[low];"
        "[c]pan=mono|c0=0.5*c0+0.5*c1,highpass=f=7500,volume=0.55,pan=stereo|c0=c0|c1=c0[air];"
        "[side][low][air]amix=inputs=3:normalize=0,volume=1.35[bed]"
    )
    tmp = dst.with_suffix(".part.wav")
    proc = run_ffmpeg([
        "-y", "-i", media_path, "-vn", "-filter_complex", graph,
        "-map", "[bed]", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(tmp),
    ], timeout=900)
    if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        return ""
    tmp.replace(dst)
    return str(dst)


def _read_wav48(path: str, root: Path, tag: str):
    import wave
    import numpy as np

    rate, channels = 48000, 2
    wav_path = path
    try:
        with wave.open(path, "rb") as wf:
            ok = wf.getframerate() == rate and wf.getsampwidth() == 2 and wf.getnchannels() in {1, 2}
    except Exception:
        ok = False
    if not ok:
        wav_path = str(root / f"{tag}.wav")
        demux_wav(path, wav_path, rate=rate, channels=channels)
    with wave.open(wav_path, "rb") as wf:
        n_ch = wf.getnchannels()
        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).reshape(-1, n_ch)
    if n_ch == 1:
        data = np.repeat(data, 2, axis=1)
    return data[:, :channels].astype(np.float32)


def _envelope(keys: list[tuple[int, float]], total: int, fallback: float):
    import numpy as np

    if not keys:
        return np.full(total, float(fallback), dtype=np.float32)
    rows = sorted((int(ms), float(gain)) for ms, gain in keys)
    times = np.array([ms * 48.0 for ms, _ in rows], dtype=np.float64)
    gains = np.array([gain for _, gain in rows], dtype=np.float32)
    return np.interp(np.arange(total, dtype=np.float64), times, gains).astype(np.float32)


def mix_timeline_audio(
    video_path: str,
    dst_wav: str,
    voice_clips: list[dict],
    footage_keys: list[tuple[int, float]],
    *,
    footage_gain: float = 1.0,
    bed_path: str = "",
    bed_keys: list[tuple[int, float]] | None = None,
    include_footage: bool = True,
    work_dir: str | None = None,
    progress_callback=None,
) -> str:
    """Footage audio follows its key points; the speech-free bed fills in where speech is ducked."""
    import wave
    import numpy as np

    def ping(pct: float, msg: str):
        if progress_callback:
            progress_callback(float(pct), msg)

    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError("The source footage is missing.")
    root = Path(work_dir or Path(dst_wav).parent / ".render")
    root.mkdir(parents=True, exist_ok=True)

    ping(5, "Reading footage audio…")
    source = _read_wav48(video_path, root, "footage")
    total = len(source)
    if include_footage:
        ping(25, "Applying footage key points…")
        mix = source * _envelope(footage_keys, total, footage_gain)[:, np.newaxis]
        if bed_path and os.path.isfile(bed_path) and bed_keys:
            ping(35, "Keeping music and sound effects under the voice-over…")
            bed = _read_wav48(bed_path, root, "bed")
            if len(bed) < total:
                bed = np.pad(bed, ((0, total - len(bed)), (0, 0)))
            mix += bed[:total] * _envelope(bed_keys, total, 0.0)[:, np.newaxis]
    else:
        mix = np.zeros_like(source)
    del source

    ping(50, f"Placing {len(voice_clips)} voice clips…")
    for index, clip in enumerate(voice_clips):
        path = str(clip.get("path") or "")
        gain = float(clip.get("gain", 1.0))
        if not os.path.isfile(path) or gain <= 0.0:
            continue
        samples = _read_wav48(path, root, f"clip_{index:04d}")
        samples = samples[int(int(clip.get("in_ms") or 0) * 48):]
        if clip.get("duration_ms"):
            samples = samples[: int(int(clip["duration_ms"]) * 48)]
        start = int(int(clip.get("start_ms") or 0) * 48)
        if start >= total or len(samples) == 0:
            continue
        end = min(total, start + len(samples))
        piece = samples[: end - start] * gain
        fade_in = min(len(piece), int(int(clip.get("fade_in_ms") or 0) * 48))
        fade_out = min(len(piece), int(int(clip.get("fade_out_ms") or 0) * 48))
        if fade_in:
            piece[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)[:, np.newaxis]
        if fade_out:
            piece[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)[:, np.newaxis]
        mix[start:end] += piece

    Path(dst_wav).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(dst_wav, "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(48000)
        out.writeframes(np.clip(mix, -32768, 32767).astype(np.int16).tobytes())
    return dst_wav


def render_timeline(
    video_path: str,
    output_path: str,
    voice_clips: list[dict],
    footage_keys: list[tuple[int, float]],
    *,
    footage_gain: float = 1.0,
    bed_path: str = "",
    bed_keys: list[tuple[int, float]] | None = None,
    overlays: list[dict] | None = None,
    segments: list[dict] | None = None,
    audio_bitrate: str = "256k",
    reencode: bool = False,
    video_filter: str = "",
    work_dir: str | None = None,
    progress_callback=None,
) -> str:
    """Mix the timeline audio, then mux it under the movie picture."""
    def ping(pct: float, msg: str):
        if progress_callback:
            progress_callback(float(pct), msg)

    root = Path(work_dir or Path(output_path).parent / ".render")
    root.mkdir(parents=True, exist_ok=True)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    mix_path = mix_timeline_audio(
        video_path, str(root / "timeline_mix.wav"), voice_clips, footage_keys,
        footage_gain=footage_gain, bed_path=bed_path, bed_keys=bed_keys,
        work_dir=str(root), progress_callback=lambda p, m: ping(float(p) * 0.55, m),
    )

    def _map_encode(pct: float, msg: str, lo: float, hi: float) -> None:
        span = max(0.0, min(100.0, float(pct)))
        ping(lo + (hi - lo) * span / 100.0, msg)

    if overlays:
        muxed = str(root / "timeline_mux.mp4")
        mux_video(
            video_path, mix_path, muxed, audio_bitrate=audio_bitrate, video_filter=video_filter,
            progress_callback=lambda pct, msg: _map_encode(pct, msg, 55, 86),
        )
        compose_overlays(
            muxed, overlays, output_path, segments=segments, work_dir=str(root),
            progress_callback=lambda pct, msg: _map_encode(pct, msg, 86, 99),
        )
    else:
        mux_video(
            video_path, mix_path, output_path,
            audio_bitrate=audio_bitrate, reencode=reencode, video_filter=video_filter,
            progress_callback=lambda pct, msg: _map_encode(pct, msg, 55, 99),
        )
    ping(100, "Export complete")
    return output_path


def mux_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    *,
    audio_bitrate: str = "256k",
    reencode: bool = False,
    video_filter: str = "",
    progress_callback=None,
) -> str:
    reencode = reencode or bool(video_filter)
    label = "Encoding video…" if reencode else "Muxing video…"

    def _ping(pct: float, msg: str = "") -> None:
        if progress_callback:
            progress_callback(max(0.0, min(100.0, float(pct))), msg or label)

    try:
        from claynext.adapters.rust_bridge.ffmpeg import RustFfmpegAdapter
        from claynext.adapters.rust_bridge.process import _find_binary

        if _find_binary("claynext-ffmpeg"):
            RustFfmpegAdapter.mux_with_progress(
                video_path, audio_path, output_path,
                reencode=reencode, audio_bitrate=audio_bitrate, video_filter=video_filter,
                progress_callback=_ping,
            )
            _ping(100, "Export complete")
            return output_path
    except FileNotFoundError:
        pass
    except Exception as exc:
        if _find_binary("claynext-ffmpeg"):
            raise
        _ = exc

    video_codec = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"] if reencode else ["-c:v", "copy"]
    vf = ["-vf", video_filter] if video_filter else []
    duration = probe_duration(video_path)

    def _on_fraction(frac: float) -> None:
        _ping(frac * 100.0, label)

    proc = run_ffmpeg_progress([
        "-y", "-i", video_path, "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        *vf, *video_codec, "-c:a", "aac", "-b:a", audio_bitrate,
        "-shortest", "-movflags", "+faststart",
        output_path,
    ], duration_sec=duration, on_fraction=_on_fraction, timeout=3600 if reencode else 900)
    if proc.returncode != 0 or not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        err = (proc.stderr or "").strip()
        raise RuntimeError(err or "Failed to mux dubbed video.")
    _ping(100, "Export complete")
    return output_path


def encode_source_movie(src: str, dest: str, progress_callback=None) -> str:
    """Re-encode a source movie through claynext-ffmpeg, reporting encode percent."""
    from claynext.adapters.rust_bridge.ffmpeg import RustFfmpegAdapter

    def _on_frac(pct: float) -> None:
        if progress_callback:
            done = float(pct) >= 100
            progress_callback(float(pct), "Export complete" if done else "Encoding video…")

    ok = RustFfmpegAdapter.transcode_video(
        src, dest,
        video_codec="libx264",
        crf=18,
        preset="medium",
        audio_codec="aac",
        sample_rate=44100,
        channels=2,
        audio_bitrate_kbps=256,
        progress_callback=_on_frac,
    )
    if not ok or not os.path.isfile(dest) or os.path.getsize(dest) == 0:
        raise RuntimeError("Encode failed.")
    if progress_callback:
        progress_callback(100, "Export complete")
    return dest
