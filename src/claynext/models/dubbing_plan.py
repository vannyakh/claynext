"""
Demucs vocal stem → WhisperX ASR → forced alignment → PyAnnote diarization
→ Khmer dubbing batch JSON.

Optional extra: `uv add whisperx torch torchaudio`
Requires HF_TOKEN and accepting pyannote/speaker-diarization-3.1.
"""
from __future__ import annotations

import gc
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("claynext.dubbing_plan")


def estimate_khmer_syllable_quota(duration_sec: float) -> dict[str, int]:
    dur = max(0.0, float(duration_sec))
    target = int(dur * 3.5)
    return {
        "min": max(1, int(dur * 2.8)),
        "target": max(1, target),
        "max": max(2, int(dur * 4.2)),
    }


def whisperx_available() -> bool:
    try:
        import whisperx  # noqa: F401
        return True
    except Exception:
        return False


def hf_token(explicit: str = "") -> str:
    if (explicit or "").strip():
        return explicit.strip()
    from claynext.models.llm_keys import get_key_pool
    keys = get_key_pool().secrets("huggingface")
    return keys[0] if keys else ""


def _device(requested: str) -> str:
    req = (requested or "cuda").lower()
    if req != "cuda":
        return "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    logger.warning("CUDA requested but not found. Falling back to CPU.")
    return "cpu"


