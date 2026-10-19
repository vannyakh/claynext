"""CPU hardware plan. Rust claynext-cpu when the tool is built, otherwise this formula."""
from __future__ import annotations

import os

from claynext.adapters.rust_bridge.cpu import RustCpuAdapter

_cpu_adapter: CpuAdapter | None = None


def plan_for(logical: int, physical: int) -> dict[str, int]:
    """Match backends/cpu/src/hardware.rs plan_for."""
    logical = max(1, int(logical))
    physical = min(logical, max(1, int(physical)))
    reserve = 2 if logical > 4 else 1
    usable = max(1, logical - reserve)
    dub_jobs = min(4, max(1, physical // 3))
    if logical == 1:
        tts_workers = 1
    elif dub_jobs == 1:
        tts_workers = min(8, max(2, usable))
    else:
        tts_workers = min(4, max(2, usable // dub_jobs))
    return {
        "logical_cores": logical,
        "physical_cores": physical,
        "reserve_cores": reserve,
        "dub_jobs": dub_jobs,
        "tts_workers": tts_workers,
    }


def _python_plan() -> dict[str, int]:
    logical = os.cpu_count() or 1
    physical = logical // 2 if logical >= 4 and logical % 2 == 0 else logical
    return plan_for(logical, physical)


class CpuAdapter:
    """How many movies and voice lines to run at once on this machine."""

    def hardware_plan(self) -> dict[str, int]:
        rust = RustCpuAdapter.hardware_plan()
        if rust:
            return plan_for(
                int(rust.get("logical_cores") or 1),
                int(rust.get("physical_cores") or rust.get("logical_cores") or 1),
            )
        return _python_plan()


def get_cpu_adapter() -> CpuAdapter:
    global _cpu_adapter
    if _cpu_adapter is None:
        _cpu_adapter = CpuAdapter()
    return _cpu_adapter
