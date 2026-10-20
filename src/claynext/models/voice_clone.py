"""
Voice Clone & Tone-Matching Engine for Claynext Studio.

Extracts character voice samples directly from movie audio, detects fundamental pitch (F0),
computes tone / timbre profiles, and enables zero-shot reference voice cloning or
tone-matched neural speech synthesis across all pipeline jobs.
"""
from __future__ import annotations

import math
import os
import re
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from claynext.adapters.ffmpeg_adapter import run_ffmpeg
from claynext.utils.config import CACHE_DIR


CLONE_DIR = CACHE_DIR / "voice_clones"
CLONE_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", str(text or "")).strip().lower()
    return re.sub(r"[-\s]+", "_", cleaned) or "voice"


def read_audio_pcm(wav_path: str) -> Tuple[np.ndarray, int]:
    """Read a WAV file into a normalized 1D float32 numpy array and sample rate."""
    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        dtype = np.int16
        scale = 32768.0
    elif sampwidth == 1:
        dtype = np.uint8
        scale = 128.0
    elif sampwidth == 4:
        dtype = np.int32
        scale = 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")

    data = np.frombuffer(raw, dtype=dtype).astype(np.float32) / scale
    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1)

    return data, framerate


def analyze_voice_tone(
    audio_path: str,
    start_sec: float = 0.0,
    duration_sec: float = 0.0,
) -> Dict[str, Any]:
    """
    Analyze fundamental frequency (F0), pitch offset, and timbre from an audio sample.

    Uses normalized autocorrelation pitch detection across voiced 30ms frames.
    """
    if not os.path.isfile(audio_path):
        return {
            "median_f0": 160.0,
            "gender": "Unknown",
            "pitch_offset_hz": 0.0,
            "spectral_centroid": 2000.0,
            "timbre": "Standard",
        }

    # If start_sec / duration_sec are given, extract slice to a temporary memory or temp file
    temp_wav: Optional[str] = None
    read_path = audio_path
    if start_sec > 0 or duration_sec > 0:
        temp_wav = str(CLONE_DIR / f"temp_probe_{os.getpid()}_{int(start_sec * 1000)}.wav")
        dur_arg = ["-t", f"{duration_sec:.3f}"] if duration_sec > 0 else []
        ok = run_ffmpeg([
            "-y", "-ss", f"{start_sec:.3f}",
            "-i", audio_path,
            *dur_arg,
            "-vn", "-ac", "1", "-ar", "16000",
            temp_wav,
        ])
        if ok and os.path.isfile(temp_wav):
            read_path = temp_wav

    try:
        samples, sr = read_audio_pcm(read_path)
    except Exception:
        return {
            "median_f0": 160.0,
            "gender": "Unknown",
            "pitch_offset_hz": 0.0,
            "spectral_centroid": 2000.0,
            "timbre": "Standard",
        }
    finally:
        if temp_wav and os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass

    if len(samples) < int(sr * 0.1):  # Less than 100ms
        return {
            "median_f0": 160.0,
            "gender": "Unknown",
            "pitch_offset_hz": 0.0,
            "spectral_centroid": 2000.0,
            "timbre": "Standard",
        }

    # 1. Autocorrelation Pitch Detection
    frame_len = int(sr * 0.030)  # 30 ms
    hop_len = int(sr * 0.015)    # 15 ms
    min_lag = int(sr / 400.0)    # 400 Hz upper bound
    max_lag = int(sr / 65.0)     # 65 Hz lower bound

    pitches: List[float] = []
    centroids: List[float] = []

    for i in range(0, len(samples) - frame_len, hop_len):
        frame = samples[i : i + frame_len]
        energy = np.sqrt(np.mean(frame ** 2))
        if energy < 0.015:  # Silence / noise gate
            continue

        windowed = frame * np.hanning(frame_len)
        corr = np.correlate(windowed, windowed, mode="full")
        corr = corr[len(corr) // 2 :]

        if len(corr) > max_lag:
            peak_sub = corr[min_lag:max_lag]
            if len(peak_sub) > 0 and corr[0] > 0:
                peak_idx = min_lag + int(np.argmax(peak_sub))
                norm_peak = corr[peak_idx] / corr[0]
                if norm_peak > 0.35:  # Voiced threshold
                    freq = sr / peak_idx
                    if 65.0 <= freq <= 400.0:
                        pitches.append(freq)

        # Spectral Centroid (Timbre Brightness)
        mag = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(frame_len, d=1.0 / sr)
        mag_sum = np.sum(mag)
        if mag_sum > 1e-4:
            centroids.append(float(np.sum(freqs * mag) / mag_sum))

    if pitches:
        median_f0 = float(np.median(pitches))
    else:
        median_f0 = 160.0

    if centroids:
        median_centroid = float(np.median(centroids))
    else:
        median_centroid = 2000.0

    # Gender determination based on acoustic pitch profile:
    # Male voices typically center around 85–150 Hz; Female around 170–260 Hz.
    if median_f0 < 165.0:
        gender = "Male"
        base_std = 125.0  # Standard male neural voice baseline
    else:
        gender = "Female"
        base_std = 210.0  # Standard female neural voice baseline

    # Pitch offset in Hz (relative to standard base neural voice)
    pitch_offset = float(round(median_f0 - base_std, 1))
    # Clamp pitch offset to reasonable bounds for TTS synthesizers (-45Hz to +45Hz)
    pitch_offset = max(-45.0, min(45.0, pitch_offset))

    # Characterize Timbre
    if median_centroid < 1600:
        timbre = "Deep / Resonant Warm"
    elif median_centroid > 2600:
        timbre = "Bright / Crisp High"
    else:
        timbre = "Balanced Cinematic"

    return {
        "median_f0": round(median_f0, 1),
        "gender": gender,
        "pitch_offset_hz": pitch_offset,
        "spectral_centroid": round(median_centroid, 1),
        "timbre": timbre,
    }


def extract_character_voice_reference(
    media_path: str,
    segments: List[Dict[str, Any]],
    speaker: str,
    *,
    out_dir: Optional[Path] = None,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Find the cleanest speech turn for `speaker` in `segments` and extract a 24kHz reference WAV.
    """
    if not media_path or not os.path.isfile(media_path):
        return None

    # Filter segments for this speaker
    spk_segs = [
        s for s in segments
        if str(s.get("speaker") or "").strip().lower() == speaker.strip().lower()
    ]
    if not spk_segs:
        return None

    # Pick the best segment: preferred duration between 2.5s and 7.0s
    from claynext.models.dubbing_service import timestamp_to_sec

    best_seg = None
    best_score = -1.0
    for s in spk_segs:
        start = float(s.get("start_sec") or timestamp_to_sec(s.get("start", "")))
        end = float(s.get("end_sec") or timestamp_to_sec(s.get("end", "")))
        dur = max(0.0, end - start)
        if dur <= 0.8:
            continue
        text_len = len(str(s.get("original_text") or s.get("text") or ""))
        # Score favors segments between 2.5s and 6.0s with substantial spoken text
        score = min(dur, 6.0) * 1.5 + min(text_len, 30)
        if score > best_score:
            best_score = score
            best_seg = (start, dur)

    if not best_seg:
        # Fall back to the very first segment
        start = float(spk_segs[0].get("start_sec") or timestamp_to_sec(spk_segs[0].get("start", "")))
        end = float(spk_segs[0].get("end_sec") or timestamp_to_sec(spk_segs[0].get("end", "")))
        best_seg = (start, max(1.5, end - start))

    start_sec, dur_sec = best_seg
    dur_sec = min(8.0, max(1.8, dur_sec))

    dest_dir = out_dir or CLONE_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify(speaker)
    out_wav = str(dest_dir / f"ref_{slug}.wav")

    # Extract audio with vocal isolation filtering: highpass 80Hz, lowpass 7500Hz, normalization
    ok = run_ffmpeg([
        "-y",
        "-ss", f"{start_sec:.3f}",
        "-t", f"{dur_sec:.3f}",
        "-i", str(media_path),
        "-vn",
        "-af", "highpass=f=80,lowpass=f=7500,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ac", "1",
        "-ar", "24000",
        out_wav,
    ])

    if not ok or not os.path.isfile(out_wav) or os.path.getsize(out_wav) < 500:
        return None

    # Analyze tone profile of the extracted clip
    tone = analyze_voice_tone(out_wav)
    tone["reference_wav"] = out_wav
    tone["speaker"] = speaker
    return out_wav, tone


def clone_character_voices_from_movie(
    media_path: str,
    segments: List[Dict[str, Any]],
    *,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Extract reference voice clips and analyze tones for all characters in the script.
    Attaches clone metadata and pitch offsets directly to each segment.
    """
    if not segments:
        return {}

    speakers = []
    for s in segments:
        spk = str(s.get("speaker") or "").strip()
        if spk and spk not in speakers:
            speakers.append(spk)

    if not speakers:
        speakers = ["Character 1"]

    profiles: Dict[str, Dict[str, Any]] = {}
    total = len(speakers)

    for i, spk in enumerate(speakers):
        if progress_callback:
            progress_callback(
                int((i / max(1, total)) * 90),
                f"Extracting voice clone sample for '{spk}' ({i + 1}/{total})…",
            )

        res = extract_character_voice_reference(media_path, segments, spk)
        if res:
            ref_wav, tone = res
            profiles[spk] = tone
        else:
            # Fallback default tone
            profiles[spk] = {
                "median_f0": 130.0,
                "gender": "Male",
                "pitch_offset_hz": 0.0,
                "spectral_centroid": 2000.0,
                "timbre": "Standard",
                "reference_wav": "",
                "speaker": spk,
            }

    # Apply clone voice configuration across all segments
    for s in segments:
        spk = str(s.get("speaker") or "").strip() or "Character 1"
        profile = profiles.get(spk)
        if not profile:
            continue

        s["reference_wav"] = profile.get("reference_wav") or ""
        s["pitch_offset"] = profile.get("pitch_offset_hz") or 0.0
        s["clone_voice"] = profile

        # Set clone voice id while retaining base neural gender matching
        gender = profile.get("gender") or "Unknown"
        if not s.get("gender_manual"):
            s["gender"] = gender

        # Assign clone voice tag
        s["tts_voice_hint"] = f"clone:{spk}"
        s["voice_id"] = f"clone:{spk}"

    if progress_callback:
        progress_callback(100, f"Cloned {len(profiles)} character voice(s) successfully!")

    return profiles


def match_timbre_eq(input_wav: str, ref_wav: str, output_wav: str) -> str:
    """
    Apply acoustic timbre matching EQ to shaped speech audio based on reference voice.
    """
    if not os.path.isfile(input_wav) or not os.path.isfile(ref_wav):
        return input_wav

    try:
        ref_tone = analyze_voice_tone(ref_wav)
        centroid = float(ref_tone.get("spectral_centroid") or 2000.0)

        # Equalizer shaping based on actor's spectral brightness
        if centroid < 1600:
            # Deep/warm resonance: boost low frequencies, gentle roll-off at extreme highs
            eq_filter = "equalizer=f=220:width_type=o:w=1.2:g=2.5,equalizer=f=3200:width_type=o:w=1.0:g=-1.0"
        elif centroid > 2600:
            # Bright/crisp: gentle high presence boost
            eq_filter = "equalizer=f=4000:width_type=o:w=1.0:g=2.0,equalizer=f=180:width_type=o:w=1.0:g=-1.5"
        else:
            # Balanced cinematic warmth
            eq_filter = "equalizer=f=280:width_type=o:w=1.0:g=1.0,equalizer=f=3500:width_type=o:w=1.0:g=1.0"

        temp_eq = str(Path(output_wav).with_name(f"temp_eq_{os.getpid()}.wav"))
        ok = run_ffmpeg([
            "-y", "-i", input_wav,
            "-af", eq_filter,
            temp_eq,
        ])
        if ok and os.path.isfile(temp_eq):
            import shutil
            shutil.move(temp_eq, output_wav)
            return output_wav
    except Exception:
        pass

    return input_wav
