"""CLI: WhisperX diarization → dubbing plan JSON."""
from __future__ import annotations

import argparse


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "plan",
        help="Build WhisperX + diarization dubbing plan JSON",
    )
    p.add_argument("--vocal-file", required=True, help="Demucs isolated vocals WAV")
    p.add_argument("--output-json", default="dubbing_plan.json")
    p.add_argument("--hf-token", default=None, help="HF token (or HF_TOKEN env)")
    p.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    p.add_argument("--model", default="large-v3", help="Whisper model size")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--chunk-size", type=int, default=15, help="Dialogue lines per batch")
    p.add_argument("--min-speakers", type=int, default=None)
    p.add_argument("--max-speakers", type=int, default=None)
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    from claynext.models.dubbing_plan import main as plan_main

    argv = [
        "--vocal-file", args.vocal_file,
        "--output-json", args.output_json,
        "--device", args.device,
        "--model", args.model,
        "--batch-size", str(args.batch_size),
        "--chunk-size", str(args.chunk_size),
    ]
    if args.hf_token:
        argv.extend(["--hf-token", args.hf_token])
    if args.min_speakers is not None:
        argv.extend(["--min-speakers", str(args.min_speakers)])
    if args.max_speakers is not None:
        argv.extend(["--max-speakers", str(args.max_speakers)])
    return int(plan_main(argv))
