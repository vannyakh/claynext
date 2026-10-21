"""Exports: canonical JSONL, and chat-format SFT files split by train / validation / test.

The chat format is one ``{"messages": [system, user, assistant]}`` object per line, which is
the shape hosted chat fine-tuning APIs accept. Whether a given hosted model can actually be
fine-tuned must be checked with the provider before use. By default only ``reviewed`` and
``gold`` records are exported for training; unreviewed exports are labelled as such.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claynext.models.datasets.io import write_records
from claynext.models.datasets.schema import DialogueRecord
from claynext.models.datasets.split import SPLITS
from claynext.models.datasets.store import now_iso, sha256_file

SFT_FORMAT_VERSION = "chat-sft/1"
TRAINING_STATUSES = ("reviewed", "gold")
SFT_SYSTEM_PROMPT = (
    "You localize film dialogue into natural spoken Khmer for dubbing. Keep the meaning. "
    "Choose pronouns and address terms from the speaker, listener, and their relationship. "
    "Match the emotion and register. Do not add profanity the source does not have. "
    "Reply with the Khmer line only."
)


def sft_user_content(rec: DialogueRecord) -> str:
    context: dict[str, Any] = {
        "source_lang": rec.source_lang,
        "target_lang": rec.target_lang,
        "text": rec.source_text,
        "speaker": rec.speaker_id,
        "listener": rec.listener_id,
        "relationship": rec.relationship,
        "emotion": rec.emotion,
        "intensity": rec.intensity,
        "register": rec.register,
        "slang_max": rec.slang_level,
        "profanity_max": rec.profanity_level,
    }
    if rec.regional.region and rec.regional.verified:
        context["region"] = rec.regional.region
    return json.dumps({k: v for k, v in context.items() if v is not None}, ensure_ascii=False, sort_keys=True)


def sft_example(rec: DialogueRecord) -> dict[str, Any] | None:
    cand = rec.preferred_candidate()
    if cand is None:
        return None
    return {"messages": [
        {"role": "system", "content": SFT_SYSTEM_PROMPT},
        {"role": "user", "content": sft_user_content(rec)},
        {"role": "assistant", "content": cand.text},
    ]}


def export_jsonl(records: list[DialogueRecord], path: str | Path) -> Path:
    return write_records(path, records)


def export_sft(
    records: list[DialogueRecord],
    out_dir: str | Path,
    *,
    statuses: tuple[str, ...] = TRAINING_STATUSES,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write ``<split>.jsonl`` (plus ``unsplit.jsonl`` if any record has no split) and ``manifest.json``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    chosen = sorted((r for r in records if r.status in statuses), key=lambda r: r.id)
    buckets: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for rec in chosen:
        example = sft_example(rec)
        if example is not None:
            buckets.setdefault(rec.split or "unsplit", []).append((rec.id, example))
    files = {}
    for split in (*SPLITS, "unsplit"):
        path = out / f"{split}.jsonl"
        rows = buckets.get(split, [])
        if not rows:
            path.unlink(missing_ok=True)
            (out / f"{split}.ids.txt").unlink(missing_ok=True)
            continue
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            for _rid, example in rows:
                fh.write(json.dumps(example, ensure_ascii=False) + "\n")
        (out / f"{split}.ids.txt").write_text("".join(f"{rid}\n" for rid, _ in rows), encoding="utf-8")
        files[split] = {"file": path.name, "examples": len(rows), "sha256": sha256_file(path)}
    unreviewed = sorted(set(statuses) - set(TRAINING_STATUSES))
    manifest = {
        "format": SFT_FORMAT_VERSION,
        "created_at": now_iso(),
        "statuses": list(statuses),
        "contains_unreviewed": bool(unreviewed),
        "files": files,
        "examples": sum(f["examples"] for f in files.values()),
        "skipped_by_status": len(records) - len(chosen),
        "source": source or {},
        "system_prompt": SFT_SYSTEM_PROMPT,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
