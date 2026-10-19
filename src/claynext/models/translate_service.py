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
    parse_retry_after,
)

# Gemini Flash free tier: 15 RPM / 1,500 RPD. 15 lines/call ≈ 35–50 calls per episode.
BATCH_SIZE = 15
GEMINI_MIN_INTERVAL = 4.1

_gemini_lock = threading.Lock()
_last_gemini_call = 0.0
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
        ("auto", "Auto · $0 (Gemini → Ollama → Google)"),
        ("gemini", "Gemini Flash · free AI Studio"),
        ("google", "Google Translate · no key"),
        ("ollama", "Ollama · local / offline"),
        ("nllb", "NLLB-200 · Hugging Face (Offline NMT)"),
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
            urllib.request.urlopen(base + "/api/tags", timeout=1.5)
            return True
        except Exception:
            return False

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
        if not segments:
            raise RuntimeError("No lines to translate.")
        pool = get_key_pool()
        if gemini_key.strip():
            try:
                pool.add_key("gemini", gemini_key.strip(), "Session")
            except Exception:
                pass

        # Fill timing / syllable budgets so LLM can fit TTS slot length
        TranslateEngine._ensure_timing(segments, target_lang)

        engine = (translator or "auto").strip().lower()
        native = "Khmer (ភាសាខ្មែរ)" if target_lang == "Khmer" else target_lang
        model = (ollama_model or os.environ.get("OLLAMA_MODEL") or "qwen2.5:7b").strip()
        style = {
            "fit_duration": bool(fit_duration),
            "use_slang": bool(use_slang),
            "use_expression": bool(use_expression),
        }

        def ping(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, msg)

        def _llm(backend: str, ollama: str = ""):
            return TranslateEngine._translate_llm(
                segments,
                target_lang,
                backend,
                ollama,
                ping,
                source_lang=source_lang,
                style=style,
            )

        chain: list[tuple[str, Callable]] = []
        if engine == "gemini":
            chain = [("Gemini Flash (free tier)", lambda: _llm("gemini"))]
        elif engine == "ollama":
            chain = [(f"Ollama {model}", lambda: _llm("ollama", model))]
        elif engine == "nllb":
            chain = [("NLLB-200 Hugging Face", lambda: TranslateEngine._translate_nllb(segments, target_lang, ping, source_lang=source_lang))]
        elif engine == "google":
            chain = [("Google Translate", lambda: TranslateEngine._translate_google_batched(segments, target_lang, ping, source_lang=source_lang))]
        else:
            if pool.secrets("gemini"):
                chain.append(("Gemini Flash (free tier)", lambda: _llm("gemini")))
            if TranslateEngine.ollama_available():
                chain.append((f"Ollama {model}", lambda: _llm("ollama", model)))
            chain.append(("Google Translate", lambda: TranslateEngine._translate_google_batched(segments, target_lang, ping, source_lang=source_lang)))

        last_err = "Translation failed"
        for i, (label, fn) in enumerate(chain):
            ping(4, f"Translating {len(segments)} line(s) → {native} ({label})…")
            try:
                return fn()
            except Exception as exc:
                last_err = str(exc)
                if i + 1 < len(chain):
                    ping(6, f"{label} unavailable ({exc}); trying next $0 engine…")
                    continue
                raise RuntimeError(last_err) from exc
        raise RuntimeError(last_err)

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
            "gender", "gender_manual", "recommended_syllables", "speed_tolerance", "segment_id",
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
            for key in ("translations", "segments", "data", "items"):
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
            if rust and "VOICE REWRITE" in rust and (not fit or "SPOKEN FIT" in rust):
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
        ]
        n = 3
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
                f"{n}. EXPRESSION TAGS: when the source implies a non-verbal beat or strong emotion, "
                f"you MAY insert at most one short TTS cue at the start or mid-line from: {tags}. "
                f"Never invent story; never stack multiple tags; omit tags when the line is plain speech."
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
            f"{n}. SLANG: Match how this person talks. If they are casual, rude, or swearing, "
            f"keep that heat with the short word people actually say — slang, an insult, or a swear word. "
            f"Do not swap it for a polite or textbook word. Do not add a curse the line did not earn."
        )
        if "Khmer" in (target_lang or "") or "ខ្មែរ" in (target_lang or ""):
            rule += (
                " Khmer — \"What the hell are you doing?\" is said \"ឯងធ្វើអីហ្នឹង?\", "
                "not \"តើអ្នកកំពុងធ្វើអ្វី?\"."
            )
        return rule

    @staticmethod
    def _spoken_fit_rule(n: int, target_lang: str) -> str:
        rule = (
            f"{n}. SPOKEN FIT (critical): write what a voice actor can say inside duration_sec "
            f"at a natural pace. Aim at recommended_syllables.target. Do not pass max. "
            f"Those numbers are spoken beats, not written words. If unsure, choose the shorter line. "
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
            if rust:
                return rust
        except Exception:
            pass
        lang = "spoken Khmer" if "Khmer" in (target_lang or "") else target_lang
        return (
            "You are tightening dubbed lines that are too long to say in the actor's slot.\n"
            f"Write new words in {lang} that this person would actually say. Keep the same voice.\n"
            "If the line is slang, an insult, or a swear, keep that heat with a shorter spoken word. "
            "Do not polish it polite.\n"
            "Keep who did the action. Drop fillers and repeated owners.\n"
            "Each khmer_text must use at most max_units spoken beats (Khmer: syllables).\n"
            "Pattern: \"then he sent her to her room\" is said \"គាត់បានជួននាងទៅបន្ទប់\", "
            "not \"បន្ទាប់មកគាត់បានបញ្ជូននាងទៅបន្ទប់របស់នាង\".\n"
            "\"What the hell are you doing?\" stays rough and short, not a textbook question.\n"
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
            else:
                mapped = TranslateEngine._gemini_batch(prompt, progress_callback)
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
        translated: List[Dict[str, Any]] = []
        total = len(segments)
        for idx, seg in enumerate(segments):
            orig = (seg.get("text") or "").strip()
            if not orig:
                continue
            trans = TranslateEngine.translate_text(orig, target_lang, source_lang=source_lang)
            translated.append(TranslateEngine._pack_row(seg, idx, trans))
            if progress_callback:
                pct = 8 + int(((idx + 1) / total) * 88)
                progress_callback(pct, f"Translated {idx + 1}/{total}")
        if not translated:
            raise RuntimeError("No translatable speech found.")
        if progress_callback:
            progress_callback(100, f"Translated {len(translated)} line(s) to {target_lang}")
        return translated

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
        batches = [segments[i:i + BATCH_SIZE] for i in range(0, len(segments), BATCH_SIZE)]
        for b, batch in enumerate(batches):
            payload = TranslateEngine._payload_for(batch, target_lang=target_lang)
            prompt = TranslateEngine._dub_prompt(
                payload, target_lang, source_lang=source_lang, style=style,
            )
            if backend == "ollama":
                mapped = TranslateEngine._ollama_generate(prompt, ollama_model)
            else:
                mapped = TranslateEngine._gemini_batch(prompt, progress_callback)
            rows = TranslateEngine._map_batch(
                batch, mapped, target_lang, fallback_google=backend == "gemini", source_lang=source_lang
            )
            if (style or {}).get("fit_duration", True):
                TranslateEngine._tighten_to_slot(
                    rows, target_lang, backend, ollama_model, progress_callback,
                )
            by_id.update(rows)
            if progress_callback:
                pct = 10 + int(((b + 1) / len(batches)) * 85)
                label = "Ollama" if backend == "ollama" else "Gemini"
                progress_callback(pct, f"{label} batch {b + 1}/{len(batches)} ({BATCH_SIZE} lines)")
        rows = [by_id[s.get("id")] for s in segments if s.get("id") in by_id]
        if not rows:
            raise RuntimeError("Translator returned no lines.")
        if progress_callback:
            progress_callback(100, f"Translated {len(rows)} line(s)")
        return rows

    @staticmethod
    def _pace_gemini():
        global _last_gemini_call
        n_keys = max(1, len(get_key_pool().secrets("gemini")))
        interval = max(1.0, GEMINI_MIN_INTERVAL / n_keys)
        with _gemini_lock:
            wait = interval - (time.monotonic() - _last_gemini_call)
            if wait > 0:
                time.sleep(wait)
            _last_gemini_call = time.monotonic()

    @staticmethod
    def _gemini_batch(prompt: str, progress_callback: Callable = None) -> list[dict]:
        models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        last_err = "Gemini request failed"
        for model in models:
            try:
                TranslateEngine._pace_gemini()
                return TranslateEngine._gemini_generate(model, prompt, progress_callback)
            except Exception as exc:
                last_err = str(exc)
                continue
        raise RuntimeError(last_err)

    @staticmethod
    def _gemini_generate(model: str, prompt: str, progress_callback: Callable = None) -> list[dict]:
        def _do(api_key: str) -> list[dict]:
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
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code in (401, 403):
                    raise InvalidKeyError(f"{model}: {exc.code}") from exc
                if is_rate_limit(exc.code, detail):
                    raise RateLimitError(f"{model}: rate limited", parse_retry_after(exc.headers, detail)) from exc
                raise RuntimeError(f"{model}: {exc.code} {detail[:400]}") from exc
            text = (
                raw.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            return TranslateEngine._parse_lines(json.loads(text))

        return get_key_pool().call_with_rotation("gemini", _do, progress=progress_callback)

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

