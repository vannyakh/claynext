"""
AI movie dubbing pipeline:

  video → audio demux → ASR segments → batched translation
       → Khmer/Edge TTS → time-stretch → FFmpeg timeline mix → mux

Demucs stem separation is optional (demucs-mlx on Apple Silicon, or demucs).
Otherwise original audio is ducked as the BGM/Foley bed.
"""
from __future__ import annotations

import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict

from claynext.models.asr_service import ASREngine, merge_dialogue_segments
from claynext.adapters.ffmpeg_service import (
    clean_source_audio,
    demux_wav,
    dynamic_duck_audio,
    ensure_speech_bed,
    fit_duration,
    make_silence,
    master_voiceover_track,
    mix_wavs,
    compose_overlays,
    mux_video,
    overlay_clips,
    probe_duration,
    volume_wav,
)
from claynext.models.dubbing_plan import (
    build_dubbing_plan,
    hf_token as resolve_hf_token,
    plan_to_segments,
    save_plan,
    whisperx_available,
)
from claynext.models.translate_service import TranslateEngine
from claynext.models.tts_service import TTSEngine
from claynext.utils.config import OUTPUTS_DIR, STUDIO_CACHE

VOICE_PAIRS = {
    "km-KH-SreymomNeural": "km-KH-PisethNeural",
    "km-KH-PisethNeural": "km-KH-SreymomNeural",
    "vi-VN-HoaiMyNeural": "vi-VN-NamMinhNeural",
    "vi-VN-NamMinhNeural": "vi-VN-HoaiMyNeural",
    "en-US-AvaNeural": "en-US-AndrewNeural",
    "en-US-AndrewNeural": "en-US-AvaNeural",
    "kitten-Bella": "kitten-Jasper",
    "kitten-Jasper": "kitten-Bella",
    "kitten-Luna": "kitten-Bruno",
    "kitten-Bruno": "kitten-Luna",
    "kitten-Rosie": "kitten-Hugo",
    "kitten-Hugo": "kitten-Rosie",
    "kitten-Kiki": "kitten-Leo",
    "kitten-Leo": "kitten-Kiki",
    "voxcpm-khmer-female": "voxcpm-khmer-male",
    "voxcpm-khmer-male": "voxcpm-khmer-female",
    "voxcpm-en-female": "voxcpm-en-male",
    "voxcpm-en-male": "voxcpm-en-female",
    "voxcpm-vi-female": "voxcpm-vi-male",
    "voxcpm-vi-male": "voxcpm-vi-female",
    "omnivoice-khmer-female": "omnivoice-khmer-male",
    "omnivoice-khmer-male": "omnivoice-khmer-female",
    "omnivoice-en-female": "omnivoice-en-male",
    "omnivoice-en-male": "omnivoice-en-female",
    "omnivoice-vi-female": "omnivoice-vi-male",
    "omnivoice-vi-male": "omnivoice-vi-female",
}


def timestamp_to_sec(ts: str) -> float:
    try:
        raw = (ts or "").strip().replace(",", ".")
        parts = raw.split(":")
        if len(parts) != 3:
            return 0.0
        h, m = int(parts[0]), int(parts[1])
        return h * 3600 + m * 60 + float(parts[2])
    except Exception:
        return 0.0


def _job_dir(video_path: str, target_lang: str, voice_id: str) -> Path:
    key = hashlib.sha1(f"{os.path.abspath(video_path)}|{target_lang}|{voice_id}".encode()).hexdigest()[:16]
    path = STUDIO_CACHE / key
    path.mkdir(parents=True, exist_ok=True)
    return path


def _voice_for_speaker(base_voice: str, speaker: str, seen: dict[str, str]) -> str:
    name = (speaker or "").strip() or "default"
    if name in seen:
        return seen[name]
    if not seen:
        seen[name] = base_voice
        return base_voice
    alt = VOICE_PAIRS.get(base_voice, base_voice)
    used = set(seen.values())
    seen[name] = alt if alt not in used else base_voice
    return seen[name]


