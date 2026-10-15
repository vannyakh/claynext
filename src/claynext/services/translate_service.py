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

from claynext.services.llm_keys import (
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
    ) -> List[Dict[str, Any]]:
        if not segments:
            raise RuntimeError("No lines to translate.")
        pool = get_key_pool()
        if gemini_key.strip():
            try:
                pool.add_key("gemini", gemini_key.strip(), "Session")
            except Exception:
                pass

        engine = (translator or "auto").strip().lower()
        native = "Khmer (ភាសាខ្មែរ)" if target_lang == "Khmer" else target_lang
        model = (ollama_model or os.environ.get("OLLAMA_MODEL") or "qwen2.5:7b").strip()

        def ping(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, msg)

        chain: list[tuple[str, Callable]] = []
        if engine == "gemini":
            chain = [("Gemini Flash (free tier)", lambda: TranslateEngine._translate_llm(segments, target_lang, "gemini", "", ping, source_lang=source_lang))]
        elif engine == "ollama":
            chain = [(f"Ollama {model}", lambda: TranslateEngine._translate_llm(segments, target_lang, "ollama", model, ping, source_lang=source_lang))]
        elif engine == "nllb":
            chain = [("NLLB-200 Hugging Face", lambda: TranslateEngine._translate_nllb(segments, target_lang, ping, source_lang=source_lang))]
        elif engine == "google":
            chain = [("Google Translate", lambda: TranslateEngine._translate_google_batched(segments, target_lang, ping, source_lang=source_lang))]
        else:
            if pool.secrets("gemini"):
                chain.append(("Gemini Flash (free tier)", lambda: TranslateEngine._translate_llm(segments, target_lang, "gemini", "", ping, source_lang=source_lang)))
            if TranslateEngine.ollama_available():
                chain.append((f"Ollama {model}", lambda: TranslateEngine._translate_llm(segments, target_lang, "ollama", model, ping, source_lang=source_lang)))
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
    def _payload_for(batch: list[dict]) -> list[dict]:
        payload = []
        for s in batch:
            start = s.get("start_sec")
            end = s.get("end_sec")
            dur = None
            if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                dur = round(max(0.08, end - start), 2)
            payload.append({
                "id": s.get("id"),
                "segment_id": s.get("segment_id", s.get("id")),
                "speaker": s.get("speaker") or "",
                "duration_sec": dur,
                "text": (s.get("text") or "").strip(),
                "recommended_syllables": s.get("recommended_syllables") or {},
                "speed_tolerance": s.get("speed_tolerance") or {},
            })
        return payload

    @staticmethod
    def _dub_prompt(payload: list[dict], target_lang: str, source_lang: str = "auto") -> str:
        lang_name = "natural conversational Khmer (ភាសាខ្មែរ)" if target_lang == "Khmer" else target_lang
        src_name = f"from {source_lang} " if source_lang and source_lang not in {"auto", "Auto Detect"} else ""
        return (
            f"You are a cinematic dubbing adapter translating film dialogue {src_name}into "
            f"{lang_name}.\n"
            "Rules:\n"
            "1. Preserve emotional tone, character nuance, and actor delivery.\n"
            "2. Respect duration_sec and recommended_syllables (min/target/max) so speech matches the visual character duration.\n"
            "3. Stay within speed_tolerance (typically 0.65–1.85).\n"
            "4. Return strictly a JSON array of objects with keys id (or segment_id) and khmer_text "
            "(use khmer_text for the translation output even if target language is not Khmer).\n\n"
            f"Dialogue segments:\n{json.dumps(payload, ensure_ascii=False)}"
        )

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
    ) -> List[Dict[str, Any]]:
        by_id: dict[Any, dict] = {}
        batches = [segments[i:i + BATCH_SIZE] for i in range(0, len(segments), BATCH_SIZE)]
        for b, batch in enumerate(batches):
            payload = TranslateEngine._payload_for(batch)
            prompt = TranslateEngine._dub_prompt(payload, target_lang, source_lang=source_lang)
            if backend == "ollama":
                mapped = TranslateEngine._ollama_generate(prompt, ollama_model)
            else:
                mapped = TranslateEngine._gemini_batch(prompt, progress_callback)
            by_id.update(
                TranslateEngine._map_batch(
                    batch, mapped, target_lang, fallback_google=backend == "gemini", source_lang=source_lang
                )
            )
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
        from claynext.services.hf_hub import is_model_downloaded
        return is_model_downloaded(model_name)

    @staticmethod
    def pull_nllb_model(
        model_name: str = "JustFrederik/nllb-200-distilled-600M-ct2-int8",
        progress_callback: Callable = None,
    ) -> str:
        from claynext.services.hf_hub import pull_model
        return pull_model(model_name, progress_callback)

    @staticmethod
    def _translate_nllb(
        segments: List[Dict[str, Any]],
        target_lang: str,
        progress_callback: Callable = None,
        source_lang: str = "auto",
        model_name: str = "JustFrederik/nllb-200-distilled-600M-ct2-int8",
    ) -> List[Dict[str, Any]]:
        from claynext.services.hf_hub import get_local_model_path, is_model_downloaded, pull_model

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
