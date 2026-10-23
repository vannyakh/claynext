"""Export ranked Khmer drafts for a later local train. Does not start one."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claynext.models.khmer_spoken.schema import DialogueExample
from claynext.models.training.trainer import training_implementation_available


def export_ranked_training(
    examples: list[DialogueExample],
    dest: str | Path,
) -> dict[str, Any]:
    """Write source/target pairs. The target is the Jev pick when one was kept.

    No weights are written. A missing peft/mlx trainer stays uninstalled.
    """
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for ex in examples:
        if ex.review_status not in {"approved", "gold"}:
            continue
        if not ex.candidates or not ex.source_text:
            continue
        target = ex.training_khmer()
        if not target:
            continue
        rows.append({
            "id": ex.id,
            "source": ex.source_text,
            "target": target,
            "license_type": ex.license_type,
            "review_status": ex.review_status,
            "from_jev": bool((ex.metadata.get("jev") or {}).get("applied")),
        })
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {
        "count": len(rows),
        "path": str(path),
        "weights_written": False,
        "trainer_installed": training_implementation_available(),
    }
