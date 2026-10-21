"""JSONL import/export and versioned gold dataset writes under data/khmer_spoken/."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from claynext.models.khmer_spoken.paths import VERSIONS_DIR, ensure_khmer_spoken_dirs
from claynext.models.khmer_spoken.schema import (
    REVIEW_GOLD,
    DialogueExample,
    can_promote_to_gold,
    validate_example,
)


def load_examples(path: str | Path) -> list[DialogueExample]:
    path = Path(path)
    if not path.is_file():
        return []
    rows: list[DialogueExample] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(DialogueExample.from_dict(json.loads(line)))
    return rows


def save_examples(path: str | Path, examples: Iterable[DialogueExample]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")
    return path


def import_jsonl(path: str | Path) -> list[DialogueExample]:
    """Load dialogue JSONL; preserve pending_native_review / license metadata."""
    return load_examples(path)


def export_gold_version(
    examples: list[DialogueExample],
    *,
    version: str | None = None,
    out_dir: str | Path | None = None,
    require_gold_only: bool = True,
) -> dict[str, Any]:
    """Write a reproducible gold dataset version under ``data/khmer_spoken/versions/``.

    Synthetic candidates without native review are excluded (or raise if forced).
    """
    ensure_khmer_spoken_dirs()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    version = version or f"ksld-{stamp}"
    root = Path(out_dir) if out_dir else VERSIONS_DIR / version
    root.mkdir(parents=True, exist_ok=True)

    from claynext.models.khmer_spoken.schema import REVIEW_APPROVED

    accepted: list[DialogueExample] = []
    rejected: list[dict[str, Any]] = []
    for ex in examples:
        eligible_status = ex.review_status in {REVIEW_GOLD, REVIEW_APPROVED}
        if require_gold_only and not eligible_status:
            rejected.append({
                "id": ex.id,
                "review_status": ex.review_status,
                "issues": ["not_approved_or_gold"],
            })
            continue
        ok, issues = can_promote_to_gold(ex)
        if not ok:
            rejected.append({
                "id": ex.id,
                "review_status": ex.review_status,
                "issues": [i.code for i in issues if i.severity == "error"],
            })
            continue
        # Normalize to gold for the versioned export.
        gold = DialogueExample.from_dict(ex.to_dict())
        gold.review_status = REVIEW_GOLD
        if not gold.approved_text:
            gold.approved_text = gold.preferred_khmer()
        accepted.append(gold)

    data_path = root / "dialogue.jsonl"
    save_examples(data_path, accepted)
    manifest = {
        "version": version,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "schema_version": "0.1.0",
        "count": len(accepted),
        "rejected_count": len(rejected),
        "path": str(data_path),
        "notes": (
            "Gold export requires native Khmer human review "
            "(verified_by + verified_at). Synthetic ≠ gold."
        ),
        "platforms": {
            "ai_studio_teacher": "candidates_only",
            "vertex_sft": "separate_client",
            "local_lora": "separate_entrypoint",
            "voice_training": "see claynext.voice_training / data/voice_datasets",
        },
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if rejected:
        (root / "rejected.json").write_text(
            json.dumps(rejected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return {
        "version": version,
        "path": str(data_path),
        "manifest": str(root / "manifest.json"),
        "count": len(accepted),
        "rejected": rejected,
    }


def summarize_review_queue(examples: list[DialogueExample]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ex in examples:
        counts[ex.review_status] = counts.get(ex.review_status, 0) + 1
        # Soft-check every row so callers can surface schema warnings.
        _ = validate_example(ex)
    return counts
