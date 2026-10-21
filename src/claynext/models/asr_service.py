"""
Automatic Speech Recognition for media files.

Supports Local Whisper AI (faster-whisper) and Cloud Gemini Flash AI Transcript.
Never returns placeholder / demo captions.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List

# Monkeypatch av.open to protect against PyAV metadata_errors signature changes
try:
    import av
    _orig_av_open = av.open

    def _safe_av_open(*args, **kwargs):
        try:
            return _orig_av_open(*args, **kwargs)
        except TypeError as exc:
            if "metadata_errors" in str(exc):
                kwargs.pop("metadata_errors", None)
                return _orig_av_open(*args, **kwargs)
            raise

    av.open = _safe_av_open
except Exception:
    pass

PLACEHOLDER_SNIPPETS = (
    "Welcome to Claynext Studio",
    "Our PySide6 engine processes audio frames",
    "Let us check out the TTS generator",
)

_LANG_CODES = {
    "Auto Detect": None,
    "English": "en",
    "Vietnamese": "vi",
    "Japanese": "ja",
    "Korean": "ko",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Chinese": "zh",
    "Khmer": "km",
}


def is_placeholder_transcript(segments: list | None) -> bool:
    if not segments:
        return False
    blob = " ".join(str(seg.get("text") or "") for seg in segments)
    return any(snip in blob for snip in PLACEHOLDER_SNIPPETS)


_HALLUCINATION_RE = re.compile(
    r"(thank(?:s| you) for watching|please subscribe|subtitles by|amara\.org|"
    r"字幕由|请不吝|谢谢观看|感谢观看|订阅|点赞|转发)",
    re.IGNORECASE,
)


def transcript_keep(
    text: str,
    *,
    avg_logprob: float = 0.0,
    no_speech_prob: float = 0.0,
) -> bool:
    """Drop low-confidence and hallucination lines. Keep real dialogue."""
    if not is_meaningful_speech(text):
        return False
    if _HALLUCINATION_RE.search(text or ""):
        return False
    # Dialogue under a score often scores lower than clean speech. Drop only
    # lines that are clearly not speech, so a quiet reply still reaches TTS.
    if no_speech_prob >= 0.88:
        return False
    if avg_logprob <= -2.05:
        return False
    if avg_logprob <= -1.55 and no_speech_prob >= 0.62:
        return False
    return True


def transcript_confidence(avg_logprob: float, no_speech_prob: float) -> float:
    lp = max(0.0, min(1.0, (float(avg_logprob) + 1.4) / 1.4))
    speech = 1.0 - max(0.0, min(1.0, float(no_speech_prob)))
    return round(0.65 * lp + 0.35 * speech, 3)


def is_meaningful_speech(text: str) -> bool:
    """Return True if text contains actual dialogue words, not just punctuation, artifacts or ellipses."""
    if not text:
        return False
    # Strip whitespace, standard punctuation, and Chinese punctuation
    cleaned = re.sub(
        r"[\s\.\,\!\?\:\;\。\，\！\？\：\；\…\—\-\~\"\'\(\)\[\]\{\}\<\>\/\\\|`*_+=#@$^&]+",
        "",
        str(text),
    )
    # Strip common Whisper hallucinations during music/ambient noise (口, ♪, etc.)
    cleaned = re.sub(r"[口♪♫\u266a\u266b]+", "", cleaned)
    return len(cleaned.strip()) > 0


def merge_dialogue_segments(
    segments: list[dict[str, Any]],
    max_gap_sec: float = 0.40,
    max_duration_sec: float = 6.0,
) -> list[dict[str, Any]]:
    """
    Clean up hallucinated ellipses/artifacts and merge adjacent sub-second speech
    fragments from the same dialogue turn so movie dialogue reads continuously.
    """
    valid = [seg for seg in segments if is_meaningful_speech(str(seg.get("text") or ""))]
    if not valid:
        return segments

    def _sec(ts_str: str) -> float:
        try:
            parts = str(ts_str).replace(",", ".").split(":")
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            return 0.0
        except Exception:
            return 0.0

    merged: list[dict[str, Any]] = []
    for seg in valid:
        if not merged:
            merged.append(dict(seg))
            continue

        prev = merged[-1]
        prev_end = _sec(prev.get("end", "00:00:00,000"))
        cur_start = _sec(seg.get("start", "00:00:00,000"))
        cur_end = _sec(seg.get("end", "00:00:00,000"))
        first_start = _sec(prev.get("start", "00:00:00,000"))

        gap = max(0.0, cur_start - prev_end)
        total_dur = max(0.0, cur_end - first_start)

        same_speaker = not prev.get("speaker") or not seg.get("speaker") or prev.get("speaker") == seg.get("speaker")

        if gap <= max_gap_sec and total_dur <= max_duration_sec and same_speaker:
            p_text = str(prev.get("text", "")).strip()
            c_text = str(seg.get("text", "")).strip()
            has_cjk = any("\u4e00" <= char <= "\u9fff" for char in p_text + c_text)
            sep = "" if has_cjk else " "
            prev["text"] = f"{p_text}{sep}{c_text}"
            prev["end"] = seg["end"]
            if "words" in prev and "words" in seg:
                prev["words"].extend(seg.get("words", []))
        else:
            merged.append(dict(seg))

    for i, item in enumerate(merged, start=1):
        item["id"] = i
    return merged


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _fmt_ts(seconds: float) -> str:
    ms = int(round(max(0.0, float(seconds)) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def _extract_wav(media_path: str, wav_path: str, progress_callback: Callable | None = None):
    if progress_callback:
        progress_callback(12, "Extracting audio…")
    try:
        from claynext.adapters.ffmpeg_service import demux_wav

        demux_wav(media_path, wav_path, rate=16000, channels=1)
        if os.path.isfile(wav_path) and os.path.getsize(wav_path) > 0:
            return
    except Exception:
        pass
    cmd = [
        _ffmpeg(),
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-y",
        "-i", media_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        wav_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=300, check=False)
    if proc.returncode != 0 or not os.path.isfile(wav_path) or os.path.getsize(wav_path) == 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or "Could not extract audio from this media file.")


def _speech_device() -> str:
    try:
        from claynext.adapters.resources import resource_plan

        return "cuda" if resource_plan().get("speech_device") == "cuda" else "cpu"
    except Exception:
        return "cpu"


_WHISPER_SIZE_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large": "Systran/faster-whisper-large-v3",
}


def _resolve_model(model_name: str, device_override: str = "auto") -> tuple[str, str]:
    raw = (model_name or "whisper-small").strip()
    lower = raw.lower()
    dev_ov = (device_override or "auto").lower()
    if dev_ov in {"cpu", "int8"}:
        device = "cpu"
    elif dev_ov in {"cuda", "gpu", "float16"}:
        device = "cuda"
    else:
        device = "cuda" if "cuda" in lower else _speech_device()
    size = lower.replace("faster-whisper-", "").replace("whisper-", "")
    size = size.replace("-cuda", "").strip() or "small"
    aliases = {
        "large": "large-v3",
        "large-v3": "large-v3",
        "tiny": "tiny",
        "base": "base",
        "small": "small",
        "medium": "medium",
    }
    return aliases.get(size, "small"), device


def _local_whisper_source(size: str) -> str:
    """Prefer a cached snapshot path so Whisper does not re-hit Hugging Face."""
    repo = _WHISPER_SIZE_REPOS.get(size) or f"Systran/faster-whisper-{size}"
    try:
        from claynext.models.hf_hub import get_local_model_path

        local = get_local_model_path(repo)
        if local:
            return local
    except Exception:
        pass
    return size


def _transcribe_gemini(
    media_path: str,
    language: str = "Auto Detect",
    progress_callback: Callable | None = None,
) -> List[Dict[str, Any]]:
    from claynext.models.llm_keys import InvalidKeyError, RateLimitError, get_key_pool

    pool = get_key_pool()
    secrets = pool.secrets("gemini")
    if not secrets:
        raise RuntimeError("No Gemini API key found. Configure API keys in Settings or select a local Whisper model.")

    if progress_callback:
        progress_callback(12, "Extracting audio for Gemini AI Transcript…")

    with tempfile.TemporaryDirectory(prefix="claynext-gemini-asr-") as tmp:
        audio_path = os.path.join(tmp, "audio.mp3")
        try:
            from claynext.adapters.ffmpeg_service import extract_audio

            extract_audio(media_path, audio_path, rate=16000, channels=1, bitrate="48k")
        except Exception:
            cmd = [
                _ffmpeg(),
                "-hide_banner",
                "-loglevel", "error",
                "-nostdin",
                "-y",
                "-i", media_path,
                "-vn",
                "-ac", "1",
                "-ar", "16000",
                "-c:a", "libmp3lame",
                "-b:a", "48k",
                audio_path,
            ]
            proc = subprocess.run(cmd, capture_output=True, timeout=300, check=False)
            if proc.returncode != 0 or not os.path.isfile(audio_path):
                raise RuntimeError("Failed to extract audio track for Gemini.")
        if not os.path.isfile(audio_path):
            raise RuntimeError("Failed to extract audio track for Gemini.")

        with open(audio_path, "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode("utf-8")

        lang_instruction = (
            f"The spoken language is {language}."
            if language != "Auto Detect"
            else "Automatically detect the spoken language."
        )
        prompt = (
            f"You are an AI transcription engine. Transcribe the audio accurately. {lang_instruction}\n"
            "Return a JSON array of segment objects with start, end timestamps and text.\n"
            "Schema:\n"
            "[\n"
            "  {\n"
            '    "id": 1,\n'
            '    "start": "00:00:00,000",\n'
            '    "end": "00:00:03,500",\n'
            '    "speaker": "Speaker 1",\n'
            '    "text": "Hello world"\n'
            "  }\n"
            "]\n"
            "Timestamps MUST follow 'HH:MM:SS,mmm' format. Return ONLY valid JSON array."
        )

        def _call_gemini(secret: str):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={secret}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"inline_data": {"mime_type": "audio/mp3", "data": b64_audio}},
                            {"text": prompt},
                        ]
                    }
                ],
                "generationConfig": {
                    "response_mime_type": "application/json",
                },
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    from claynext.models.llm_keys import note_llm_usage
                    note_llm_usage("gemini-3.8-flash", resp_data)
                    cand_text = resp_data["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(cand_text)
            except urllib.error.HTTPError as err:
                body = err.read().decode("utf-8", errors="replace")
                if err.code == 429:
                    raise RateLimitError("Gemini rate limited", retry_after=30.0)
                if err.code in (400, 403) and ("API_KEY_INVALID" in body or "API key not valid" in body):
                    raise InvalidKeyError("Invalid API key")
                raise RuntimeError(f"Gemini API error ({err.code}): {body}")

        if progress_callback:
            progress_callback(40, "Processing AI Transcript via Gemini Flash…")

        res = pool.call_with_rotation("gemini", _call_gemini, progress=progress_callback)
        if not isinstance(res, list):
            raise RuntimeError("Gemini did not return valid transcript items.")

        rows: List[Dict[str, Any]] = []
        for i, item in enumerate(res, start=1):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            rows.append({
                "id": i,
                "start": str(item.get("start") or "00:00:00,000"),
                "end": str(item.get("end") or "00:00:01,000"),
                "speaker": str(item.get("speaker") or ""),
                "text": text,
            })

        if not rows:
            raise RuntimeError("Gemini detected no dialogue lines.")
        return merge_dialogue_segments(rows)


class ASREngine:
    MODELS = [
        "whisper-small",
        "whisper-medium",
        "whisper-large-v3",
        "whisper-tiny",
        "whisper-base",
        "gemini-flash",
        "faster-whisper-cuda",
        "sglang-omni",
    ]
    LANGUAGES = list(_LANG_CODES.keys())

    @staticmethod
    def transcribe(
        media_path: str,
        model_name: str = "whisper-small",
        language: str = "Auto Detect",
        progress_callback: Callable = None,
        vad_filter: bool = True,
        beam_size: int = 5,
        word_timestamps: bool = False,
        initial_prompt: str | None = None,
        compute_device: str = "auto",
        clip_timestamps: list[float] | None = None,
        control: Any = None,
    ) -> List[Dict[str, Any]]:
        if not media_path or not os.path.isfile(media_path):
            raise FileNotFoundError("Media file not found.")

        if (model_name or "").strip().lower() in {"sglang-omni", "sglang"}:
            try:
                if progress_callback:
                    progress_callback(12, "Transcribing with SGLang-Omni…")
                from claynext.models.sglang_omni import transcribe as sglang_transcribe

                rows = merge_dialogue_segments(
                    sglang_transcribe(media_path, language, control=control)
                )
                if progress_callback:
                    progress_callback(100, f"SGLang-Omni transcript complete ({len(rows)} lines)")
                return rows
            except Exception as exc:
                if progress_callback:
                    progress_callback(18, f"SGLang-Omni error: {exc} — falling back to Whisper…")
                model_name = "whisper-small"

        if os.path.splitext(media_path)[1].lower() in {
            ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts", ".m2ts",
        }:
            try:
                from claynext.models.features import transcript_ocr_enabled

                if transcript_ocr_enabled():
                    from claynext.models.ocr_service import try_ocr_transcript

                    ocr_rows = try_ocr_transcript(
                        media_path,
                        language=language,
                        progress_callback=progress_callback,
                    )
                    if ocr_rows:
                        if progress_callback:
                            progress_callback(100, f"OCR captions used ({len(ocr_rows)} lines)")
                        return ocr_rows
            except Exception:
                pass

        # 1. Gemini Cloud AI Transcript
        if "gemini" in (model_name or "").lower():
            try:
                rows = _transcribe_gemini(media_path, language=language, progress_callback=progress_callback)
                if progress_callback:
                    progress_callback(100, f"Gemini AI Transcript complete ({len(rows)} lines)")
                return rows
            except Exception as exc:
                if progress_callback:
                    progress_callback(20, f"Gemini error: {exc} — falling back to Whisper AI…")
                # Fallback to local whisper
                model_name = "whisper-small"

        # 2. Local Whisper AI (faster-whisper)
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "Transcription engine is not installed. Run: uv add faster-whisper"
            ) from exc

        size, device = _resolve_model(model_name, device_override=compute_device)
        model_source = _local_whisper_source(size)
        lang = _LANG_CODES.get(language, None)
        local_only = os.path.isdir(model_source)

        if progress_callback:
            where = "cache" if local_only else "hub"
            progress_callback(8, f"Loading Whisper {size} ({device}, {where})…")

        if compute_device == "float16" and device == "cuda":
            compute = "float16"
        elif compute_device == "int8":
            compute = "int8"
        else:
            compute = "float16" if device == "cuda" else "int8"

        cpu_threads = 4
        if device == "cpu":
            try:
                from claynext.adapters.resources import resource_plan

                cpu_threads = max(1, int(resource_plan()["threads"]))
            except Exception:
                cpu_threads = 4
        try:
            model = WhisperModel(
                model_source,
                device=device,
                compute_type=compute,
                cpu_threads=cpu_threads,
                num_workers=1,
                local_files_only=local_only,
            )
        except Exception:
            if device != "cpu":
                if progress_callback:
                    progress_callback(10, "GPU unavailable — using CPU…")
                model = WhisperModel(
                    model_source,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=cpu_threads,
                    num_workers=1,
                    local_files_only=local_only,
                )
            else:
                raise RuntimeError(f"Could not load Whisper model '{size}'.") from None

        with tempfile.TemporaryDirectory(prefix="claynext-asr-") as tmp:
            wav_path = os.path.join(tmp, "audio.wav")
            _extract_wav(media_path, wav_path, progress_callback)
            if progress_callback:
                progress_callback(35, "Transcribing speech…")

            transcribe_kwargs: dict[str, Any] = {
                "language": lang,
                "vad_filter": bool(vad_filter),
                "beam_size": max(1, min(10, int(beam_size))),
                "word_timestamps": bool(word_timestamps),
            }
            # Cover the whole movie, then drop low-confidence junk below.
            transcribe_kwargs["condition_on_previous_text"] = False
            if vad_filter:
                transcribe_kwargs["vad_parameters"] = dict(
                    min_silence_duration_ms=160,
                    speech_pad_ms=480,
                    threshold=0.20,
                )
            if initial_prompt and initial_prompt.strip():
                transcribe_kwargs["initial_prompt"] = initial_prompt.strip()
            if clip_timestamps and len(clip_timestamps) >= 2:
                transcribe_kwargs["clip_timestamps"] = clip_timestamps

            try:
                segments_iter, info = model.transcribe(wav_path, **transcribe_kwargs)
            except TypeError:
                transcribe_kwargs.pop("clip_timestamps", None)
                segments_iter, info = model.transcribe(wav_path, **transcribe_kwargs)
            rows: List[Dict[str, Any]] = []
            for i, seg in enumerate(segments_iter, start=1):
                text = (seg.text or "").strip()
                if not text:
                    continue
                avg_lp = float(getattr(seg, "avg_logprob", 0.0) or 0.0)
                no_speech = float(getattr(seg, "no_speech_prob", 0.0) or 0.0)
                if not transcript_keep(text, avg_logprob=avg_lp, no_speech_prob=no_speech):
                    continue
                row_item: Dict[str, Any] = {
                    "id": i,
                    "start": _fmt_ts(seg.start or 0),
                    "end": _fmt_ts(seg.end or 0),
                    "speaker": "",
                    "text": text,
                    "confidence": transcript_confidence(avg_lp, no_speech),
                }
                if word_timestamps and hasattr(seg, "words") and seg.words:
                    row_item["words"] = [
                        {"word": w.word, "start": w.start, "end": w.end, "prob": getattr(w, "probability", 1.0)}
                        for w in seg.words
                    ]
                rows.append(row_item)
                if progress_callback and i % 4 == 0:
                    progress_callback(min(90, 35 + i), f"Transcribed {i} line(s)…")

        if not rows:
            raise RuntimeError("No speech found in this media.")
        if is_placeholder_transcript(rows):
            raise RuntimeError("Refusing to use placeholder captions.")

        rows = merge_dialogue_segments(rows)

        if progress_callback:
            detected = getattr(info, "language", None)
            extra = f" · lang={detected}" if detected else ""
            progress_callback(100, f"Transcription complete{extra}")
        return rows

    @staticmethod
    def export_srt(segments: List[Dict[str, Any]], file_path: str):
        with open(file_path, "w", encoding="utf-8") as f:
            for seg in segments:
                f.write(f"{seg['id']}\n")
                f.write(f"{seg['start']} --> {seg['end']}\n")
                f.write(f"{seg['text']}\n\n")

    @staticmethod
    def export_vtt(segments: List[Dict[str, Any]], file_path: str):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            for seg in segments:
                start = str(seg["start"]).replace(",", ".")
                end = str(seg["end"]).replace(",", ".")
                f.write(f"{start} --> {end}\n")
                f.write(f"{seg['text']}\n\n")

