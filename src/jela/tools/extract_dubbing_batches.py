"""CLI: python -m jela.tools.extract_dubbing_batches --vocal-file vocals.wav"""
from __future__ import annotations

import argparse
import os

from jela.core.dubbing_plan import hf_token as resolve_hf_token
from jela.core.dubbing_plan import run_pipeline
from jela.utils.logging import configure_logging

__all__ = ["main", "run_pipeline"]


def main(argv: list[str] | None = None) -> int:
    logger = configure_logging("jela.dub_plan")
    parser = argparse.ArgumentParser(
        description="Movie dialogue diarizer and Khmer dubbing batch generator"
    )
    parser.add_argument("--vocal-file", required=True, help="Demucs isolated vocals WAV")
    parser.add_argument("--output-json", default="dubbing_plan.json")
    parser.add_argument("--hf-token", default=os.getenv("HF_TOKEN"))
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--model", default="large-v3", help="Whisper model size")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--chunk-size", type=int, default=15, help="Dialogue lines per batch")
    parser.add_argument("--min-speakers", type=int, default=None)
    parser.add_argument("--max-speakers", type=int, default=None)
    args = parser.parse_args(argv)

    token = resolve_hf_token(args.hf_token or "")
    if not token:
        logger.error("Hugging Face token required. Set HF_TOKEN, save a key, or pass --hf-token.")
        return 1

    run_pipeline(
        vocal_audio_path=args.vocal_file,
        output_json_path=args.output_json,
        hf_token=token,
        device=args.device,
        whisper_model_name=args.model,
        batch_size=args.batch_size,
        min_speakers=args.min_speakers,
        max_speakers=args.max_speakers,
        batch_chunk_size=args.chunk_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
