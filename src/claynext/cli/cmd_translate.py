"""CLI: translate subtitle / script segments."""
from __future__ import annotations

import argparse
from pathlib import Path

from claynext.cli.common import die, load_segments, make_progress, save_segments


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("translate", help="Translate SRT / VTT / JSON lines")
    p.add_argument("input", help="Input .srt / .vtt / .json")
    p.add_argument("--target-lang", required=True, help="Target language (e.g. Khmer, English)")
    p.add_argument("--source-lang", default="auto", help="Source language hint")
    p.add_argument(
        "--translator",
        default="auto",
        choices=["auto", "gemini", "ollama", "nllb", "google"],
        help="Translation backend",
    )
    p.add_argument("--ollama-model", default="qwen2.5:7b", help="Ollama model when --translator ollama")
    p.add_argument(
        "-o", "--output",
        help="Output path. Default: <input>.<lang>.srt (or same suffix)",
    )
    p.add_argument("--format", choices=["srt", "vtt", "json"], help="Force export format")
    p.add_argument("-q", "--quiet", action="store_true", help="Hide progress")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    from claynext.models.translate_service import TranslateEngine

    rows = load_segments(args.input)
    progress = make_progress(args.quiet)
    try:
        translated = TranslateEngine.translate_subtitles(
            rows,
            target_lang=args.target_lang,
            source_lang=args.source_lang,
            translator=args.translator,
            ollama_model=args.ollama_model,
            progress_callback=progress,
        )
    except Exception as exc:
        die(str(exc))

    src = Path(args.input)
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in args.target_lang).strip("-")
    out = Path(args.output) if args.output else src.with_name(f"{src.stem}.{slug}{src.suffix or '.srt'}")
    path = save_segments(out, translated, fmt=args.format)
    print(path)
    return 0
