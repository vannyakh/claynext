"""Capped raw probes. Not a gold benchmark.

Stops on HTTP 503 or when no key is free. Does not retry for hours.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claynext.models.benchmarks.prompt import PROMPT_VERSION, translation_prompt
from claynext.models.benchmarks.providers import redact_provider_error
from claynext.models.benchmarks.runner import PROBE_ROW_CAP, run_benchmark
from claynext.models.benchmarks.schema import BenchmarkRow

OLLAMA_CANDIDATES = ("aya-expanse:8b", "qwen2.5:7b", "qwen3:8b")
PENDING_CASE_LIMIT = 8


def pending_pronoun_rows(limit: int = PENDING_CASE_LIMIT) -> list[BenchmarkRow]:
    """Draft pronoun cases for a raw probe. They are not gold and are not scored.

    Spoken Gemini drafts under ``data/khmer_spoken/`` are not loaded here.
    """
    from claynext.prompts.loader import EVALUATIONS_DIR, load_jsonl

    if limit > PROBE_ROW_CAP:
        raise ValueError(f"probe cap is {PROBE_ROW_CAP} rows")
    rows: list[BenchmarkRow] = []
    for case in load_jsonl(EVALUATIONS_DIR / "khmer_pronoun_cases.jsonl"):
        review = case.get("review") or {}
        if review.get("status") in {"gold", "reviewed"}:
            continue
        scene = str((case.get("scene") or {}).get("id") or case.get("id") or "")
        rows.append(BenchmarkRow(
            id=str(case.get("id") or ""),
            scene_id=scene,
            dialogue_family_id=scene,
            source_language=str(case.get("source_language") or "en"),
            source_text=str(case.get("source_text") or ""),
            reference_khmer="",
            split="test",
            licence="unknown",
            review_status="pending_native_review",
            origin="human_authored",
            dataset_version="khmer-pronoun-cases-pending",
            locked=True,
            synthetic_only=False,
        ))
        if len(rows) >= limit:
            break
    return rows


def assert_probe_cap(rows: list[BenchmarkRow]) -> None:
    if len(rows) > PROBE_ROW_CAP:
        raise ValueError(f"probe cap is {PROBE_ROW_CAP} rows")


def provider_ready(provider_id: str) -> bool:
    """True when the key pool has a usable key. Does not return the secret."""
    from claynext.models.llm_keys import get_key_pool

    return get_key_pool().ready_count(provider_id) > 0


def gemini_once(prompt: str, *, model: str = "gemini-flash-latest", temperature: float = 0.0) -> dict[str, Any]:
    """One generateContent call. No cooldown sleep. Stops on 503."""
    import urllib.error
    import urllib.parse
    import urllib.request

    from claynext.models.llm_keys import (
        InvalidKeyError,
        RateLimitError,
        get_key_pool,
        is_rate_limit,
        note_llm_usage,
    )

    if not provider_ready("gemini"):
        return {"ok": False, "stop": True, "error": "no free key", "text": ""}

    def _do(api_key: str) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={urllib.parse.quote(api_key)}"
        )
        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = json.loads(response.read().decode("utf-8"))
            note_llm_usage(model, raw)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise InvalidKeyError(f"{model}: {exc.code}") from exc
            if exc.code == 503:
                raise RuntimeError("503") from exc
            if is_rate_limit(exc.code, ""):
                raise RateLimitError(f"{model}: rate limited", None) from exc
            raise RuntimeError(f"http {exc.code}") from exc
        return (
            raw.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )

    try:
        text = get_key_pool().call_with_rotation(
            "gemini", _do, max_cooldown_waits=0, max_wait=0,
        )
    except RuntimeError as exc:
        message = redact_provider_error(str(exc))
        stop = message == "503" or "no available" in message.lower() or "rate-limited" in message.lower()
        return {"ok": False, "stop": stop or message == "503", "error": message, "text": ""}
    except Exception as exc:
        return {
            "ok": False,
            "stop": True,
            "error": redact_provider_error(str(exc)),
            "text": "",
        }
    return {"ok": True, "stop": False, "error": "", "text": text}


def run_gemini_raw_probe(
    rows: list[BenchmarkRow],
    *,
    out_dir: str | Path,
    model: str = "gemini-flash-latest",
) -> dict[str, Any]:
    """Record raw Gemini text. Labelled not a gold benchmark. Stops on the first hard error."""
    assert_probe_cap(rows)
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, Any]] = []
    stopped = ""
    for row in rows:
        result = gemini_once(translation_prompt(row), model=model, temperature=0.0)
        if not result["ok"]:
            stopped = result["error"] or "provider error"
            outputs.append({
                "id": row.id, "ok": False, "error": stopped, "text": "", "source_text": row.source_text,
            })
            break
        outputs.append({
            "id": row.id, "ok": True, "error": "", "text": result["text"], "source_text": row.source_text,
        })
    report = {
        "synthetic_fixture": False,
        "not_a_gold_benchmark": True,
        "quality_score": None,
        "prompt_version": PROMPT_VERSION,
        "decoding": {"temperature": 0, "prompt_version": PROMPT_VERSION},
        "provider_label": "gemini",
        "model_id": model,
        "n_requested": len(rows),
        "n_completed": sum(1 for row in outputs if row["ok"]),
        "stopped_error": stopped or None,
        "outputs": outputs,
        "note": (
            "Raw provider text only. Rows are not a locked human-reviewed gold set. "
            "This file is not a quality score and not a comparison against GPT."
        ),
    }
    path = folder / "gemini-raw-probe.json"
    path.write_text(
        redact_provider_error(json.dumps(report, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    report["path"] = str(path)
    return report


def ollama_inventory() -> dict[str, Any]:
    """Names already installed. Does not pull weights."""
    from claynext.models.translate_service import TranslateEngine

    available, names = TranslateEngine.get_ollama_model_names()
    present = [name for name in OLLAMA_CANDIDATES if name in set(names)]
    return {"running": available, "installed_candidates": present, "pulled": False}


def run_ollama_raw_probe(
    rows: list[BenchmarkRow],
    *,
    model_id: str,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Untuned local generation for a model that is already installed. Stops on the first error."""
    import json as json_mod
    import urllib.error
    import urllib.request

    from claynext.models.translate_service import TranslateEngine

    assert_probe_cap(rows)
    inventory = ollama_inventory()
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    if not inventory["running"] or model_id not in inventory["installed_candidates"]:
        report = {
            "synthetic_fixture": False,
            "not_a_gold_benchmark": True,
            "quality_score": None,
            "provider_label": "ollama",
            "model_id": model_id,
            "n_completed": 0,
            "stopped_error": "ollama is not running or the model is not installed",
            "inventory": inventory,
            "outputs": [],
        }
        path = folder / "ollama-raw-probe.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["path"] = str(path)
        return report

    host = TranslateEngine.ollama_host()
    outputs: list[dict[str, Any]] = []
    stopped = ""
    for row in rows:
        body = json_mod.dumps({
            "model": model_id,
            "prompt": translation_prompt(row),
            "stream": False,
            "options": {"temperature": 0, "num_predict": 128},
        }).encode("utf-8")
        request = urllib.request.Request(
            host + "/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = json_mod.loads(response.read().decode("utf-8"))
            text = str(raw.get("response") or "").strip()
            outputs.append({"id": row.id, "ok": True, "error": "", "text": text})
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            stopped = redact_provider_error(str(exc))
            outputs.append({"id": row.id, "ok": False, "error": stopped, "text": ""})
            break
    report = {
        "synthetic_fixture": False,
        "not_a_gold_benchmark": True,
        "quality_score": None,
        "prompt_version": PROMPT_VERSION,
        "decoding": {"temperature": 0, "num_predict": 128},
        "provider_label": "ollama",
        "model_id": model_id,
        "n_requested": len(rows),
        "n_completed": sum(1 for row in outputs if row["ok"]),
        "stopped_error": stopped or None,
        "outputs": outputs,
        "note": "Untuned local raw text. Not a gold score and not a win over a hosted model.",
    }
    path = folder / "ollama-raw-probe.json"
    path.write_text(
        redact_provider_error(json.dumps(report, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    report["path"] = str(path)
    return report


def run_callable_report(rows: list[BenchmarkRow], translate, **kwargs: Any) -> dict[str, Any]:
    """Test and fixture entry. Live probes use the raw probe functions above."""
    return run_benchmark(rows, translate, hosted_probe=True, **kwargs)