def _fmt_ts(seconds: float) -> str:
    ms = int(round(max(0.0, float(seconds)) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def build_dubbing_plan(
    vocal_audio_path: str,
    hf_token_value: str,
    *,
    device: str = "cuda",
    whisper_model_name: str = "large-v3",
    batch_size: int = 16,
    compute_type: str = "float16",
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    batch_chunk_size: int = 15,
    progress_callback: Callable | None = None,
) -> dict[str, Any]:
    if not os.path.isfile(vocal_audio_path):
        raise FileNotFoundError(f"Vocal stem audio not found: {vocal_audio_path}")
    token = hf_token(hf_token_value)
    if not token:
        raise RuntimeError("Hugging Face token required for PyAnnote. Set HF_TOKEN or pass hf_token.")

    try:
        import whisperx
        from whisperx.diarize import DiarizationPipeline
    except ImportError as exc:
        raise RuntimeError(
            "WhisperX is not installed. Run: uv add whisperx torch torchaudio"
        ) from exc

    def ping(pct: int, msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(pct, msg)

    device = _device(device)
    if device == "cpu" and compute_type == "float16":
        compute_type = "int8"

    ping(8, f"Loading vocal stem · {os.path.basename(vocal_audio_path)}")
    audio = whisperx.load_audio(vocal_audio_path)

    ping(12, f"WhisperX {whisper_model_name} on {device} ({compute_type})…")
    asr_model = whisperx.load_model(whisper_model_name, device, compute_type=compute_type)
    ping(20, "Transcribing vocal stem…")
    transcription_result = asr_model.transcribe(audio, batch_size=batch_size)
    detected_lang = transcription_result.get("language", "en")
    del asr_model
    gc.collect()
    try:
        import torch
        if device == "cuda":
            torch.cuda.empty_cache()
    except Exception:
        pass

    ping(45, f"Forced alignment ({detected_lang})…")
    try:
        align_model, align_metadata = whisperx.load_align_model(
            language_code=detected_lang, device=device
        )
        aligned_result = whisperx.align(
            transcription_result["segments"],
            align_model,
            align_metadata,
            audio,
            device,
            return_char_alignments=False,
        )
        del align_model
        gc.collect()
        try:
            import torch
            if device == "cuda":
                torch.cuda.empty_cache()
        except Exception:
            pass
    except Exception as exc:
        logger.warning("Forced alignment skipped: %s", exc)
        aligned_result = transcription_result

    ping(62, "PyAnnote speaker diarization…")
    diarize_model = DiarizationPipeline(use_auth_token=token, device=device)
    diarize_segments = diarize_model(
        audio,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )
    final_result = whisperx.assign_word_speakers(diarize_segments, aligned_result)
    del diarize_model
    gc.collect()

    ping(82, "Building Khmer dubbing batches…")
    cleaned: list[dict[str, Any]] = []
    for idx, seg in enumerate(final_result.get("segments") or []):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = round(float(seg["start"]), 3)
        end = round(float(seg["end"]), 3)
        duration = round(end - start, 3)
        if duration < 0.15:
            continue
        speaker = seg.get("speaker") or "UNKNOWN_SPEAKER"
        cleaned.append({
            "segment_id": f"seg_{idx:04d}",
            "speaker": speaker,
            "tts_voice_hint": "",
            "timeline": {
                "start_sec": start,
                "end_sec": end,
                "duration_sec": duration,
                "start_ms": int(start * 1000),
                "end_ms": int(end * 1000),
            },
            "source_dialogue": {
                "language": detected_lang,
                "text": text,
            },
            "khmer_localization_constraints": {
                "target_language": "km-KH",
                "recommended_syllables": estimate_khmer_syllable_quota(duration),
                "speed_tolerance": {"min_rate": 0.85, "max_rate": 1.20},
            },
        })

    chunk = max(1, int(batch_chunk_size))
    batches = []
    for b_idx in range(0, len(cleaned), chunk):
        group = cleaned[b_idx:b_idx + chunk]
        batches.append({
            "batch_index": b_idx // chunk + 1,
            "segment_count": len(group),
            "batch_start_sec": group[0]["timeline"]["start_sec"],
            "batch_end_sec": group[-1]["timeline"]["end_sec"],
            "segments": group,
        })

    payload = {
        "metadata": {
            "source_audio_file": os.path.basename(vocal_audio_path),
            "source_language": detected_lang,
            "total_dialogue_segments": len(cleaned),
            "total_batches": len(batches),
            "batch_size_setting": chunk,
        },
        "batches": batches,
    }
    ping(100, f"Plan ready · {len(cleaned)} lines · {len(batches)} batches")
    return payload


def save_plan(payload: dict[str, Any], output_json_path: str) -> str:
    path = Path(output_json_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def plan_to_segments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten dubbing_plan.json batches into engine segment rows."""
    rows: list[dict[str, Any]] = []
    seq = 1
    for batch in payload.get("batches") or []:
        for seg in batch.get("segments") or []:
            tl = seg.get("timeline") or {}
            src = seg.get("source_dialogue") or {}
            constraints = seg.get("khmer_localization_constraints") or {}
            start = float(tl.get("start_sec") or 0)
            end = float(tl.get("end_sec") or 0)
            rows.append({
                "id": seq,
                "segment_id": seg.get("segment_id") or f"seg_{seq:04d}",
                "start": _fmt_ts(start),
                "end": _fmt_ts(end),
                "start_sec": start,
                "end_sec": end,
                "speaker": seg.get("speaker") or "",
                "text": (src.get("text") or "").strip(),
                "tts_voice_hint": seg.get("tts_voice_hint") or "",
                "language": src.get("language") or "",
                "recommended_syllables": constraints.get("recommended_syllables") or {},
                "speed_tolerance": constraints.get("speed_tolerance") or {},
            })
            seq += 1
    return rows


def run_pipeline(
    vocal_audio_path: str,
    output_json_path: str,
    hf_token: str,
    device: str = "cuda",
    whisper_model_name: str = "large-v3",
    batch_size: int = 16,
    compute_type: str = "float16",
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    batch_chunk_size: int = 15,
) -> dict[str, Any]:
    """WhisperX + PyAnnote planner; writes dubbing_plan.json and returns the payload."""
    payload = build_dubbing_plan(
        vocal_audio_path,
        hf_token,
        device=device,
        whisper_model_name=whisper_model_name,
        batch_size=batch_size,
        compute_type=compute_type,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        batch_chunk_size=batch_chunk_size,
    )
    save_plan(payload, output_json_path)
    logger.info(
        "Successfully processed %s lines into %s batches.",
        payload["metadata"]["total_dialogue_segments"],
        payload["metadata"]["total_batches"],
    )
    logger.info("Saved dubbing plan JSON to: %s", output_json_path)
    return payload


def main(argv: list[str] | None = None) -> int:
    import argparse
    from claynext.utils.logging import configure_logging
    cli_logger = configure_logging("claynext.dub_plan")
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

    token = hf_token(args.hf_token or "")
    if not token:
        cli_logger.error("Hugging Face token required. Set HF_TOKEN, save a key, or pass --hf-token.")
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

