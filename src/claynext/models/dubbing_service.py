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

from claynext.models.asr_service import ASREngine
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
            is_question = bool(i > 0 and any(prev_text.endswith(q) for q in ("?", "？", "吗", "呢", "吧", "呀", "？")))

            if i > 0 and (gap >= 0.85 or (gap >= 0.35 and is_question)):
                current_char_idx = 2 if current_char_idx == 1 else 1

            s["speaker"] = f"Character {current_char_idx}"
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

    if progress_callback:
        progress_callback(37, "Naming characters and reading expression…")
    apply_character_cast(segments)

    return assign_gender_and_voices(
        segments,
        primary_voice=primary_voice,
        secondary_voice=secondary_voice or primary_voice,
        lang=target_lang,
        force_redetect=True,
    )


def _try_demucs(wav_path: str, out_dir: Path, ping: Callable) -> tuple[str | None, str | None]:
    """Return (bgm_path, vocals_path) via demucs-mlx or demucs when settings allow."""
    try:
        from claynext.models.features import demucs_model_name, prefer_demucs_bed
        from claynext.models.stem_separation import separate_movie_stems

        if not prefer_demucs_bed():
            return None, None
        result = separate_movie_stems(
            wav_path,
            out_dir=out_dir / "stems",
            model=demucs_model_name(),
            progress_callback=ping,
        )
        bed = result.get("bed")
        vocals = result.get("vocals")
        return (bed if bed else None), (vocals if vocals else None)
    except Exception:
        return None, None


def _speech_clip_pairs(path: str, duration: float) -> list[float] | None:
    """Pack the extracted track into speech windows. Short media stays one pass."""
    if duration <= 45 or not path or not os.path.isfile(path):
        return None
    spans: list[tuple[float, float]] = []
    try:
        from claynext.adapters.ai import get_ai_adapter

        for item in get_ai_adapter().vad_chunk(path) or []:
            start = float(item.get("start_sec") or 0)
            end = float(item.get("end_sec") or 0)
            if end > start:
                spans.append((start, end))
    except Exception:
        spans = []
    windows: list[tuple[float, float]] = []
    if spans:
        cur_s, cur_e = spans[0]
        for start, end in spans[1:]:
            if end - cur_s <= 36 and start - cur_e <= 0.8:
                cur_e = end
            else:
                windows.append((max(0.0, cur_s - 0.12), min(duration, cur_e + 0.2)))
                cur_s, cur_e = start, end
        windows.append((max(0.0, cur_s - 0.12), min(duration, cur_e + 0.2)))
    else:
        cursor = 0.0
        while cursor < duration - 0.3:
            windows.append((cursor, min(duration, cursor + 40.0)))
            cursor += 40.0
    if len(windows) <= 1:
        return None
    pairs: list[float] = []
    for start, end in windows:
        if end - start >= 0.4:
            pairs.extend([round(start, 3), round(end, 3)])
    return pairs if len(pairs) >= 4 else None


def _tts_workers(requested: int | None) -> int:
    if requested is not None and int(requested) > 0:
        return max(1, int(requested))
    try:
        from claynext.adapters.cpu import get_cpu_adapter

        return max(1, int(get_cpu_adapter().hardware_plan().get("tts_workers") or 1))
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
        from claynext.models.gender_voices import expression_tag
        from claynext.models.tts_expression import has_expression_tags

        tag = expression_tag(str(item.get("expression") or ""))
        if tag and text_to_speak and not has_expression_tags(text_to_speak):
            text_to_speak = f"{tag} {text_to_speak}"
        raw_mp3 = str(job / f"seg_{idx + 1:04d}.mp3")
        TTSEngine.synthesize(text_to_speak, voice, raw_mp3)
        start = float(item.get("start_sec") or timestamp_to_sec(item.get("start", "")))
        end = float(item.get("end_sec") or timestamp_to_sec(item.get("end", "")))
        slot = max(0.15, end - start) if end > start else 2.0
        fitted = str(job / f"seg_{idx + 1:04d}_fit.wav")
        if sync_mode == "natural":
            min_t, max_t = 1.0, 1.0
        elif sync_mode == "subtle":
            min_t, max_t = 0.85, 1.25
        else:
            min_t, max_t = 0.65, 1.85
        fit_duration(raw_mp3, fitted, slot, min_tempo=min_t, max_tempo=max_t, pad_or_trim=True)
        if not render and vocal_master:
            fitted = master_voiceover_track(
                fitted, str(job / f"seg_{idx + 1:04d}_master.wav"), volume_boost=voiceover_boost,
            )
        item["audio_path"] = fitted
        item["start_ms"] = int(start * 1000)
        item["voice_id"] = voice
        item["duration"] = f"{slot:.1f}s"
        item["duration_sec"] = round(slot, 2)
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
        ping(7, "Probing media duration…")
        duration = probe_duration(video_path) or probe_duration(full_wav)
        if duration <= 0:
            raise RuntimeError("Could not read media duration.")

        ping(9, "Separating music / vocals (when available)…")
        bgm_separated, vocals_path = _try_demucs(
            full_wav,
            job,
            lambda p, m: ping(9 + int(max(0, min(100, int(p))) * 0.06), m),
        )
        asr_source = vocals_path or full_wav
        ping(15, "Vocal stem ready…" if vocals_path else "Using full mix for ASR…")

        # Step 1: Speech Recognition
        token = resolve_hf_token(hf_token)
        segments: list[dict] = []
        if whisperx_available() and token:
            ping(16, "WhisperX + PyAnnote diarization on vocal stem…")
            wx_model = asr_model.replace("whisper-", "").replace("faster-whisper-", "") or "small"
            if wx_model == "cuda":
                wx_model = "large-v3"
            plan = build_dubbing_plan(
                asr_source,
                token,
                whisper_model_name=wx_model if wx_model in {"tiny", "base", "small", "medium", "large-v3", "large-v2"} else "small",
                device="cuda",
                batch_chunk_size=15,
                progress_callback=lambda p, m: ping(16 + int(p * 0.22), m),
            )
            ping(37, "Saving dubbing plan…")
            save_plan(plan, str(job / "dubbing_plan.json"))
            segments = plan_to_segments(plan)
            if not segments:
                raise RuntimeError("WhisperX produced no dialogue segments.")
        else:
            effective_lang = source_lang if source_lang and source_lang != "Auto Detect" else asr_language
            clips = _speech_clip_pairs(asr_source, duration)
            chunk_note = f" · {len(clips) // 2} speech chunks" if clips else ""
            ping(16, f"Transcribing the source track ({effective_lang}){chunk_note}…")
            segments = ASREngine.transcribe(
                asr_source,
                model_name=asr_model,
                language=effective_lang,
                clip_timestamps=clips,
                progress_callback=lambda p, m: ping(16 + int(p * 0.22), m),
            )

        if auto_chain:
            ping(38, "Reading gender, expression, and character names…")
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
            ping(42, f"Translating {len(segments)} line(s) with cast, gender, and expression…")
            translated = TranslateEngine.translate_subtitles(
                segments,
                target_lang=target_lang,
                source_lang=source_lang,
                gemini_key=gemini_key,
                translator=translator,
                ollama_model=ollama_model,
                fit_duration=translate_fit_duration,
                use_slang=translate_slang,
                use_expression=translate_expression,
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
                    if en > st:
                        dialogue_intervals.append((st, en))

                bgm_bed = str(job / "bgm_dynamic_ducked.wav")
                duck_target = max(0.05, min(0.50, float(background_vol)))
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
                    center_attenuation=max(0.0, min(1.0, float(center_attenuation))),
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
        }

