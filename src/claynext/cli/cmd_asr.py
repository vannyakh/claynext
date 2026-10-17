"""CLI: speech recognition → SRT / VTT / JSON."""
from __future__ import annotations

import argparse
from pathlib import Path

from claynext.cli.common import die, make_progress, require_file, save_segments


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("asr", help="Transcribe video/audio to SRT/VTT/JSON")
    p.add_argument("media", help="Input video or audio file")
    p.add_argument(
        "-o", "--output",
        help="Output path (.srt / .vtt / .json). Default: <media>.srt",
    )
    p.add_argument("--model", default="whisper-small", help="ASR model id")
    p.add_argument("--lang", default="Auto Detect", help="Spoken language hint")
    p.add_argument("--device", default="auto", help="Compute device (auto/cpu/cuda)")
    p.add_argument("--format", choices=["srt", "vtt", "json"], help="Force export format")
    p.add_argument("-q", "--quiet", action="store_true", help="Hide progress")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    from claynext.models.asr_service import ASREngine

    media = require_file(args.media, label="media")
    out = Path(args.output) if args.output else media.with_suffix(".srt")
    progress = make_progress(args.quiet)
    try:
        segments = ASREngine.transcribe(
            str(media),
            model_name=args.model,
            language=args.lang,
            compute_device=args.device,
            progress_callback=progress,
        )
    except Exception as exc:
        die(str(exc))
    path = save_segments(out, segments, fmt=args.format)
    print(path)
    return 0
