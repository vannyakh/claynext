"""
Caption translation for dubbing — $0 paths.

- Gemini Flash via Google AI Studio free tier (rotating keys, 15 RPM)
- Google Translate (no key)
- Ollama local (Qwen / Llama, no API key)
- Meta NLLB-200 local (fully offline)
TTS stays Edge neural (km-KH) and needs no key.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List

from claynext.models.llm_keys import (
    InvalidKeyError,
    RateLimitError,
    get_key_pool,
    is_rate_limit,
    note_llm_usage,
    parse_retry_after,
)

# Gemini Flash free tier: ~15 RPM / key. Pack by lines + chars; roll keys for speed.
BATCH_SIZE = 48
BATCH_MAX_CHARS = 9000
GEMINI_MIN_INTERVAL = 4.2  # per-key floor (~14 RPM); more keys → more parallel throughput
GOOGLE_MAX_WORKERS = 6

_gemini_lock = threading.Lock()
_last_gemini_call_by_key: dict[str, float] = {}
_nllb_lock = threading.Lock()
_nllb_tok = None
_nllb_model = None


class TranslateEngine:
    TARGET_LANGUAGES = [
        "Khmer",
        "Chinese",
        "Vietnamese",
        "English",
        "Japanese",
        "Korean",
        "Thai",
        "Chinese (Simplified)",
        "Spanish",
        "French",
        "German",
        "Russian",
    ]

    LANG_CODES = {
        "Khmer": "km",
        "Chinese": "zh-CN",
        "Chinese (Simplified)": "zh-CN",
        "Chinese (Traditional)": "zh-TW",
        "Vietnamese": "vi",
        "English": "en",
        "Japanese": "ja",
        "Korean": "ko",
        "Thai": "th",
        "Spanish": "es",
        "French": "fr",
        "German": "de",
        "Russian": "ru",
    }

    NLLB_CODES = {
        "Khmer": "khm_Khmr",
        "Chinese": "zho_Hans",
        "Vietnamese": "vie_Latn",
        "English": "eng_Latn",
        "Japanese": "jpn_Jpan",
        "Korean": "kor_Hang",
        "Thai": "tha_Thai",
        "Chinese (Simplified)": "zho_Hans",
        "Spanish": "spa_Latn",
        "French": "fra_Latn",
        "German": "deu_Latn",
        "Russian": "rus_Cyrl",
    }

    ENGINES = [
        ("auto", "Auto · Best movie (Gemini → Ollama → NLLB → Google)"),
        ("movie", "Movie dub · cinematic rewrite"),
        ("gemini", "Gemini Flash · free AI Studio"),
        ("qwen", "Qwen · DashScope"),
        ("deepseek", "DeepSeek"),
        ("groq", "Groq"),
        ("openrouter", "OpenRouter"),
        ("openai", "OpenAI"),
        ("mistral", "Mistral"),
        ("moonshot", "Moonshot"),
        ("glm", "GLM"),
        ("xai", "xAI"),
        ("ollama", "Ollama · local cinematic"),
        ("nllb", "NLLB-200 · offline NMT"),
        ("google", "Google Translate · literal"),
    ]

    # Approximate speaking units / second for TTS duration budgeting in LLM prompts.
    _PACE_RATES = {
        "Khmer": 3.5,
        "Chinese": 4.0,
        "Chinese (Simplified)": 4.0,
        "Chinese (Traditional)": 4.0,
        "Japanese": 4.2,
        "Korean": 4.0,
        "Vietnamese": 3.8,
        "Thai": 3.8,
        "English": 3.2,
        "Spanish": 3.4,
        "French": 3.3,
        "German": 3.1,
        "Russian": 3.2,
    }

    @staticmethod
    def estimate_speech_quota(duration_sec: float, target_lang: str = "") -> dict[str, int]:
        """min / target / max speaking units for a line slot (LLM duration fit).

        Prefers Rust via DubbingAdapter; falls back to local pace table.
        """
        try:
            from claynext.adapters.dubbing import get_dubbing_adapter

            return get_dubbing_adapter().estimate_speech_quota(
                duration_sec, target_lang or ""
            )
        except Exception:
            pass
        dur = max(0.0, float(duration_sec or 0.0))
        rate = TranslateEngine._PACE_RATES.get(target_lang or "", 3.5)
        beats = dur * rate
        target = max(1, int(round(beats * 0.90)))
        return {
            "min": max(1, int(round(beats * 0.60))),
            "target": target,
            "max": max(target, int(round(beats))),
        }

    @staticmethod
    def spoken_units(text: str, target_lang: str = "") -> int:
        """Beats a line takes to say. Khmer counts syllables."""
        try:
            from claynext.adapters.dubbing import get_dubbing_adapter

            counted = get_dubbing_adapter().spoken_units(text, target_lang)
            if counted is not None:
                return counted
        except Exception:
            pass
        return TranslateEngine._spoken_units_py(text, target_lang)

    @staticmethod
    def spoken_units_fast(text: str, target_lang: str = "") -> int:
        """Fast in-memory syllable / beat calculation without spawning subprocesses.

        Essential for GUI table rendering, tooltips, and real-time typing where
        forking processes blocks the Qt main thread and causes UI FPS drops.
        """
        return TranslateEngine._spoken_units_py(text, target_lang)

    @staticmethod
    def _spoken_units_py(text: str, target_lang: str = "") -> int:
        bare = []
        skipping = False
        for ch in text or "":
            if ch == "[":
                skipping = True
                continue
            if ch == "]" and skipping:
                skipping = False
                continue
            if not skipping:
                bare.append(ch)
        raw = "".join(bare).strip()
        if not raw:
            return 0
        khmer = "Khmer" in (target_lang or "") or any("\u1780" <= ch <= "\u17ff" for ch in raw)
        if khmer:
            return max(1, TranslateEngine._khmer_beats(raw))
        cjk = sum(1 for ch in raw if "\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" or "\uac00" <= ch <= "\ud7af")
        latin = sum(1 for ch in raw if ch.isascii() and ch.isalpha())
        if cjk and (not latin or cjk * 2 >= latin):
            return max(1, cjk)
        beats = 0
        in_vowel = False
        for ch in raw:
            if ch in "aeiouyAEIOUY":
                if not in_vowel:
                    beats += 1
                    in_vowel = True
            else:
                in_vowel = False
        return max(1, beats)

    @staticmethod
    def _khmer_beats(text: str) -> int:
        chars = list(text or "")
        n = len(chars)
        i = 0
        beats = 0

        def base(ch: str) -> bool:
            return "\u1780" <= ch <= "\u17b3"

        def vowel(ch: str) -> bool:
            return "\u17b6" <= ch <= "\u17c5"

        def sign(ch: str) -> bool:
            return "\u17c6" <= ch <= "\u17d1" or ch in "\u17d3\u17dd"

        def coda(index: int) -> bool:
            j = index + 1
            if j < n and chars[j] == "\u17d2":
                return False
            while j < n and sign(chars[j]):
                j += 1
            if j < n and vowel(chars[j]):
                return False
            return True

        while i < n:
            if not base(chars[i]):
                i += 1
                continue
            beats += 1
            i += 1
            while i < n:
                if chars[i] == "\u17d2" and i + 1 < n and base(chars[i + 1]):
                    i += 2
                    continue
                if vowel(chars[i]) or sign(chars[i]):
                    i += 1
                    continue
                if base(chars[i]) and coda(i):
                    i += 1
                    continue
                break
        return beats

    @staticmethod
    def gemini_key() -> str:
        keys = get_key_pool().secrets("gemini")
        return keys[0] if keys else ""

    @staticmethod
    def ollama_host() -> str:
        return (os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")

    @staticmethod
    def ollama_available(host: str = "") -> bool:
        base = (host or TranslateEngine.ollama_host()).rstrip("/")
        try:
            req = urllib.request.Request(base + "/api/tags", headers={"User-Agent": "Claynext/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    @staticmethod
    def list_ollama_models(host: str = "") -> tuple[bool, list[dict[str, Any]]]:
        """Check Ollama availability and return (available, model_records)."""
        base = (host or TranslateEngine.ollama_host()).rstrip("/")
        try:
            req = urllib.request.Request(f"{base}/api/tags", headers={"User-Agent": "Claynext/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                return True, models if isinstance(models, list) else []
        except Exception:
            return False, []

    @staticmethod
    def get_ollama_model_names(host: str = "") -> tuple[bool, list[str]]:
        """Return (available, list_of_installed_model_names)."""
        avail, models = TranslateEngine.list_ollama_models(host)
        names: list[str] = []
        for m in models:
            if isinstance(m, dict):
                n = str(m.get("name") or m.get("model") or "").strip()
                if n and n not in names:
                    names.append(n)
        return avail, names

    @staticmethod
    def translate_subtitles(
        segments: List[Dict[str, Any]],
        target_lang: str,
        source_lang: str = "auto",
        progress_callback: Callable = None,
        gemini_key: str = "",
        translator: str = "auto",
        ollama_model: str = "",
        *,
        fit_duration: bool = True,
        use_slang: bool = True,
        use_expression: bool = True,
    ) -> List[Dict[str, Any]]:
        """Public entry — delegates to the cinematic movie-translate flow."""
        from claynext.models.movie_translate import translate_movie_dialogue

        return translate_movie_dialogue(
            segments,
            target_lang=target_lang,
            source_lang=source_lang,
            translator=translator,
            ollama_model=ollama_model,
            gemini_key=gemini_key,
            fit_duration=fit_duration,
            use_slang=use_slang,
            use_expression=use_expression,
            progress_callback=progress_callback,
        )

    @staticmethod
    def translate_text(text: str, target_lang: str, source_lang: str = "auto") -> str:
        raw = (text or "").strip()
        if not raw:
            return ""
        code = TranslateEngine.LANG_CODES.get(target_lang, "km")
        src_code = (
            TranslateEngine.LANG_CODES.get(source_lang, "auto")
            if source_lang and source_lang not in {"auto", "Auto Detect"}
            else "auto"
        )

        # 1. Try Google Translate Chrome Extension API (highest reliability, free, no 429)
        try:
            url = (
                f"https://translate.googleapis.com/translate_a/single?client=dict-chrome-ex&sl={src_code}"
                f"&tl={code}&dt=t&q={urllib.parse.quote(raw)}"
            )
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=6) as r:
                data = json.loads(r.read().decode("utf-8"))
                if data and isinstance(data, list) and data[0] and isinstance(data[0], list):
                    joined = "".join(part[0] for part in data[0] if part and len(part) > 0 and part[0])
                    if joined.strip():
                        return joined.strip()
        except Exception:
            pass

        # 2. Try deep_translator GoogleTranslator
        try:
            from deep_translator import GoogleTranslator
            out = GoogleTranslator(source=src_code, target=code).translate(raw)
            if out and str(out).strip():
                return str(out).strip()
        except Exception:
            pass

        # 3. Try direct Google gtx endpoint with desktop user agent
        try:
            url = (
                f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={src_code}"
                f"&tl={code}&dt=t&q={urllib.parse.quote(raw)}"
            )
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=6) as r:
                data = json.loads(r.read().decode("utf-8"))
                if data and isinstance(data, list) and data[0] and isinstance(data[0], list):
                    joined = "".join(part[0] for part in data[0] if part and len(part) > 0 and part[0])
                    if joined.strip():
                        return joined.strip()
        except Exception:
            pass

        return raw

    @staticmethod
    def _pack_row(seg: dict, idx: int, trans: str) -> dict:
        orig = (seg.get("text") or "").strip()
        row = {
            "id": seg.get("id", idx + 1),
            "start": seg.get("start", ""),
            "end": seg.get("end", ""),
            "speaker": seg.get("speaker", ""),
            "original_text": orig,
            "text": orig,
            "translated_text": trans,
        }
        for key in (
            "start_sec", "end_sec", "duration_sec", "tts_voice_hint", "voice_id",
            "gender", "gender_manual", "expression", "character",
            "recommended_syllables", "speed_tolerance", "segment_id",
        ):
            if key in seg:
                row[key] = seg[key]
        return row

    @staticmethod
    def _line_text(item: dict) -> str:
        for key in ("khmer_dialogue", "khmer_text", "translated_text", "text", "translation"):
            val = (item.get(key) or "").strip() if isinstance(item, dict) else ""
            if val:
                return val
        return ""

    @staticmethod
    def _parse_lines(parsed: Any) -> list[dict]:
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        if isinstance(parsed, dict):
            for key in ("translations", "segments", "lines", "result", "data", "items"):
                if isinstance(parsed.get(key), list):
                    parsed = parsed[key]
                    break
        if not isinstance(parsed, list):
            raise RuntimeError("Translator JSON was not a list.")
        return parsed

    @staticmethod
    def _ensure_timing(segments: list[dict], target_lang: str) -> None:
        """Ensure start/end/duration + speech quota exist for duration-aware translate."""
        from claynext.models.dubbing_service import timestamp_to_sec

        for seg in segments:
            start = seg.get("start_sec")
            end = seg.get("end_sec")
            if not isinstance(start, (int, float)):
                start = timestamp_to_sec(str(seg.get("start") or ""))
                seg["start_sec"] = start
            if not isinstance(end, (int, float)):
                end = timestamp_to_sec(str(seg.get("end") or ""))
                seg["end_sec"] = end
            dur = float(seg.get("duration_sec") or 0.0)
            if dur <= 0 and isinstance(start, (int, float)) and isinstance(end, (int, float)):
                dur = max(0.15, float(end) - float(start))
                seg["duration_sec"] = round(dur, 3)
            quota = seg.get("recommended_syllables")
            if not isinstance(quota, dict) or not quota.get("target"):
                seg["recommended_syllables"] = TranslateEngine.estimate_speech_quota(
                    float(seg.get("duration_sec") or dur or 2.0),
                    target_lang,
                )
            if not seg.get("speed_tolerance"):
                seg["speed_tolerance"] = {"min_rate": 0.65, "max_rate": 1.85}

    @staticmethod
    def _payload_for(batch: list[dict], target_lang: str = "") -> list[dict]:
        payload = []
        for s in batch:
            start = s.get("start_sec")
            end = s.get("end_sec")
            dur = s.get("duration_sec")
            if not isinstance(dur, (int, float)) or float(dur) <= 0:
                if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                    dur = round(max(0.08, end - start), 2)
                else:
                    dur = 2.0
            quota = s.get("recommended_syllables") or {}
            if not isinstance(quota, dict) or not quota.get("target"):
                quota = TranslateEngine.estimate_speech_quota(float(dur), target_lang)
            payload.append({
                "id": s.get("id"),
                "segment_id": s.get("segment_id", s.get("id")),
                "speaker": s.get("speaker") or "",
                "gender": s.get("gender") or "",
                "expression": s.get("expression") or "",
                "duration_sec": float(dur),
                "text": (s.get("text") or s.get("original_text") or "").strip(),
                "recommended_syllables": quota,
                "speed_tolerance": s.get("speed_tolerance") or {"min_rate": 0.65, "max_rate": 1.85},
            })
        return payload

    @staticmethod
    def _dub_prompt(
        payload: list[dict],
        target_lang: str,
        source_lang: str = "auto",
        *,
        style: dict | None = None,
    ) -> str:
        style = style or {}
        # Prefer Rust via DubbingAdapter so GUI/features share one prompt builder.
        try:
            from claynext.adapters.dubbing import get_dubbing_adapter

            rust = get_dubbing_adapter().build_dub_prompt(
                payload, target_lang, source_lang, style=style
            )
            # An older binary has no voice-rewrite rule, so keep the Python prompt.
            fit = bool(style.get("fit_duration", True))
            if (
                rust
                and "VOICE REWRITE" in rust
                and "NEUTRAL SPEECH" in rust
                and "CAST:" in rust
                and (not fit or "SPOKEN FIT" in rust)
            ):
                return rust
        except Exception:
            pass

        fit = bool(style.get("fit_duration", True))
        slang = bool(style.get("use_slang", True))
        expression = bool(style.get("use_expression", True))
        lang_name = "natural conversational Khmer (ភាសាខ្មែរ)" if target_lang == "Khmer" else target_lang
        src_name = f"from {source_lang} " if source_lang and source_lang not in {"auto", "Auto Detect"} else ""

        rules = [
            TranslateEngine._voice_rewrite_rule(),
            "2. Keep the scene true. Do not invent plot, names, or actions. Change the words so the line sounds spoken.",
            "3. CAST: speaker is this character's name. gender is Female, Male, or empty. "
            "expression is this line's feeling (laugh, sigh, shout, whisper, sad, angry, or empty). "
            "Write that person, and keep the same name sounding the same across lines.",
        ]
        n = 4
        if fit:
            rules.append(TranslateEngine._spoken_fit_rule(n, target_lang))
            n += 1
        if slang:
            rules.append(TranslateEngine._register_rule(n, target_lang))
            n += 1
        if expression:
            from claynext.models.tts_expression import EXPRESSION_CHIPS

            tags = ", ".join(tok for _label, tok in EXPRESSION_CHIPS)
            rules.append(
                f"{n}. EXPRESSION TAGS: when the source has a breath, a laugh, or a clear emotion, "
                f"you MAY insert at most one TTS cue from: {tags}. Put it before the words it colors. "
                f"The tag is a voice delay, not a word: do not translate it, and do not speak the brackets. "
                f"If the segment's expression is set, start with that tag and no other. "
                f"Never stack tags. Omit them when expression is empty and the line is plain speech."
            )
            n += 1
        rules.append(
            f"{n}. Return STRICTLY a JSON array of objects with keys id (or segment_id) and khmer_text "
            f"(use khmer_text for the translated spoken line even when the target is not Khmer)."
        )

        features = []
        if fit:
            features.append("duration-fit")
        if slang:
            features.append("slang/idiom")
        if expression:
            features.append("expression-tags")
        feat = ", ".join(features) if features else "literal"

        return (
            f"You are a dubbing writer for film dialogue {src_name}into {lang_name}.\n"
            "You know the script. Write a new spoken line, not a translation of each word.\n"
            "It must sound like this person talking, in the same breath.\n"
            f"Active features: {feat}.\n"
            "Rules:\n"
            + "\n".join(rules)
            + f"\n\nDialogue segments:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    @staticmethod
    def _voice_rewrite_rule() -> str:
        return (
            "1. VOICE REWRITE: Do not translate word by word. Understand the line, then write new words — "
            "the best line a native speaker would say in that moment. Keep who did it, what happened, "
            "the feeling, and the sound of the voice (short or drawn out, sharp or soft, polite or rough). "
            "Do not copy the source grammar. A dictionary line nobody would say is wrong."
        )

    @staticmethod
    def _register_rule(n: int, target_lang: str) -> str:
        rule = (
            f"{n}. NEUTRAL SPEECH: When the line uses slang, an idiom, or a figure of speech, "
            f"say what it means in real life. Use the everyday phrase a person would actually speak — "
            f"neutral, natural, and clear. Do not translate the idiom word by word. "
            f"Do not invent extra swearing. Do not turn it into a textbook sentence."
        )
        if "Khmer" in (target_lang or "") or "ខ្មែរ" in (target_lang or ""):
            rule += (
                " Khmer — \"piece of cake\" is said \"ងាយណាស់\", not a cake. "
                "\"What the hell are you doing?\" is said \"ឯងធ្វើអីហ្នឹង?\", "
                "not \"តើអ្នកកំពុងធ្វើអ្វី?\"."
            )
        return rule

    @staticmethod
    def _spoken_fit_rule(n: int, target_lang: str) -> str:
        rule = (
            f"{n}. SPOKEN FIT (critical): this line is one spoken turn. Fit the words inside duration_sec "
            f"so the voice finishes before the next segment starts. Aim at recommended_syllables.target. "
            f"Do not pass max. Those numbers are spoken beats, not written words. "
            f"If unsure, choose the shorter line. "
            f"Drop fillers that do not change the action (then, so, well, and, you know). "
            f"Drop a repeated owner when that person is already in the line (\"her room\" → \"the room\")."
        )
        if "Khmer" in (target_lang or "") or "ខ្មែរ" in (target_lang or ""):
            rule += (
                " Khmer pattern — source \"then he sent her to her room\"; "
                "too long to say: \"បន្ទាប់មកគាត់បានបញ្ជូននាងទៅបន្ទប់របស់នាង\"; "
                "say: \"គាត់បានជួននាងទៅបន្ទប់\"."
            )
        return rule

    @staticmethod
    def _fit_prompt(lines: list[dict], target_lang: str) -> str:
        try:
            from claynext.adapters.dubbing import get_dubbing_adapter

            rust = get_dubbing_adapter().build_fit_prompt(lines, target_lang)
            if rust and "NEUTRAL SPEECH" in rust:
                return rust
        except Exception:
            pass
        lang = "spoken Khmer" if "Khmer" in (target_lang or "") else target_lang
        return (
            "You are tightening dubbed lines that are too long to say in the actor's slot.\n"
            f"Write new words in {lang} that this person would actually say. Keep the same voice.\n"
            "NEUTRAL SPEECH: say slang and idioms as the real-world phrase, short and clear. "
            "Do not translate them word by word, and do not add a curse.\n"
            "Keep expression tags such as [sigh] if they are already there. Do not add a new one.\n"
            "Keep who did the action. Drop fillers and repeated owners.\n"
            "Each khmer_text must use at most max_units spoken beats (Khmer: syllables). Tags do not count.\n"
            "Pattern: \"then he sent her to her room\" is said \"គាត់បានជួននាងទៅបន្ទប់\", "
            "not \"បន្ទាប់មកគាត់បានបញ្ជូននាងទៅបន្ទប់របស់នាង\".\n"
            "Return STRICTLY a JSON array of objects with keys id and khmer_text.\n\n"
            f"Lines:\n{json.dumps(lines, ensure_ascii=False)}"
        )

    @staticmethod
    def _tighten_to_slot(
        rows: dict,
        target_lang: str,
        backend: str,
        ollama_model: str,
        progress_callback: Callable = None,
    ) -> None:
        """One rewrite for lines whose spoken beats run past the slot."""
        pending = []
        for row in rows.values():
            quota = row.get("recommended_syllables") or {}
            cap = int(quota.get("max") or 0)
            text = str(row.get("translated_text") or "")
            if cap > 0 and text:
                pending.append((row, cap, text))
        if not pending:
            return
        counts = TranslateEngine._spoken_units_many(
            [text for _row, _cap, text in pending], target_lang,
        )
        overflow: list[dict] = []
        for (row, cap, text), units in zip(pending, counts):
            if units > cap:
                overflow.append({
                    "id": row.get("id"),
                    "text": row.get("original_text") or row.get("text") or "",
                    "khmer_text": text,
                    "duration_sec": row.get("duration_sec"),
                    "max_units": cap,
                    "units": units,
                })
        if not overflow:
            return
        prompt = TranslateEngine._fit_prompt(overflow, target_lang)
        try:
            if backend == "ollama":
                mapped = TranslateEngine._ollama_generate(prompt, ollama_model)
            elif backend == "gemini":
                mapped = TranslateEngine._gemini_batch(prompt, progress_callback)
            else:
                mapped = TranslateEngine._chat_batch(backend, prompt, progress_callback)
        except Exception:
            return
        by_key = {}
        for item in mapped:
            if isinstance(item, dict):
                by_key[str(item.get("id", item.get("segment_id")))] = item
        for row in rows.values():
            item = by_key.get(str(row.get("id")))
            if not item:
                continue
            fresh = TranslateEngine._line_text(item)
            if not fresh:
                continue
            old = str(row.get("translated_text") or "")
            fresh_n, old_n = TranslateEngine._spoken_units_many([fresh, old], target_lang)
            if fresh_n < old_n:
                row["translated_text"] = fresh

    @staticmethod
    def _spoken_units_many(texts: list[str], target_lang: str = "") -> list[int]:
        try:
            from claynext.adapters.dubbing import get_dubbing_adapter

            counted = get_dubbing_adapter().spoken_units_many(texts, target_lang)
            if counted is not None and len(counted) == len(texts):
                return counted
        except Exception:
            pass
        return [TranslateEngine._spoken_units_py(text, target_lang) for text in texts]

    @staticmethod
    def _map_batch(
        batch: list[dict],
        mapped: list[dict],
        target_lang: str,
        *,
        fallback_google: bool = True,
        source_lang: str = "auto",
    ) -> dict[Any, dict]:
        lookup = {}
        for item in mapped:
            if not isinstance(item, dict):
                continue
            key = item.get("id", item.get("segment_id"))
            lookup[str(key)] = item
        rows = {}
        for s in batch:
            key = str(s.get("id"))
            item = lookup.get(key) or lookup.get(str(s.get("segment_id", ""))) or {}
            trans = TranslateEngine._line_text(item)
            if not trans and fallback_google:
                trans = TranslateEngine.translate_text((s.get("text") or ""), target_lang, source_lang=source_lang)
            if not trans:
                trans = (s.get("text") or "").strip()
            rows[s.get("id")] = TranslateEngine._pack_row(s, int(s.get("id") or 0), trans)
        return rows

    @staticmethod
    def _translate_google_batched(
        segments: List[Dict[str, Any]],
        target_lang: str,
        progress_callback: Callable = None,
        source_lang: str = "auto",
    ) -> List[Dict[str, Any]]:
        import concurrent.futures

        total = len(segments)
        if total == 0:
            raise RuntimeError("No translatable speech found.")

        results: dict[int, str] = {}
        def _fetch(idx: int, text: str) -> tuple[int, str]:
            if not text.strip():
                return idx, ""
            return idx, TranslateEngine.translate_text(text, target_lang, source_lang=source_lang)

        # Concurrent Google calls — capped to reduce free-endpoint 429s
        workers = min(GOOGLE_MAX_WORKERS, max(2, total))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_fetch, idx, str(seg.get("text") or seg.get("original_text") or ""))
                for idx, seg in enumerate(segments)
            ]
            completed = 0
            for fut in concurrent.futures.as_completed(futures):
                idx, trans = fut.result()
                results[idx] = trans
                completed += 1
                if progress_callback:
                    pct = 8 + int((completed / total) * 88)
                    progress_callback(pct, f"Translated {completed}/{total}")

        translated: List[Dict[str, Any]] = []
        for idx, seg in enumerate(segments):
            orig = (seg.get("text") or seg.get("original_text") or "").strip()
            if not orig:
                continue
            trans = results.get(idx, "")
            translated.append(TranslateEngine._pack_row(seg, idx, trans or orig))

        if not translated:
            raise RuntimeError("No translatable speech found.")
        if progress_callback:
            progress_callback(100, f"Translated {len(translated)} line(s) to {target_lang}")
        return translated

    @staticmethod
    def _pack_batches(segments: List[Dict[str, Any]]) -> list[list[dict]]:
        """Pack lines into API batches by count + char budget (fewer wasted RPM)."""
        batches: list[list[dict]] = []
        cur: list[dict] = []
        chars = 0
        for seg in segments:
            text = str(seg.get("text") or seg.get("original_text") or "")
            cost = max(24, len(text) + 48)
            if cur and (len(cur) >= BATCH_SIZE or chars + cost > BATCH_MAX_CHARS):
                batches.append(cur)
                cur = []
                chars = 0
            cur.append(seg)
            chars += cost
        if cur:
            batches.append(cur)
        return batches

    @staticmethod
    def _translate_llm(
        segments: List[Dict[str, Any]],
        target_lang: str,
        backend: str,
        ollama_model: str,
        progress_callback: Callable = None,
        source_lang: str = "auto",
        style: dict | None = None,
    ) -> List[Dict[str, Any]]:
        by_id: dict[Any, dict] = {}
        batches = TranslateEngine._pack_batches(segments)
        style = style or {}

        def _run_one(batch: list[dict]) -> dict[Any, dict]:
            payload = TranslateEngine._payload_for(batch, target_lang=target_lang)
            prompt = TranslateEngine._dub_prompt(
                payload, target_lang, source_lang=source_lang, style=style,
            )
            if backend == "ollama":
                mapped = TranslateEngine._ollama_generate(prompt, ollama_model)
            elif backend == "gemini":
                mapped = TranslateEngine._gemini_batch(prompt, progress_callback)
            else:
                mapped = TranslateEngine._chat_batch(backend, prompt, progress_callback)
            return TranslateEngine._map_batch(
                batch,
                mapped,
                target_lang,
                fallback_google=backend != "ollama",
                source_lang=source_lang,
            )

        # Cloud keys: run concurrent batches when several keys are ready.
        from claynext.models.llm_providers import CHAT_PROVIDERS

        parallel = 1
        if backend in {"gemini", *CHAT_PROVIDERS}:
            parallel = max(1, min(4, get_key_pool().ready_count(backend), len(batches)))

        if parallel <= 1 or len(batches) <= 1:
            for b, batch in enumerate(batches):
                by_id.update(_run_one(batch))
                if progress_callback:
                    pct = 10 + int(((b + 1) / max(1, len(batches))) * 80)
                    label = TranslateEngine._engine_label(backend)
                    progress_callback(
                        pct, f"{label} batch {b + 1}/{len(batches)} ({len(batch)} lines)"
                    )
        else:
            import concurrent.futures

            done = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as pool:
                futs = {pool.submit(_run_one, batch): i for i, batch in enumerate(batches)}
                for fut in concurrent.futures.as_completed(futs):
                    by_id.update(fut.result())
                    done += 1
                    if progress_callback:
                        pct = 10 + int((done / len(batches)) * 80)
                        progress_callback(
                            pct,
                            f"{TranslateEngine._engine_label(backend)} parallel {done}/{len(batches)} "
                            f"· {parallel} key lane(s)",
                        )

        rows_map = by_id
        # One tighten pass for overflow when duration-fit is on (saves mid-batch RPM).
        if style.get("force_fit") or style.get("fit_duration", True):
            if progress_callback:
                progress_callback(92, "Fitting long lines into speech slots…")
            TranslateEngine._tighten_to_slot(
                rows_map, target_lang, backend, ollama_model, progress_callback,
            )

        rows = [rows_map[s.get("id")] for s in segments if s.get("id") in rows_map]
        if not rows:
            raise RuntimeError("Translator returned no lines.")
        if progress_callback:
            progress_callback(100, f"Translated {len(rows)} line(s)")
        return rows

    @staticmethod
    def _pace_gemini(api_key: str = ""):
        """Per-key pacing so rolling keys each keep their own RPM budget."""
        key = (api_key or "_default")[-24:]
        interval = max(0.8, GEMINI_MIN_INTERVAL)
        with _gemini_lock:
            last = _last_gemini_call_by_key.get(key, 0.0)
            wait = interval - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            _last_gemini_call_by_key[key] = time.monotonic()

    @staticmethod
    def _engine_label(backend: str) -> str:
        from claynext.models.llm_providers import CHAT_PROVIDERS

        if backend in CHAT_PROVIDERS:
            return CHAT_PROVIDERS[backend]["label"]
        return {"ollama": "Ollama", "gemini": "Gemini Flash"}.get(backend, backend)

    @staticmethod
    def _chat_batch(provider: str, prompt: str, progress_callback: Callable = None) -> list[dict]:
        from claynext.models.llm_chat import chat_text, json_from_text

        text = chat_text(provider, prompt, progress=progress_callback)
        return TranslateEngine._parse_lines(json_from_text(text))

    @staticmethod
    def _gemini_batch(prompt: str, progress_callback: Callable = None) -> list[dict]:
        # Prefer Flash 2.0; only drop to 1.5 after the whole key pool fails that model.
        models = ["gemini-2.0-flash", "gemini-1.5-flash"]
        last_err = "Gemini request failed"
        for model in models:
            try:
                return TranslateEngine._gemini_generate(model, prompt, progress_callback)
            except RateLimitError as exc:
                last_err = str(exc)
                continue
            except Exception as exc:
                last_err = str(exc)
                # Invalid / 404 model → try next; other errors still try next model once.
                continue
        raise RuntimeError(last_err)

    @staticmethod
    def _gemini_generate(model: str, prompt: str, progress_callback: Callable = None) -> list[dict]:
        def _do(api_key: str) -> list[dict]:
            TranslateEngine._pace_gemini(api_key)
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                f"?key={urllib.parse.quote(api_key)}"
            )
            body = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
            }).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                note_llm_usage(model, raw)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code in (401, 403):
                    raise InvalidKeyError(f"{model}: {exc.code}") from exc
                if is_rate_limit(exc.code, detail):
                    raise RateLimitError(
                        f"{model}: rate limited", parse_retry_after(exc.headers, detail)
                    ) from exc
                raise RuntimeError(f"{model}: {exc.code} {detail[:400]}") from exc
            text = (
                raw.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            return TranslateEngine._parse_lines(json.loads(text))

        return get_key_pool().call_with_rotation(
            "gemini", _do, progress=progress_callback, max_cooldown_waits=3
        )

    @staticmethod
    def _ollama_generate(prompt: str, model: str) -> list[dict]:
        host = TranslateEngine.ollama_host()
        name = model or "qwen2.5:7b"
        body = json.dumps({
            "model": name,
            "prompt": prompt,
            "format": "json",
            "stream": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            host + "/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Ollama is not running at {host}. Install from ollama.com then: ollama run {name}"
            ) from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"Ollama {name}: {exc.code} {detail}") from exc
        text = raw.get("response") or ""
        if not text.strip():
            raise RuntimeError(f"Ollama {name} returned an empty response.")
        try:
            return TranslateEngine._parse_lines(json.loads(text))
        except Exception:
            return TranslateEngine._parse_lines(text)

    @staticmethod
    def is_nllb_downloaded(model_name: str = "JustFrederik/nllb-200-distilled-600M-ct2-int8") -> bool:
        from claynext.models.hf_hub import is_model_downloaded
        return is_model_downloaded(model_name)

    @staticmethod
    def pull_nllb_model(
        model_name: str = "JustFrederik/nllb-200-distilled-600M-ct2-int8",
        progress_callback: Callable = None,
    ) -> str:
        from claynext.models.hf_hub import pull_model
        return pull_model(model_name, progress_callback)

    @staticmethod
    def _translate_nllb(
        segments: List[Dict[str, Any]],
        target_lang: str,
        progress_callback: Callable = None,
        source_lang: str = "auto",
        model_name: str = "JustFrederik/nllb-200-distilled-600M-ct2-int8",
    ) -> List[Dict[str, Any]]:
        from claynext.models.hf_hub import get_local_model_path, is_model_downloaded, pull_model

        tgt_code = TranslateEngine.NLLB_CODES.get(target_lang)
        if not tgt_code:
            raise RuntimeError(f"NLLB does not support {target_lang}.")

        # Auto-detect or resolve source language code
        src_code = "eng_Latn"
        if source_lang and source_lang not in ("auto", "Auto Detect"):
            src_code = TranslateEngine.NLLB_CODES.get(source_lang, "eng_Latn")
        else:
            sample_blob = " ".join((s.get("text") or "") for s in segments[:5])
            if any("\u4e00" <= ch <= "\u9fff" for ch in sample_blob):
                src_code = "zho_Hans"
            elif any("\u1780" <= ch <= "\u17ff" for ch in sample_blob):
                src_code = "khm_Khmr"
            elif any("\u3040" <= ch <= "\u30ff" for ch in sample_blob):
                src_code = "jpn_Jpan"
            elif any("\uac00" <= ch <= "\ud7af" for ch in sample_blob):
                src_code = "kor_Hang"

        # Check and pull from Hugging Face if not available
        local_dir = get_local_model_path(model_name)
        if not local_dir:
            if progress_callback:
                progress_callback(5, f"Pulling {model_name} from Hugging Face…")
            local_dir = pull_model(model_name, progress_callback)

        rows: List[Dict[str, Any]] = []
        total = len(segments)

        # 1. Preferred high-speed CTranslate2 path
        try:
            import ctranslate2
            from transformers import AutoTokenizer

            if progress_callback:
                progress_callback(12, "Loading NLLB model…")

            translator = ctranslate2.Translator(local_dir)
            tokenizer = AutoTokenizer.from_pretrained(local_dir, src_lang=src_code)

            for idx, seg in enumerate(segments):
                orig = (seg.get("text") or "").strip()
                if not orig:
                    continue
                tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(orig))
                results = translator.translate_batch(
                    [tokens],
                    target_prefix=[[tgt_code]],
                    max_decoding_length=128,
                    repetition_penalty=1.2,
                    no_repeat_ngram_size=3,
                )
                out_tokens = results[0].hypotheses[0]
                clean_tokens = [t for t in out_tokens if t not in (tgt_code, "</s>")]
                ids = tokenizer.convert_tokens_to_ids(clean_tokens)
                trans = tokenizer.decode(ids).strip()
                if not trans:
                    trans = orig
                rows.append(TranslateEngine._pack_row(seg, idx, trans))
                if progress_callback:
                    pct = 12 + int(((idx + 1) / total) * 85)
                    progress_callback(pct, f"NLLB {idx + 1}/{total}")
        except Exception as ct2_err:
            # 2. Fallback to standard Transformers if torch is present
            try:
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
                tok = AutoTokenizer.from_pretrained(local_dir)
                if hasattr(tok, "src_lang"):
                    tok.src_lang = src_code
                model = AutoModelForSeq2SeqLM.from_pretrained(local_dir)
                bos = getattr(tok, "lang_code_to_id", {}).get(tgt_code, 2)
                for idx, seg in enumerate(segments):
                    orig = (seg.get("text") or "").strip()
                    if not orig:
                        continue
                    inputs = tok(orig, return_tensors="pt")
                    tokens = model.generate(**inputs, forced_bos_token_id=bos, max_length=128)
                    trans = tok.batch_decode(tokens, skip_special_tokens=True)[0].strip() or orig
                    rows.append(TranslateEngine._pack_row(seg, idx, trans))
                    if progress_callback:
                        pct = 12 + int(((idx + 1) / total) * 85)
                        progress_callback(pct, f"NLLB {idx + 1}/{total}")
            except Exception:
                raise RuntimeError(f"NLLB offline translation failed: {ct2_err}")

        if not rows:
            raise RuntimeError("NLLB produced no translations.")
        if progress_callback:
            progress_callback(100, f"Translated {len(rows)} line(s) with NLLB")
        return rows

