"""Offline evaluation harness for Khmer TTS fixtures."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claynext.voice_training.datasets.dataset_builder import load_dataset
from claynext.voice_training.evaluation.intelligibility import score_intelligibility
from claynext.voice_training.evaluation.naturalness import score_naturalness
from claynext.voice_training.evaluation.speaker_consistency import score_speaker_consistency


def run_evaluation(
    dataset_path: str | Path,
    *,
    hypotheses: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Evaluate a speech dataset offline.

    ``hypotheses`` maps segment_id → synthesized/transcript hypothesis text.
    When omitted, uses ``tts_pronunciation`` or ``transcript_spoken`` as both
    ref and hyp (self-consistency smoke check for fixtures).
    """
    dataset = load_dataset(dataset_path)
    hyps = hypotheses or {}
    intel_scores: list[float] = []
    nat_scores: list[float] = []
    per_segment: list[dict[str, Any]] = []

    for seg in dataset.segments:
        ref = seg.transcript_display or seg.transcript_spoken or seg.tts_pronunciation
        hyp = hyps.get(seg.segment_id) or seg.tts_pronunciation or seg.transcript_spoken or ref
        intel = score_intelligibility(ref, hyp)
        nat = score_naturalness(
            quality_score=seg.quality_score,
            duration_sec=max(0.0, seg.end_sec - seg.start_sec),
            has_transcript=bool(ref),
        )
        intel_scores.append(float(intel["score"]))
        nat_scores.append(float(nat["score"]))
        per_segment.append({
            "segment_id": seg.segment_id,
            "intelligibility": intel,
            "naturalness": nat,
        })

    speaker = score_speaker_consistency([s.speaker_id for s in dataset.segments])
    summary = {
        "dataset_id": dataset.dataset_id,
        "segments": len(dataset.segments),
        "intelligibility_mean": round(sum(intel_scores) / max(len(intel_scores), 1), 4),
        "naturalness_mean": round(sum(nat_scores) / max(len(nat_scores), 1), 4),
        "speaker_consistency": speaker,
        "per_segment": per_segment,
    }
    return summary


def write_evaluation_report(summary: dict[str, Any], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p
