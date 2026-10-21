"""Speaker adapter / LoRA stub for multi-speaker TTS (dry-run metadata only)."""
from __future__ import annotations

from typing import Any


def plan_speaker_adapters(speaker_ids: list[str], *, rank: int = 8) -> dict[str, Any]:
    """Describe adapter slots for each speaker without allocating GPU weights."""
    unique = sorted({s for s in speaker_ids if s})
    return {
        "method": "lora_stub",
        "rank": rank,
        "speakers": [
            {"speaker_id": sid, "adapter_id": f"spk_adapt_{sid}", "status": "planned"}
            for sid in unique
        ],
        "note": "Adapters are planned only until a compatible trainer is installed.",
    }
