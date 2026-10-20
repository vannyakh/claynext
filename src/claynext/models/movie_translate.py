"""
Best-path cinematic translation for movie dubbing.

Dub pipeline call path:
  DubbingEngine → translate_movie_dialogue → TranslateEngine LLM / NLLB / Google

Auto / movie engine order:
  1. Gemini Flash (rolling API keys, parallel batches)
  2. Ollama (aya-expanse / qwen3 / requested — local quality)
  3. NLLB-200 offline (if weights are present)
  4. Google Translate (last-resort literal)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from claynext.models.llm_keys import get_key_pool


# Preference order for local cinematic rewrite (installed tags win).
_OLLAMA_PREF_DEFAULT = (
    "qwen3:8b",
    "aya-expanse:8b",
    "qwen2.5:7b",
    "qwen2.5:3b",
    "llama3.2:3b",
)

# Khmer / SEA dialogue: prefer multilingual Aya when present.
_OLLAMA_PREF_KHMER = (
    "aya-expanse:8b",
    "qwen3:8b",
    "qwen2.5:7b",
    "qwen2.5:3b",
)

_CAST_KEYS = (
    "speaker",
    "gender",
    "gender_manual",
    "expression",
    "character",
    "tts_voice_hint",
    "voice_id",
    "start_sec",
    "end_sec",
    "duration_sec",
    "recommended_syllables",
    "speed_tolerance",
    "segment_id",
)


@dataclass(frozen=True)
class MovieTranslateOptions:
    translator: str = "auto"
    ollama_model: str = ""
    gemini_key: str = ""
    fit_duration: bool = True
    use_slang: bool = True
    use_expression: bool = True


def _installed_ollama() -> set[str]:
    try:
        from claynext.models.translate_service import TranslateEngine

        avail, names = TranslateEngine.get_ollama_model_names()
        if not avail:
            return set()
        return {str(n).strip() for n in names if str(n).strip()}
    except Exception:
        return set()


def pick_ollama_model(requested: str = "", *, target_lang: str = "") -> str:
    """Pick the best installed Ollama tag for movie dialogue rewrite."""
    want = (requested or os.environ.get("OLLAMA_MODEL") or "").strip()
    installed = _installed_ollama()
    pref = (
        _OLLAMA_PREF_KHMER
        if "Khmer" in (target_lang or "") or "ខ្មែរ" in (target_lang or "")
        else _OLLAMA_PREF_DEFAULT
    )
    if want and (not installed or want in installed):
        return want
    for tag in pref:
        if tag in installed:
            return tag
    return want or pref[0]


def resolve_movie_engine_chain(
    translator: str,
    *,
    target_lang: str = "",
    ollama_model: str = "",
) -> list[tuple[str, str, str]]:
    """
    Build (label, backend, model) steps for cinematic translate.

    backend: gemini | ollama | nllb | google
    """
    from claynext.models.translate_service import TranslateEngine

    engine = (translator or "auto").strip().lower()
    model = pick_ollama_model(ollama_model, target_lang=target_lang)
    pool = get_key_pool()
    cinematic = engine in {"", "auto", "movie", "best"}

    steps: list[tuple[str, str, str]] = []

    def _add(label: str, backend: str, mod: str = "") -> None:
        steps.append((label, backend, mod))

    if engine == "gemini":
        _add("Gemini Flash · cinematic", "gemini")
    elif engine == "ollama":
        _add(f"Ollama {model} · cinematic", "ollama", model)
    elif engine == "nllb":
        _add("NLLB-200 · offline", "nllb")
    elif engine == "google":
        _add("Google Translate", "google")
    elif cinematic:
        if pool.secrets("gemini") or pool.ready_count("gemini") > 0:
            _add("Gemini Flash · cinematic (rolling keys)", "gemini")
        if TranslateEngine.ollama_available():
            _add(f"Ollama {model} · cinematic", "ollama", model)
        try:
            if TranslateEngine.is_nllb_downloaded():
                _add("NLLB-200 · offline", "nllb")
        except Exception:
            pass
        _add("Google Translate · fallback", "google")
    else:
        # Unknown id → same as auto
        return resolve_movie_engine_chain(
            "auto", target_lang=target_lang, ollama_model=ollama_model
        )

    return steps


def _merge_cast(originals: list[dict[str, Any]], translated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep speaker / gender / timing from the transcript on rewritten lines."""
    by_id = {str(s.get("id")): s for s in originals if s.get("id") is not None}
    out: list[dict[str, Any]] = []
    for row in translated:
        src = by_id.get(str(row.get("id")), {})
        merged = dict(row)
        for key in _CAST_KEYS:
            if key not in merged or merged.get(key) in (None, "", {}, []):
                if key in src and src.get(key) not in (None, "", {}, []):
                    merged[key] = src[key]
            elif key in ("speaker", "gender", "expression", "character") and not merged.get(key):
                if src.get(key):
                    merged[key] = src[key]
        # Always prefer source timing / quota when present.
        for key in ("start_sec", "end_sec", "duration_sec", "recommended_syllables", "speed_tolerance"):
            if key in src and src.get(key) not in (None, "", {}):
                merged[key] = src[key]
        if not merged.get("original_text"):
            merged["original_text"] = src.get("text") or src.get("original_text") or ""
        if not merged.get("text"):
            merged["text"] = merged.get("original_text") or ""
        out.append(merged)
    return out


