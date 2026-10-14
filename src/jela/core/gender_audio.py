"""
Audio gender classification for dubbing ASR analysis.

Uses Hugging Face ``prithivMLmods/Common-Voice-Gender-Detection``
(wav2vec2 sequence classification: female / male) on dialogue clips.
Falls back silently when torch / transformers weights are unavailable.
"""
from __future__ import annotations

import os
import threading
import wave
from pathlib import Path
from typing import Any, Callable

import numpy as np

MODEL_ID = "prithivMLmods/Common-Voice-Gender-Detection"
_SAMPLE_RATE = 16000
_MAX_CLIPS_PER_CHAR = 3
_MIN_CLIP_SEC = 0.35
_MAX_CLIP_SEC = 8.0

_lock = threading.Lock()
_model = None
_processor = None
_load_error: str | None = None

Ping = Callable[[int, str], None] | None


def gender_model_available() -> bool:
    """True when torch + transformers can load the classifier."""
    try:
        import torch  # noqa: F401
        from transformers import (  # noqa: F401
            Wav2Vec2FeatureExtractor,
            Wav2Vec2ForSequenceClassification,
        )
        return True
    except Exception:
        return False


def _model_dir() -> Path | None:
    try:
        from jela.core.hf_hub import get_local_model_path, is_model_downloaded, pull_model

        if not is_model_downloaded(MODEL_ID):
            pull_model(MODEL_ID)
        path = get_local_model_path(MODEL_ID)
        return Path(path) if path else None
    except Exception:
        return None


def _ensure_model():
    global _model, _processor, _load_error
    with _lock:
        if _model is not None and _processor is not None:
            return _model, _processor
        if _load_error:
            raise RuntimeError(_load_error)
        try:
            import torch
            from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForSequenceClassification

            local = _model_dir()
            source = str(local) if local and local.is_dir() else MODEL_ID
            _processor = Wav2Vec2FeatureExtractor.from_pretrained(source)
            _model = Wav2Vec2ForSequenceClassification.from_pretrained(source)
            _model.eval()
            if torch.cuda.is_available():
                _model = _model.to("cuda")
            return _model, _processor
        except Exception as exc:
            _load_error = str(exc)
            raise RuntimeError(_load_error) from exc


def _extract_clip(src: str, start: float, end: float, dst: Path) -> bool:
    from jela.core.ffmpeg_tools import run_ffmpeg

    start = max(0.0, float(start))
    end = max(start + _MIN_CLIP_SEC, float(end))
    if end - start > _MAX_CLIP_SEC:
        mid = (start + end) / 2.0
        start = mid - _MAX_CLIP_SEC / 2.0
        end = start + _MAX_CLIP_SEC
    dst.parent.mkdir(parents=True, exist_ok=True)
    proc = run_ffmpeg(
        [
            "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
            "-i", src, "-vn", "-ac", "1", "-ar", str(_SAMPLE_RATE),
            "-c:a", "pcm_s16le", str(dst),
        ],
        timeout=120,
    )
    return proc.returncode == 0 and dst.is_file() and dst.stat().st_size > 44


