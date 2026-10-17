"""CLI: text-to-speech synthesis."""
from __future__ import annotations

import argparse
from pathlib import Path

from claynext.cli.common import die, ensure_parent, make_progress, require_file
from claynext.utils.config import OUTPUTS_DIR


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("tts", help="Synthesize speech from text")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="Text to speak")
    src.add_argument("--file", metavar="PATH", help="UTF-8 text file to speak")
    p.add_argument("--voice", required=True, help="Voice id (e.g. en-US-AvaNeural)")
    p.add_argument(
        "-o", "--output",
        help="Output audio path (.mp3 / .wav). Default under data/outputs/",
    )
    p.add_argument("--speed", type=float, default=1.0, help="Speaking rate")
    p.add_argument("--pitch", type=float, default=0.0, help="Pitch offset")
    p.add_argument("-q", "--quiet", action="store_true", help="Hide progress")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    from claynext.models.tts_service import TTSEngine

    if args.text is not None:
        text = str(args.text)
    else:
        path = require_file(args.file, label="text file")
        text = path.read_text(encoding="utf-8")
    text = text.strip()
    if not text:
        die("empty text")

    out = Path(args.output) if args.output else Path(OUTPUTS_DIR) / "cli_tts.mp3"
    ensure_parent(out)
    progress = make_progress(args.quiet)
    try:
        written = TTSEngine.synthesize(
            text,
            args.voice,
            str(out),
            speed=float(args.speed),
            pitch=float(args.pitch),
            progress_callback=progress,
        )
    except Exception as exc:
        die(str(exc))
    print(written or out)
    return 0