def _fill_untranslated(
    originals: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    target_lang: str,
    source_lang: str,
    ping: Callable | None,
) -> list[dict[str, Any]]:
    """Google-fill any line the cinematic pass left in the source language."""
    if not rows or not target_lang:
        return rows
    same_lang = (target_lang or "").strip().lower() == (source_lang or "").strip().lower()
    if same_lang or source_lang in {"", "auto", "Auto Detect"} and target_lang in {"", "auto"}:
        return rows
    missing: list[dict[str, Any]] = []
    by_id = {str(r.get("id")): r for r in rows}
    for src in originals:
        row = by_id.get(str(src.get("id")))
        if row is None:
            missing.append(src)
            continue
        orig = str(src.get("text") or src.get("original_text") or "").strip()
        trans = str(row.get("translated_text") or "").strip()
        if not trans or (len(orig) >= 8 and trans == orig):
            missing.append(src)
    if not missing:
        return rows
    if ping:
        ping(94, f"Filling {len(missing)} untranslated line(s)…")
    try:
        from claynext.models.translate_service import TranslateEngine

        filled = TranslateEngine._translate_google_batched(
            missing, target_lang, source_lang=source_lang,
        )
    except Exception:
        return rows
    filled_by = {str(r.get("id")): r for r in filled}
    out: list[dict[str, Any]] = []
    for row in rows:
        fresh = filled_by.get(str(row.get("id")))
        if not fresh:
            out.append(row)
            continue
        text = str(fresh.get("translated_text") or "").strip()
        orig = str(row.get("original_text") or row.get("text") or "").strip()
        if text and text != orig:
            row = dict(row)
            row["translated_text"] = text
        out.append(row)
    # Lines the first pass dropped entirely.
    have = {str(r.get("id")) for r in out}
    for src in missing:
        key = str(src.get("id"))
        if key in have:
            continue
        fresh = filled_by.get(key)
        if fresh:
            out.append(fresh)
    return out


def translate_movie_dialogue(
    segments: list[dict[str, Any]],
    target_lang: str,
    source_lang: str = "auto",
    *,
    options: MovieTranslateOptions | None = None,
    translator: str = "auto",
    ollama_model: str = "",
    gemini_key: str = "",
    fit_duration: bool = True,
    use_slang: bool = True,
    use_expression: bool = True,
    progress_callback: Callable | None = None,
) -> list[dict[str, Any]]:
    """
    Translate film dialogue for dubbing — cinematic rewrite, cast-aware, slot-fit.
    """
    from claynext.models.translate_service import TranslateEngine

    if not segments:
        raise RuntimeError("No lines to translate.")

    opts = options or MovieTranslateOptions(
        translator=translator,
        ollama_model=ollama_model,
        gemini_key=gemini_key,
        fit_duration=fit_duration,
        use_slang=use_slang,
        use_expression=use_expression,
    )

    pool = get_key_pool()
    if (opts.gemini_key or "").strip():
        try:
            pool.add_key("gemini", opts.gemini_key.strip(), "Session")
        except Exception:
            pass

    # Timing + speech quotas for duration-aware LLM rewrite
    TranslateEngine._ensure_timing(segments, target_lang)

    native = "Khmer (ភាសាខ្មែរ)" if target_lang == "Khmer" else target_lang
    style = {
        "fit_duration": bool(opts.fit_duration),
        "use_slang": bool(opts.use_slang),
        "use_expression": bool(opts.use_expression),
        "movie": True,
    }

    def ping(pct: int, msg: str) -> None:
        if progress_callback:
            progress_callback(pct, msg)

    chain = resolve_movie_engine_chain(
        opts.translator,
        target_lang=target_lang,
        ollama_model=opts.ollama_model,
    )
    if not chain:
        raise RuntimeError("No translation engines available.")

    last_err = "Movie translation failed"
    for i, (label, backend, model) in enumerate(chain):
        ping(4, f"Movie translate · {len(segments)} line(s) → {native} ({label})…")
        try:
            if backend == "gemini":
                rows = TranslateEngine._translate_llm(
                    segments,
                    target_lang,
                    "gemini",
                    "",
                    ping,
                    source_lang=source_lang,
                    style=style,
                )
            elif backend == "ollama":
                rows = TranslateEngine._translate_llm(
                    segments,
                    target_lang,
                    "ollama",
                    model,
                    ping,
                    source_lang=source_lang,
                    style=style,
                )
            elif backend == "nllb":
                rows = TranslateEngine._translate_nllb(
                    segments, target_lang, ping, source_lang=source_lang
                )
            else:
                rows = TranslateEngine._translate_google_batched(
                    segments, target_lang, ping, source_lang=source_lang
                )
            merged = _merge_cast(segments, rows)
            merged = _fill_untranslated(
                segments, merged, target_lang, source_lang, ping,
            )
            ping(100, f"Movie translate ready · {len(merged)} line(s) via {label}")
            return merged
        except Exception as exc:
            last_err = str(exc)
            if i + 1 < len(chain):
                ping(6, f"{label} unavailable ({exc}); trying next engine…")
                continue
            raise RuntimeError(last_err) from exc
    raise RuntimeError(last_err)