def _read_pcm16(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    if data.size == 0:
        return data
    peak = float(np.max(np.abs(data))) or 1.0
    return data / peak


def classify_audio_file(path: str) -> tuple[str, float]:
    """
    Classify a mono/stereo audio file.

    Returns ``(Female|Male|Unknown, confidence 0..1)``.
    """
    if not path or not os.path.isfile(path):
        return "Unknown", 0.0
    model, processor = _ensure_model()
    import torch

    # Resample via ffmpeg scratch if needed.
    tmp = Path(path)
    if tmp.suffix.lower() != ".wav":
        scratch = tmp.with_suffix(".gender16k.wav")
        if not _extract_clip(path, 0.0, _MAX_CLIP_SEC, scratch):
            return "Unknown", 0.0
        speech = _read_pcm16(scratch)
        scratch.unlink(missing_ok=True)
    else:
        speech = _read_pcm16(tmp)
        # Re-encode if not 16 kHz mono.
        try:
            with wave.open(str(tmp), "rb") as wf:
                rate, ch = wf.getframerate(), wf.getnchannels()
        except Exception:
            rate, ch = 0, 0
        if rate != _SAMPLE_RATE or ch != 1:
            scratch = tmp.with_name(tmp.stem + "_g16k.wav")
            if not _extract_clip(str(tmp), 0.0, _MAX_CLIP_SEC, scratch):
                return "Unknown", 0.0
            speech = _read_pcm16(scratch)
            scratch.unlink(missing_ok=True)

    if speech.size < int(_SAMPLE_RATE * _MIN_CLIP_SEC):
        return "Unknown", 0.0

    inputs = processor(speech, sampling_rate=_SAMPLE_RATE, return_tensors="pt", padding=True)
    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        logits = model(**inputs).logits
        probs = torch.nn.functional.softmax(logits, dim=-1).squeeze()
        if probs.ndim == 0:
            return "Unknown", 0.0
        idx = int(torch.argmax(probs).item())
        conf = float(probs[idx].item())

    id2label = getattr(model.config, "id2label", None) or {0: "female", 1: "male"}
    label = str(id2label.get(idx, id2label.get(str(idx), "unknown"))).lower()
    if "female" in label or label == "f":
        return "Female", conf
    if "male" in label or label == "m":
        return "Male", conf
    return "Unknown", conf


def _seg_times(seg: dict[str, Any]) -> tuple[float, float]:
    from jela.core.dubbing_engine import timestamp_to_sec

    start = seg.get("start_sec")
    end = seg.get("end_sec")
    if isinstance(start, (int, float)) and isinstance(end, (int, float)):
        return float(start), float(end)
    return timestamp_to_sec(seg.get("start", "")), timestamp_to_sec(seg.get("end", ""))


def enrich_segments_with_audio_gender(
    segments: list[dict[str, Any]],
    audio_path: str,
    *,
    work_dir: str | Path | None = None,
    progress_callback: Ping = None,
    min_confidence: float = 0.55,
) -> list[dict[str, Any]]:
    """
    Run wav2vec2 gender detection on a few clips per character.

    Sets ``audio_gender``, ``audio_gender_confidence``, and fills ``gender``
    when not manually locked.
    """
    if not segments or not audio_path or not os.path.isfile(audio_path):
        return segments
    if not gender_model_available():
        return segments

    try:
        _ensure_model()
    except Exception:
        return segments

    root = Path(work_dir or Path(audio_path).parent / ".gender")
    root.mkdir(parents=True, exist_ok=True)

    # Group indices by speaker; pick longest clips for sampling.
    by_char: dict[str, list[int]] = {}
    for i, seg in enumerate(segments):
        name = str(seg.get("speaker") or "").strip() or "Character 1"
        by_char.setdefault(name, []).append(i)

    total = max(1, len(by_char))
    done = 0
    for name, indices in by_char.items():
        ranked = sorted(
            indices,
            key=lambda i: max(0.0, _seg_times(segments[i])[1] - _seg_times(segments[i])[0]),
            reverse=True,
        )[:_MAX_CLIPS_PER_CHAR]
        votes: list[tuple[str, float]] = []
        for j, idx in enumerate(ranked):
            seg = segments[idx]
            if seg.get("gender_manual"):
                continue
            start, end = _seg_times(seg)
            if end - start < _MIN_CLIP_SEC:
                continue
            clip = root / f"{name.replace(' ', '_')}_{idx}_{j}.wav"
            if not _extract_clip(audio_path, start, end, clip):
                continue
            try:
                gender, conf = classify_audio_file(str(clip))
            except Exception:
                gender, conf = "Unknown", 0.0
            finally:
                clip.unlink(missing_ok=True)
            if gender != "Unknown" and conf >= min_confidence:
                votes.append((gender, conf))
                seg["audio_gender"] = gender
                seg["audio_gender_confidence"] = round(conf, 3)

        if votes:
            # Confidence-weighted majority.
            scores = {"Female": 0.0, "Male": 0.0}
            for g, c in votes:
                scores[g] = scores.get(g, 0.0) + c
            winner = max(scores, key=scores.get)
            if scores[winner] > 0:
                for idx in indices:
                    seg = segments[idx]
                    if seg.get("gender_manual"):
                        continue
                    seg["audio_gender"] = winner
                    seg["gender"] = winner
                    seg["gender_source"] = "audio"

        done += 1
        if progress_callback:
            progress_callback(
                20 + int(60 * done / total),
                f"Audio gender · {name} ({done}/{total})",
            )

    return segments
