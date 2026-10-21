"""High-level KSLD milestone helpers for GUI Workers (non-blocking callers)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from claynext.models.khmer_spoken.datasets.gemini_candidate_generator import (
    generate_candidates_batch,
)
from claynext.models.khmer_spoken.datasets.io_store import (
    export_gold_version,
    import_jsonl,
    save_examples,
)
from claynext.models.khmer_spoken.evaluation.khmer_translation_benchmark import run_benchmark
from claynext.models.khmer_spoken.paths import (
    DEFAULT_FIXTURE,
    WORKSPACE_CANDIDATES,
    ensure_khmer_spoken_dirs,
)
from claynext.models.khmer_spoken.providers.google_tts_provider import GeminiTtsProvider
from claynext.models.khmer_spoken.schema import DialogueExample
from claynext.models.khmer_spoken.tts.gemini_voice_registry import default_voice
from claynext.models.khmer_spoken.tts.khmer_pronunciation_evaluator import (
    evaluate_pronunciation_text,
)

ProgressCb = Callable[[int, str], None] | None


def run_milestone_import(path: str | Path | None = None) -> list[DialogueExample]:
    """Import fixture or user JSONL into memory (caller saves workspace)."""
    ensure_khmer_spoken_dirs()
    src = Path(path) if path else DEFAULT_FIXTURE
    return import_jsonl(src)


def load_or_import_workspace(
    path: str | Path | None = None,
) -> list[DialogueExample]:
    ensure_khmer_spoken_dirs()
    if path:
        return import_jsonl(path)
    if WORKSPACE_CANDIDATES.is_file():
        return import_jsonl(WORKSPACE_CANDIDATES)
    return run_milestone_import(DEFAULT_FIXTURE)


def save_workspace(examples: list[DialogueExample], path: Path | None = None) -> Path:
    ensure_khmer_spoken_dirs()
    return save_examples(path or WORKSPACE_CANDIDATES, examples)


def worker_generate_candidates(
    examples: list[DialogueExample] | None = None,
    *,
    limit: int | None = None,
    progress_callback: ProgressCb = None,
) -> dict:
    rows = examples if examples is not None else load_or_import_workspace()
    report = generate_candidates_batch(rows, limit=limit, progress_callback=progress_callback)
    save_workspace(report["examples"])
    return report


def worker_export_gold(
    examples: list[DialogueExample] | None = None,
    *,
    version: str | None = None,
    progress_callback: ProgressCb = None,
) -> dict:
    if progress_callback:
        progress_callback(10, "Validating gold rows…")
    rows = examples if examples is not None else load_or_import_workspace()
    result = export_gold_version(rows, version=version)
    if progress_callback:
        progress_callback(100, f"Exported {result['count']} gold rows")
    return result


def worker_run_eval(
    examples: list[DialogueExample] | None = None,
    *,
    use_gemini_judge: bool = False,
    progress_callback: ProgressCb = None,
) -> dict:
    rows = examples if examples is not None else load_or_import_workspace()
    report = run_benchmark(
        rows, use_gemini_judge=use_gemini_judge, progress_callback=progress_callback
    )
    return report.to_dict()


def worker_tts_preview(
    text: str,
    output_path: str | Path,
    *,
    voice: str | None = None,
    progress_callback: ProgressCb = None,
) -> dict:
    check = evaluate_pronunciation_text(text)
    provider = GeminiTtsProvider()
    result = provider.synthesize_preview(
        text,
        output_path,
        voice=voice or default_voice(),
        progress_callback=progress_callback,
    )
    return {
        "tts": {
            "ok": result.ok,
            "path": result.path,
            "model": result.model,
            "voice": result.voice,
            "skipped": result.skipped,
            "error": result.error,
            "reason": result.reason,
        },
        "pronunciation": check.to_dict(),
    }
