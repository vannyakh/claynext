#!/usr/bin/env python3
"""
Demucs vocal stem -> WhisperX transcription -> speaker diarization
-> Khmer dubbing batch JSON.

Usage:
  export HF_TOKEN="hf_..."
  uv run python extract_dubbing_batches.py \\
    --vocal-file ./separated/htdemucs/episode_01/vocals.wav \\
    --output-json ./batches/episode_01_khmer_plan.json \\
    --chunk-size 15 \\
    --device cuda
"""
from claynext.services.dubbing_plan import main

if __name__ == "__main__":
    raise SystemExit(main())
