"""Build and persist speech datasets; assign train/val/test by session/source."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from claynext.voice_training.datasets.speech_schema import SpeechDataset, SpeechSegment

Split = Literal["train", "val", "test"]


def load_dataset(path: str | Path) -> SpeechDataset:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return SpeechDataset.from_dict(data)


def save_dataset(dataset: SpeechDataset, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dataset.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def write_segments_jsonl(segments: list[SpeechSegment], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for seg in segments:
            fh.write(json.dumps(seg.to_dict(), ensure_ascii=False) + "\n")
    return p


def read_segments_jsonl(path: str | Path) -> list[SpeechSegment]:
    rows: list[SpeechSegment] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(SpeechSegment.from_dict(json.loads(line)))
    return rows


def assign_splits(
    dataset: SpeechDataset,
    *,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    group_by: Literal["session", "source"] = "session",
    seed: int = 42,
) -> SpeechDataset:
    """
    Assign train/val/test so that all segments from one session (or source)
    share the same split — prevents leakage across folds.
    """
    import hashlib

    groups: dict[str, list[SpeechSegment]] = {}
    for seg in dataset.segments:
        key = seg.session_id if group_by == "session" else seg.source_id
        key = key or seg.segment_id
        groups.setdefault(key, []).append(seg)

    keys = sorted(groups.keys())
    # Deterministic shuffle via hash of key + seed.
    keys.sort(key=lambda k: hashlib.sha1(f"{seed}:{k}".encode()).hexdigest())

    n = len(keys)
    n_test = max(0, int(round(n * test_ratio))) if n else 0
    n_val = max(0, int(round(n * val_ratio))) if n else 0
    if n_test + n_val >= n and n > 0:
        n_test = min(n_test, max(0, n - 1))
        n_val = min(n_val, max(0, n - n_test - (1 if n > n_test else 0)))

    test_keys = set(keys[:n_test])
    val_keys = set(keys[n_test : n_test + n_val])

    for key, segs in groups.items():
        if key in test_keys:
            split: Split = "test"
        elif key in val_keys:
            split = "val"
        else:
            split = "train"
        for seg in segs:
            seg.train_split = split

    return dataset


def upsert_segment(dataset: SpeechDataset, segment: SpeechSegment) -> SpeechDataset:
    for i, existing in enumerate(dataset.segments):
        if existing.segment_id == segment.segment_id:
            dataset.segments[i] = segment
            return dataset
    dataset.segments.append(segment)
    return dataset


def dataset_summary(dataset: SpeechDataset) -> dict[str, Any]:
    splits: dict[str, int] = {"train": 0, "val": 0, "test": 0}
    speakers: set[str] = set()
    emotions: dict[str, int] = {}
    for seg in dataset.segments:
        splits[seg.train_split] = splits.get(seg.train_split, 0) + 1
        if seg.speaker_id:
            speakers.add(seg.speaker_id)
        emotions[seg.emotion] = emotions.get(seg.emotion, 0) + 1
    return {
        "dataset_id": dataset.dataset_id,
        "name": dataset.name,
        "sessions": len(dataset.sessions),
        "segments": len(dataset.segments),
        "speakers": len(speakers),
        "splits": splits,
        "emotions": emotions,
    }