def analyze_movie_characters(
    segments: list[dict],
    primary_voice: str = "km-KH-SreymomNeural",
    secondary_voice: str = "km-KH-PisethNeural",
    target_lang: str = "",
    *,
    audio_path: str = "",
    work_dir: str | Path | None = None,
    progress_callback: Callable | None = None,
) -> list[dict]:
    """
    Analyze dialogue turns, pauses, and character transitions.
    Assigns character labels, gender (audio model + text), duration quotas,
    and gender-matched neural voices per character.
    """
    from claynext.models.gender_audio import enrich_segments_with_audio_gender
    from claynext.models.gender_voices import apply_character_cast, assign_gender_and_voices

    if not segments:
        return []

    # Check if segments already have speaker attribution (e.g. from WhisperX or Gemini)
    existing_speakers = [
        str(s.get("speaker") or "").strip()
        for s in segments
        if str(s.get("speaker") or "").strip() and str(s.get("speaker") or "").strip() not in {"UNKNOWN_SPEAKER", "Unknown", ""}
    ]
    has_diarization = len(existing_speakers) >= max(1, len(segments) // 3)

    if has_diarization:
        seen_speakers: dict[str, str] = {}
        for s in segments:
            spk = str(s.get("speaker") or "").strip() or "Speaker 1"
            if spk not in seen_speakers:
                seen_speakers[spk] = f"Character {len(seen_speakers) + 1}"

        for s in segments:
            spk = str(s.get("speaker") or "").strip() or "Speaker 1"
            s.setdefault("speaker_id", spk)
            s.setdefault("speaker_source", "diarization")
            s["speaker"] = seen_speakers[spk]
            start_sec = timestamp_to_sec(s.get("start", ""))
            end_sec = timestamp_to_sec(s.get("end", ""))
            dur = max(0.15, end_sec - start_sec)
            s["start_sec"] = start_sec
            s["end_sec"] = end_sec
            s["duration_sec"] = round(dur, 3)
            s["recommended_syllables"] = TranslateEngine.estimate_speech_quota(
                dur, target_lang or "Khmer"
            )
            s["speed_tolerance"] = {"min_rate": 0.65, "max_rate": 1.85}
    else:
        # No diarization: conversational pause and turn analysis
        current_char_idx = 1
        prev_end = 0.0

        for i, s in enumerate(segments):
            start_sec = timestamp_to_sec(s.get("start", ""))
            end_sec = timestamp_to_sec(s.get("end", ""))
            dur = max(0.15, end_sec - start_sec)

            gap = start_sec - prev_end if i > 0 else 0.0
            prev_text = str(segments[i - 1].get("text", "")).strip() if i > 0 else ""
            prev_intent = ""
            if prev_text:
                from claynext.models.gender_voices import detect_line_intent

                prev_intent = detect_line_intent(prev_text)
            turn = prev_intent in {"question", "command", "plea"}

            if i > 0 and (gap >= 0.85 or (gap >= 0.28 and turn)):
                current_char_idx = 2 if current_char_idx == 1 else 1

            s["speaker"] = f"Character {current_char_idx}"
            s.setdefault("speaker_id", f"TURN_{current_char_idx}")
            s.setdefault("speaker_source", "turn_heuristic")
            s["start_sec"] = start_sec
            s["end_sec"] = end_sec
            s["duration_sec"] = round(dur, 3)
            s["recommended_syllables"] = TranslateEngine.estimate_speech_quota(
                dur, target_lang or "Khmer"
            )
            s["speed_tolerance"] = {"min_rate": 0.65, "max_rate": 1.85}
            prev_end = end_sec

    # ASR audio gender: wav2vec2 Common-Voice classifier per character.
    gender_on = True
    try:
        from claynext.controllers.store import get_store

        gender_on = get_store().get_setting("dub", "gender_detect", "1") == "1"
    except Exception:
        gender_on = True
    if gender_on and audio_path and os.path.isfile(audio_path):
        if progress_callback:
            progress_callback(36, "Audio gender detection (Common-Voice)…")
        enrich_segments_with_audio_gender(
            segments,
            audio_path,
            work_dir=Path(work_dir) / "gender" if work_dir else None,
            progress_callback=progress_callback,
        )

    # Fast path: skip LLM cast naming when gender assist is off.
    if gender_on:
        if progress_callback:
            progress_callback(37, "AI naming characters & voice profiling…")
        try:
            from claynext.models.gender_voices import llm_analyze_cast_and_gender

            llm_analyze_cast_and_gender(segments, progress_callback=progress_callback)
        except Exception:
            pass
    elif progress_callback:
        progress_callback(37, "Fast cast · lead & co-star only…")
    apply_character_cast(segments)
    try:
        from claynext.models.jev_decisions import refine_cast

        refine_cast(segments, progress_callback=progress_callback)
    except Exception:
        pass

    return assign_gender_and_voices(
        segments,
        primary_voice=primary_voice,
        secondary_voice=secondary_voice or primary_voice,
        lang=target_lang,
        force_redetect=True,
    )


def _try_demucs(wav_path: str, out_dir: Path, ping: Callable) -> dict[str, str]:
    """Isolate vocals, music, and effects when a stem model is available."""
    empty = {"bed": "", "vocals": "", "effects": "", "music": ""}
    try:
        from claynext.models.features import demucs_model_name, prefer_demucs_bed
        from claynext.models.stem_separation import separate_movie_stems

        if not prefer_demucs_bed():
            return empty
        result = separate_movie_stems(
            wav_path,
            out_dir=out_dir / "stems",
            model=demucs_model_name(),
            progress_callback=ping,
        )
        return {
            "bed": str(result.get("bed") or ""),
            "vocals": str(result.get("vocals") or ""),
            "effects": str(result.get("effects") or ""),
            "music": str(result.get("music") or ""),
        }
    except Exception:
        return empty


def _soundtrack_turns(path: str) -> list[dict]:
    """Speech turns on the soundtrack. Empty when the core tool is unavailable."""
    if not path or not os.path.isfile(path):
        return []
    try:
        from claynext.adapters.ai import get_ai_adapter

        turns = []
        for item in get_ai_adapter().vad_chunk(path, threshold=0.22) or []:
            start = float(item.get("start_sec") or 0)
            end = float(item.get("end_sec") or 0)
            if end - start >= 0.18:
                turns.append({
                    "start_sec": start,
                    "end_sec": end,
                    "confidence": float(item.get("confidence") or 0.85),
                })
        return turns
    except Exception:
        return []


def _speech_clip_pairs(path: str, duration: float) -> list[float] | None:
    """One Whisper window per soundtrack speech turn.

    A pause stays a pause, so a quiet reply is its own window instead of being
    skipped inside a long clip. A turn longer than half a minute is sliced.
    """
    if duration <= 20 or not path or not os.path.isfile(path):
        return None
    spans = [
        (float(item["start_sec"]), float(item["end_sec"]))
        for item in _soundtrack_turns(path)
    ]
    if len(spans) < 2:
        return None
    pairs: list[float] = []
    for start, end in spans:
        cursor = max(0.0, start)
        limit = min(duration, end)
        while cursor < limit - 0.12:
            nxt = min(limit, cursor + 32.0)
            if nxt - cursor >= 0.28:
                pairs.extend([round(cursor, 3), round(nxt, 3)])
            if nxt >= limit - 0.05:
                break
            cursor = nxt
    return pairs if len(pairs) >= 4 else None


def _fit_lines_fallback(lines: list[dict], turns: list[dict]) -> list[dict]:
    """Same snap as the Rust fitter, used when that binary is not built yet."""
    if not lines or not turns:
        return lines

    def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
        return max(0.0, min(a1, b1) - max(a0, b0))

    owners: list[int | None] = []
    for line in lines:
        best_i = None
        best = 0.0
        for i, turn in enumerate(turns):
            score = _overlap(line["start_sec"], line["end_sec"], turn["start_sec"], turn["end_sec"])
            if score > best:
                best = score
                best_i = i
        owners.append(best_i if best > 0.04 else None)
    groups: dict[int, list[int]] = {}
    for index, owner in enumerate(owners):
        if owner is not None:
            groups.setdefault(owner, []).append(index)
    out = [dict(line) for line in lines]
    for turn_i, members in groups.items():
        turn = turns[turn_i]
        if len(members) == 1:
            line = out[members[0]]
            line["start_sec"] = max(turn["start_sec"], line["start_sec"] - 0.45)
            line["start_sec"] = min(line["start_sec"], lines[members[0]]["start_sec"])
            line["end_sec"] = min(turn["end_sec"], line["end_sec"] + 0.45)
            line["end_sec"] = max(line["end_sec"], lines[members[0]]["end_sec"])
            continue
        members = sorted(members, key=lambda i: lines[i]["start_sec"])
        weights = [max(0.2, lines[i]["end_sec"] - lines[i]["start_sec"]) for i in members]
        total = sum(weights) or 0.2
        cursor = float(turn["start_sec"])
        span = max(0.12 * len(members), float(turn["end_sec"]) - cursor)
        for n, index in enumerate(members):
            if n + 1 == len(members):
                end = float(turn["end_sec"])
            else:
                end = min(
                    float(turn["end_sec"]) - 0.12 * (len(members) - n - 1),
                    cursor + max(0.12, span * weights[n] / total),
                )
            out[index]["start_sec"] = cursor
            out[index]["end_sec"] = max(cursor + 0.12, end)
            cursor = out[index]["end_sec"]
    return out


def _fit_segments_to_soundtrack(segments: list[dict], path: str) -> list[dict]:
    """Move each transcript line onto the speech it belongs to on the track."""
    turns = _soundtrack_turns(path)
    if not turns or not segments:
        return segments
    lines = []
    for seg in segments:
        start = float(seg.get("start_sec") or timestamp_to_sec(seg.get("start", "")))
        end = float(seg.get("end_sec") or timestamp_to_sec(seg.get("end", "")))
        if end <= start:
            end = start + 0.4
        lines.append({
            "start_sec": start,
            "end_sec": end,
            "text": str(seg.get("text") or ""),
        })
    fitted = None
    try:
        from claynext.adapters.ai import get_ai_adapter

        fitted = get_ai_adapter().fit_speech(lines, turns)
    except Exception:
        fitted = None
    if not fitted or len(fitted) != len(segments):
        fitted = _fit_lines_fallback(lines, turns)
    from claynext.models.asr_service import _fmt_ts

    for seg, line in zip(segments, fitted):
        start = max(0.0, float(line.get("start_sec") or 0))
        end = max(start + 0.12, float(line.get("end_sec") or start))
        seg["start"] = _fmt_ts(start)
        seg["end"] = _fmt_ts(end)
        seg["start_sec"] = round(start, 3)
        seg["end_sec"] = round(end, 3)
        seg["duration_sec"] = round(end - start, 3)
    return segments


def _speech_device() -> str:
    try:
        from claynext.adapters.resources import resource_plan

        return "cuda" if resource_plan().get("speech_device") == "cuda" else "cpu"
    except Exception:
        return "cpu"


def _tts_workers(requested: int | None) -> int:
    if requested is not None and int(requested) > 0:
        return max(1, int(requested))
    try:
        from claynext.adapters.resources import resource_plan

        return max(1, int(resource_plan().get("tts_workers") or 1))
    except Exception:
        return 1


def _speak_lines(
    translated: list[dict],
    *,
    job: Path,
    voice_id: str,
    sync_mode: str,
    render: bool,
    vocal_master: bool,
    voiceover_boost: float,
    workers: int,
    control,
    share: Callable,
    ping: Callable,
) -> list[tuple[str, int]]:
    """Speak every line. Several lines run at once when the machine has the cores."""
    pending = [
        (idx, item)
        for idx, item in enumerate(translated)
        if str(item.get("translated_text") or item.get("text") or "").strip()
    ]
    total = max(1, len(pending))
    placed: list[tuple[str, int]] = []
    lock = threading.Lock()
    done = 0

    def _one(idx: int, item: dict) -> None:
        if control is not None:
            control.checkpoint()
        voice = item.get("tts_voice_hint") or voice_id
        text_to_speak = str(item.get("translated_text") or item.get("text") or "")
        performance = item.get("performance") if isinstance(item.get("performance"), dict) else None
        if performance is None:
            from claynext.models.gender_voices import expression_tag
            from claynext.models.tts_expression import has_expression_tags

            expr = str(item.get("expression") or "")
            if not expr:
                from claynext.models.gender_voices import delivery_for_intent, detect_line_intent

                expr = delivery_for_intent(item.get("intent") or detect_line_intent(text_to_speak))
            tag = expression_tag(expr)
            if tag and text_to_speak and not has_expression_tags(text_to_speak):
                text_to_speak = f"{tag} {text_to_speak}"
        raw_mp3 = str(job / f"seg_{idx + 1:04d}.mp3")
        start = float(item.get("start_sec") or timestamp_to_sec(item.get("start", "")))
        end = float(item.get("end_sec") or timestamp_to_sec(item.get("end", "")))
        slot = max(0.15, end - start) if end > start else 2.0
        fitted = str(job / f"seg_{idx + 1:04d}_fit.wav")

        spoken = False
        clean_text = text_to_speak.strip()
        ref_wav = str(item.get("reference_wav") or "")
        pitch_val = float(item.get("pitch_offset") or 0.0)
        if not ref_wav and item.get("clone_voice"):
            ref_wav = str(item["clone_voice"].get("reference_wav") or "")
            if not pitch_val:
                pitch_val = float(item["clone_voice"].get("pitch_offset_hz") or 0.0)

        if clean_text:
            fallback_voice = voice_id if voice_id and not str(voice_id).startswith("clone:") else ""
            if not fallback_voice:
                gender = str(item.get("gender") or "").lower()
                fallback_voice = (
                    "km-KH-SreymomNeural" if gender.startswith("f") else "km-KH-PisethNeural"
                )
            attempts = [(voice, ref_wav, pitch_val), (fallback_voice, "", 0.0)]
            for attempt, (try_voice, try_ref, try_pitch) in enumerate(attempts):
                if control is not None:
                    control.checkpoint()
                if not try_voice:
                    continue
                try:
                    TTSEngine.synthesize(
                        clean_text, try_voice, raw_mp3,
                        pitch=try_pitch, reference_wav=try_ref,
                        control=control,
                        performance=performance,
                    )
                    spoken = os.path.isfile(raw_mp3) and os.path.getsize(raw_mp3) > 100
                    if spoken:
                        voice = try_voice
                        break
                except Exception:
                    if attempt == 0:
                        import time
                        time.sleep(0.2)

        if spoken:
            try:
                from claynext.adapters.ffmpeg_service import apply_speech_eq

                eq_wav = str(job / f"seg_{idx + 1:04d}_eq.wav")
                eq_path = apply_speech_eq(raw_mp3, eq_wav)
                if eq_path and os.path.isfile(eq_path):
                    raw_mp3 = eq_path
            except Exception:
                pass
            if sync_mode == "natural":
                min_t, max_t = 0.95, 1.60
            elif sync_mode == "subtle":
                min_t, max_t = 0.85, 2.00
            else:
                min_t, max_t = 0.65, 2.80
            intent = str(item.get("intent") or "")
            if intent == "narration":
                min_t, max_t = max(min_t, 0.90), min(max_t, 1.22)
            elif intent == "command":
                min_t, max_t = max(min_t, 0.95), min(max_t, 1.40)
            elif intent in {"plea", "aside"}:
                min_t, max_t = min_t, min(max_t, 1.25)
            if performance is not None:
                from claynext.models.character_intel import tempo_window

                min_t, max_t = tempo_window(item, min_t, max_t)
            try:
                fit_duration(raw_mp3, fitted, slot, min_tempo=min_t, max_tempo=max_t, pad_or_trim=False, never_trim=True)
            except Exception:
                make_silence(fitted, slot)
        else:
            make_silence(fitted, slot)

        if not render and vocal_master and os.path.isfile(fitted):
            try:
                fitted = master_voiceover_track(
                    fitted, str(job / f"seg_{idx + 1:04d}_master.wav"), volume_boost=voiceover_boost,
                )
            except Exception:
                pass
        item["audio_path"] = fitted
        item["start_ms"] = int(start * 1000)
        item["voice_id"] = voice
        actual_slot = probe_duration(fitted) if os.path.isfile(fitted) else slot
        item["duration"] = f"{actual_slot:.1f}s"
        item["duration_sec"] = round(actual_slot, 2)
        with lock:
            placed.append((fitted, int(start * 1000)))
        share("clip", {"index": idx, "segment": dict(item)})

    if workers <= 1 or len(pending) <= 1:
        for n, (idx, item) in enumerate(pending):
            speaker = item.get("speaker") or f"Line {idx + 1}"
            ping(58 + int((n / total) * 24), f"TTS {n + 1}/{total} ({speaker})…")
            _one(idx, item)
            ping(58 + int(((n + 1) / total) * 24), f"Dubbed {n + 1}/{total} ({speaker})")
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_one, idx, item) for idx, item in pending]
            try:
                for fut in as_completed(futures):
                    fut.result()
                    done += 1
                    ping(58 + int((done / total) * 24), f"Dubbed {done}/{total}")
            except Exception:
                if control is not None:
                    control.cancel()
                raise
    placed.sort(key=lambda row: row[1])
    return placed


