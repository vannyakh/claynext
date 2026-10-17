"""CLI: full movie dubbing pipeline (ASR → translate → TTS → mux)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from claynext.cli.common import die, make_progress, require_file, save_segments
from claynext.utils.config import OUTPUTS_DIR


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("dub", help="Dub a movie (ASR -> translate -> TTS -> mux)")
    p.add_argument("video", help="Input video file")
    p.add_argument("-o", "--output", help="Output dubbed MP4 path")
    p.add_argument("--source-lang", default="Chinese", help="Spoken source language")
    p.add_argument("--target-lang", default="Khmer", help="Dub language")
    p.add_argument("--voice", default="km-KH-SreymomNeural", help="Primary TTS voice id")
    p.add_argument("--voice2", default="", help="Secondary TTS voice id")
    p.add_argument("--asr-model", default="whisper-small", help="ASR model id")
    p.add_argument(
        "--translator",
        default="auto",
        choices=["auto", "gemini", "ollama", "nllb", "google"],
        help="Translation backend",
    )
    p.add_argument("--ollama-model", default="qwen2.5:7b")
    p.add_argument("--bg", type=float, default=0.15, help="Background duck level 0-1")
    p.add_argument(
        "--sync",
        default="stretch",
        choices=["stretch", "subtle", "natural"],
        help="Line duration fit mode",
    )
    p.add_argument(
        "--no-chain",
        action="store_true",
        help="Skip translate/cast; speak original lines with lead voice",
    )
    p.add_argument(
        "--timeline-only",
        action="store_true",
        help="Skip final mux (return segments + bed like Studio)",
    )
    p.add_argument(
        "--export-script",
        metavar="PATH",
        help="Also write dubbed segments (.srt / .json)",
    )
    p.add_argument("--hf-token", default="", help="Hugging Face token (WhisperX)")
    p.add_argument("--no-fit", action="store_true", help="Disable TTS duration fit in translate")
    p.add_argument("--no-slang", action="store_true", help="Disable slang/idiom in translate")
    p.add_argument("--no-expression", action="store_true", help="Disable expression tags in translate")
    p.add_argument("-q", "--quiet", action="store_true", help="Hide progress")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    from claynext.models.dubbing_service import DubbingEngine

    video = require_file(args.video, label="video")
    progress = make_progress(args.quiet)
    out = args.output
    if not out and not args.timeline_only:
        slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in args.target_lang).strip("-")
        out = str(Path(OUTPUTS_DIR) / f"{video.stem}_dub_{slug}.mp4")

    try:
        result = DubbingEngine.process_dubbing(
            video_path=str(video),
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            voice_id=args.voice,
            secondary_voice_id=args.voice2 or args.voice,
            background_vol=float(args.bg),
            output_path=out,
            asr_model=args.asr_model,
            asr_language=args.source_lang,
            translator=args.translator,
            ollama_model=args.ollama_model,
            hf_token=args.hf_token or "",
            sync_mode=args.sync,
            auto_chain=not args.no_chain,
            render=not args.timeline_only,
            translate_fit_duration=not args.no_fit,
            translate_slang=not args.no_slang,
            translate_expression=not args.no_expression,
            progress_callback=progress,
        )
    except Exception as exc:
        die(str(exc))

    if args.export_script:
        segs = result.get("segments") or []
        save_segments(args.export_script, segs)

    # Machine-readable summary on stdout
    summary = {
        "output_path": result.get("output_path") or "",
        "bed_path": result.get("bed_path") or "",
        "segments_dubbed": result.get("segments_dubbed"),
        "source_language": result.get("source_language"),
        "target_language": result.get("target_language"),
        "voice_used": result.get("voice_used"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0