class DubbingEngine:
    @staticmethod
    def process_dubbing(
        video_path: str,
        target_lang: str = "Khmer",
        voice_id: str = "km-KH-SreymomNeural",
        secondary_voice_id: str = "km-KH-PisethNeural",
        source_lang: str = "Chinese",
        background_vol: float = 0.15,
        output_path: str | None = None,
        asr_model: str = "whisper-small",
        asr_language: str = "Chinese",
        gemini_key: str = "",
        hf_token: str = "",
        translator: str = "auto",
        ollama_model: str = "",
        overlays: list[dict] | None = None,
        progress_callback: Callable = None,
        vocal_master: bool = True,
        center_attenuation: float = 0.70,
        voiceover_boost: float = 1.15,
        fade_ms: int = 150,
        sync_mode: str = "stretch",
        auto_chain: bool = True,
        render: bool = True,
        control=None,
        live: Callable | None = None,
        translate_fit_duration: bool = True,
        translate_slang: bool = True,
        translate_expression: bool = True,
        tts_workers: int | None = None,
    ) -> Dict[str, Any]:
        if not video_path or not os.path.isfile(video_path):
            raise FileNotFoundError("Select a video file first.")

        stem = Path(video_path).stem
        lang_slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in target_lang).strip("-")
        if output_path is None:
            output_path = str(OUTPUTS_DIR / f"{stem}_dub_{lang_slug}.mp4")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        job = _job_dir(video_path, target_lang, voice_id)

        def ping(pct: int, msg: str):
            if control is not None:
                control.checkpoint()
            if progress_callback:
                progress_callback(pct, msg)

        def share(kind: str, payload):
            if live is not None:
                try:
                    live(kind, payload)
                except Exception:
                    pass

        ping(2, "Extracting audio from the source track…")
        full_wav = str(job / "source_48k.wav")
        demux_wav(video_path, full_wav, rate=48000, channels=2)
        ping(4, "Cleaning source audio…")
        clean_wav = str(job / "source_clean.wav")
        clean_audio = clean_source_audio(full_wav, clean_wav)
        ping(7, "Probing media duration…")
        duration = probe_duration(video_path) or probe_duration(full_wav)
        if duration <= 0:
            raise RuntimeError("Could not read media duration.")

        # Fast path: skip Demucs when Auto-mix / isolate bed is off (big latency win).
        want_stems = True
        try:
            from claynext.controllers.store import get_store

            want_stems = get_store().get_setting("dub", "auto_mix", "1") == "1"
        except Exception:
            want_stems = True
        bgm_separated, vocals_path = None, None
        effects_path, music_path = "", ""
        if want_stems:
            ping(9, "Isolating vocals, music, and effects…")
            stems = _try_demucs(
                full_wav,
                job,
                lambda p, m: ping(9 + int(max(0, min(100, int(p))) * 0.06), m),
            )
            bgm_separated = stems.get("bed") or None
            vocals_path = stems.get("vocals") or None
            effects_path = stems.get("effects") or ""
            music_path = stems.get("music") or ""
            ping(15, "Vocal stem ready…" if vocals_path else "Using full mix for ASR…")
        else:
            ping(9, "Fast path · skipping stem separation…")
            ping(15, "Using full mix for ASR…")
        asr_source = vocals_path or clean_audio or full_wav

        # Step 1: Speech Recognition. OCR captions are optional and off by default.
        token = resolve_hf_token(hf_token)
        segments: list[dict] = []
        effective_lang = source_lang if source_lang and source_lang != "Auto Detect" else asr_language
        used_ocr = False
        try:
            from claynext.models.features import transcript_ocr_enabled

            if transcript_ocr_enabled():
                from claynext.models.ocr_service import try_ocr_transcript

                ping(16, "Checking burned-in captions…")
                ocr_rows = try_ocr_transcript(
                    video_path,
                    language=effective_lang,
                    progress_callback=lambda p, m: ping(16 + int(max(0, min(100, int(p))) * 0.20), m),
                    control=control,
                )
                if ocr_rows:
                    segments = merge_dialogue_segments(ocr_rows)
                    used_ocr = bool(segments)
                    if used_ocr:
                        ping(37, f"OCR captions used · {len(segments)} line(s)")
        except Exception:
            used_ocr = False
            segments = []

        if not used_ocr and whisperx_available() and token:
            ping(16, "WhisperX + PyAnnote diarization on vocal stem…")
            wx_model = asr_model.replace("whisper-", "").replace("faster-whisper-", "") or "small"
            if wx_model == "cuda":
                wx_model = "large-v3"
            plan = build_dubbing_plan(
                asr_source,
                token,
                whisper_model_name=wx_model if wx_model in {"tiny", "base", "small", "medium", "large-v3", "large-v2"} else "small",
                device=_speech_device(),
                batch_chunk_size=15,
                progress_callback=lambda p, m: ping(16 + int(p * 0.22), m),
            )
            ping(37, "Saving dubbing plan…")
            save_plan(plan, str(job / "dubbing_plan.json"))
            segments = plan_to_segments(plan)
            if not segments:
                raise RuntimeError("WhisperX produced no dialogue segments.")
        else:
            if not used_ocr:
                clips = _speech_clip_pairs(asr_source, duration)
                if clips:
                    chunk_note = f" · {len(clips) // 2} speech turns on the soundtrack"
                else:
                    chunk_note = " · full track"
                ping(16, f"Transcribing the source track ({effective_lang}){chunk_note}…")
                segments = ASREngine.transcribe(
                    asr_source,
                    model_name=asr_model,
                    language=effective_lang,
                    clip_timestamps=clips,
                    vad_filter=not bool(clips),
                    progress_callback=lambda p, m: ping(16 + int(p * 0.22), m),
                    control=control,
                )
                segments = merge_dialogue_segments(segments)

        ping(37, "Fitting each line to the speech on the soundtrack…")
        segments = _fit_segments_to_soundtrack(segments, asr_source)

        if auto_chain:
            ping(38, "Classifying who speaks, gender, intent, and expression…")
            segments = analyze_movie_characters(
                segments,
                primary_voice=voice_id,
                secondary_voice=secondary_voice_id or voice_id,
                target_lang=target_lang,
                audio_path=asr_source,
                work_dir=job,
                progress_callback=lambda p, m: ping(max(38, min(41, int(p))), m),
            )
        ping(38, f"Transcript ready · {len(segments)} line(s)")
        share("transcript", [dict(seg) for seg in segments])
        if auto_chain:
            names = sorted({str(seg.get("speaker") or "") for seg in segments if seg.get("speaker")})
            cast = ", ".join(names[:4])
            if cast:
                ping(41, f"Cast · {cast}")
            ping(42, f"Movie translate · {len(segments)} line(s) · cast / gender / expression…")
            from claynext.models.movie_translate import (
                MovieTranslateOptions,
                pick_ollama_model,
                translate_movie_dialogue,
            )

            ollama_pick = pick_ollama_model(ollama_model, target_lang=target_lang)
            translated = translate_movie_dialogue(
                segments,
                target_lang=target_lang,
                source_lang=source_lang,
                options=MovieTranslateOptions(
                    translator=translator or "auto",
                    ollama_model=ollama_pick,
                    gemini_key=gemini_key,
                    fit_duration=translate_fit_duration,
                    use_slang=translate_slang,
                    use_expression=translate_expression,
                ),
                progress_callback=lambda p, m: ping(42 + int(p * 0.14), m),
            )
            from claynext.models.gender_voices import assign_gender_and_voices

            # Refine gender from source + dub text, then lock TTS voices per character.
            ping(56, "Locking TTS voices per character…")
            assign_gender_and_voices(
                translated,
                primary_voice=voice_id,
                secondary_voice=secondary_voice_id or voice_id,
                lang=target_lang,
                force_redetect=False,
            )
            ping(57, f"Cast ready · {len(translated)} line(s)")
            # Character detection auto-builds a clone voice per speaker and TTS uses it.
            clone_on = True
            try:
                from claynext.controllers.store import get_store

                clone_on = get_store().get_setting("dub", "clone_voices", "1") == "1"
            except Exception:
                clone_on = True
            if clone_on:
                try:
                    from claynext.models.voice_clone import clone_character_voices_from_movie

                    ping(57, "Cloning character voices from the movie for TTS…")
                    profiles = clone_character_voices_from_movie(
                        asr_source or video_path,
                        translated,
                        progress_callback=lambda _p, m: ping(57, m),
                    )
                    n_clone = sum(1 for p in profiles.values() if p.get("reference_wav"))
                    ping(57, f"Clone voices ready · {n_clone or len(profiles)} character(s)")
                except Exception:
                    pass
        else:
            ping(38, "Speaking the original lines with the lead voice…")
            for i, seg in enumerate(segments):
                if i % 8 == 0:
                    ping(38 + int((i / max(1, len(segments))) * 18), f"Preparing line {i + 1}/{len(segments)}…")
                seg["speaker"] = seg.get("speaker") or "Character 1"
                seg["tts_voice_hint"] = voice_id
                if not str(seg.get("translated_text") or "").strip():
                    seg["translated_text"] = seg.get("text") or ""
            translated = segments

        if auto_chain:
            from claynext.models.character_intel import planner_enabled, run_character_stage

            if planner_enabled():
                ping(57, "Planning each line's performance…")
                run_character_stage(
                    translated,
                    media_path=video_path,
                    audio_path=vocals_path or asr_source,
                    job_dir=job,
                    target_lang=target_lang,
                    source_lang=effective_lang,
                    base_voice=voice_id,
                    ping=ping,
                    share=share,
                )
        share("translated", [dict(seg) for seg in translated])
        # Step 4: TTS Speech Synthesis & Character Duration Fitting
        workers = _tts_workers(tts_workers)
        ping(58, f"Synthesizing dialogue on {workers} voice worker(s)…")
        placed = _speak_lines(
            translated,
            job=job,
            voice_id=voice_id,
            sync_mode=sync_mode,
            render=render,
            vocal_master=vocal_master,
            voiceover_boost=voiceover_boost,
            workers=workers,
            control=control,
            share=share,
            ping=ping,
        )

        if not render:
            ping(96, "Building the speech-free music and effects bed…")
            if bgm_separated and os.path.isfile(bgm_separated):
                bed = bgm_separated
            else:
                # Demucs already attempted above; fall back to the FFmpeg mid-side bed.
                bed = ensure_speech_bed(video_path, use_demucs=False)
            ping(99, "Assembling timeline clips…")
            ping(100, f"Voice track ready ({len(placed)} clips)")
            return {
                "output_path": "",
                "source_language": source_lang,
                "target_language": target_lang,
                "segments_dubbed": len(placed),
                "voice_used": voice_id,
                "secondary_voice_used": secondary_voice_id,
                "segments": translated,
                "duration_sec": duration,
                "bed_path": bed or "",
                "clean_audio": clean_audio if os.path.isfile(clean_audio) else "",
                "vocals_path": vocals_path if vocals_path and os.path.isfile(vocals_path) else "",
                "effects_path": effects_path if effects_path and os.path.isfile(effects_path) else "",
                "music_path": music_path if music_path and os.path.isfile(music_path) else "",
            }

        # Step 5: Fast Timeline Composition & Broadcast Voiceover Mastering
        ping(83, "Compositing dialogue timeline track…")
        raw_dialogue = str(job / "dialogue_raw.wav")
        overlay_clips(placed, duration, raw_dialogue, work_dir=str(job))
        ping(85, "Dialogue track laid out…")

        if vocal_master:
            ping(86, "Mastering voiceover track (presence EQ, dynamic limiter & clarity)…")
            mastered_dialogue = str(job / "dialogue_mastered.wav")
            dialogue = master_voiceover_track(raw_dialogue, mastered_dialogue, volume_boost=voiceover_boost)
            ping(88, "Voiceover master ready…")
        else:
            dialogue = raw_dialogue

        # Step 6: Isolate the original voice. The bed keeps effects and background.
        ping(89, "Removing the original voice · keeping effects and background…")
        if bgm_separated and os.path.isfile(bgm_separated):
            bgm_bed = bgm_separated
            ping(91, "Isolated bed ready · original voice removed…")
        else:
            isolated = ensure_speech_bed(video_path, use_demucs=False)
            if isolated and os.path.isfile(isolated):
                bgm_bed = isolated
                ping(91, "Effects and background isolated · original voice removed…")
            else:
                dialogue_intervals: list[tuple[float, float]] = []
                for item in translated:
                    txt = (item.get("translated_text") or item.get("text") or "").strip()
                    if not txt:
                        continue
                    st = float(item.get("start_sec") or timestamp_to_sec(item.get("start", "")))
                    en = float(item.get("end_sec") or timestamp_to_sec(item.get("end", "")))
                    dur = float(item.get("duration_sec") or 0.0)
                    if dur > 0:
                        en = max(en, st + dur)
                    if en > st:
                        dialogue_intervals.append((st, en))

                bgm_bed = str(job / "bgm_dynamic_ducked.wav")
                duck_target = max(0.0, min(0.50, float(background_vol)))
                if duck_target <= 0.05:
                    duck_target = 0.0
                clamped_fade_ms = max(50, min(500, int(fade_ms)))
                fade_sec = clamped_fade_ms / 1000.0
                dynamic_duck_audio(
                    full_wav,
                    dialogue_intervals,
                    bgm_bed,
                    duck_vol=duck_target,
                    fade_in_sec=fade_sec,
                    fade_out_sec=fade_sec,
                    fade_ms=clamped_fade_ms,
                    center_attenuation=1.0 if duck_target == 0.0 else max(0.0, min(1.0, float(center_attenuation))),
                )
                ping(91, "Dynamic duck bed ready…")

        # Step 7: Final Audio Mix
        ping(92, "Mixing cinema audio bed + dubbed dialogue…")
        mix_path = str(job / "final_mix.wav")
        mix_wavs([bgm_bed, dialogue], mix_path, weights=[1.0, float(voiceover_boost)])
        ping(93, "Final mix ready…")

        # Step 7: Video Mux
        ping(94, "Muxing dubbed audio into final video…")
        if overlays:
            muxed = str(job / "mux_audio.mp4")
            mux_video(video_path, mix_path, muxed)
            ping(96, "Rendering preview overlays…")
            compose_overlays(
                muxed,
                overlays,
                output_path,
                segments=translated,
                work_dir=str(job),
            )
        else:
            mux_video(video_path, mix_path, output_path)

        ping(100, f"Dubbing complete ({len(translated)} lines)")
        return {
            "output_path": output_path,
            "source_language": source_lang,
            "target_language": target_lang,
            "segments_dubbed": len(translated),
            "voice_used": voice_id,
            "secondary_voice_used": secondary_voice_id,
            "segments": translated,
            "duration_sec": duration,
            "bed_path": bgm_bed if os.path.isfile(bgm_bed) else "",
            "dialogue_path": dialogue if os.path.isfile(dialogue) else "",
            "clean_audio": clean_audio if os.path.isfile(clean_audio) else "",
            "vocals_path": vocals_path if vocals_path and os.path.isfile(vocals_path) else "",
            "effects_path": effects_path if effects_path and os.path.isfile(effects_path) else "",
            "music_path": music_path if music_path and os.path.isfile(music_path) else "",
        }

