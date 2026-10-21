"""One hardware plan for speech, encode, and worker pools.

Tools read this instead of guessing CUDA or a fixed thread count.
"""
from __future__ import annotations

import os
import platform
from typing import Any

from claynext.adapters.cpu import get_cpu_adapter

_MACHINE: dict[str, Any] | None = None

_LEGACY_DEVICES = {
    "CPU Threadpool (Fallback)": "best",
    "CUDA (NVIDIA GPU)": "cuda",
    "DirectML (AMD / Intel GPU)": "qsv",
}

_ENCODE_LABELS = {
    "cpu": "CPU encode",
    "videotoolbox": "VideoToolbox",
    "cuda": "NVIDIA encode",
    "qsv": "Quick Sync",
    "amf": "AMD encode",
    "mf": "Media Foundation",
}


def _machine() -> dict[str, Any]:
    global _MACHINE
    if _MACHINE is not None:
        return _MACHINE
    cpu = get_cpu_adapter().hardware_plan()
    logical = max(1, int(cpu.get("logical_cores") or 1))
    physical = max(1, int(cpu.get("physical_cores") or logical))
    reserve = max(0, int(cpu.get("reserve_cores") or 0))
    kind = _detect_encode_kind()
    _MACHINE = {
        "logical_cores": logical,
        "physical_cores": physical,
        "reserve_cores": reserve,
        "usable": max(1, logical - reserve),
        "dub_jobs": max(1, int(cpu.get("dub_jobs") or 1)),
        "tts_workers": max(1, int(cpu.get("tts_workers") or 1)),
        "encode_kind": kind,
    }
    return _MACHINE


def _detect_encode_kind() -> str:
    name = ""
    try:
        from claynext.adapters.hardware_codecs_adapter import get_hardware_codecs

        name = str(get_hardware_codecs().get_recommended_encoder() or "")
    except Exception:
        name = ""
    lower = name.lower()
    if "videotoolbox" in lower:
        return "videotoolbox"
    if "nvenc" in lower:
        return "cuda"
    if "qsv" in lower:
        return "qsv"
    if "amf" in lower:
        return "amf"
    if "_mf" in lower or lower.endswith("mf"):
        return "mf"
    if platform.system() == "Darwin":
        return "videotoolbox"
    if platform.system() == "Windows":
        return "mf"
    return "cpu"


def available_devices() -> list[dict[str, str]]:
    """Choices the Hardware tab can offer on this machine."""
    kind = str(_machine()["encode_kind"])
    rows = [
        {"id": "best", "label": "Best"},
        {"id": "cpu", "label": "CPU"},
    ]
    extra = {
        "videotoolbox": ("videotoolbox", "VideoToolbox"),
        "cuda": ("cuda", "NVIDIA CUDA"),
        "qsv": ("qsv", "Intel Quick Sync"),
        "amf": ("amf", "AMD"),
        "mf": ("mf", "Media Foundation"),
    }
    if kind in extra:
        pid, label = extra[kind]
        rows.append({"id": pid, "label": label})
    return rows


def stored_choice() -> tuple[str, int]:
    """Saved device id and thread cap. ``0`` threads means Auto."""
    from claynext.controllers.store import get_store

    store = get_store()
    raw_device = str(store.get_setting("studio", "device", "best") or "best")
    raw_threads = str(store.get_setting("studio", "worker_threads", "0") or "0")
    device = _LEGACY_DEVICES.get(raw_device, raw_device)
    # The old dialog always stored the CPU fallback and 4 threads. Treat that as Auto / Best.
    if raw_device in _LEGACY_DEVICES and raw_threads == "4":
        return device, 0
    try:
        threads = max(0, int(raw_threads))
    except ValueError:
        threads = 0
    return device, threads


def resource_plan(*, device: str | None = None, threads: int | None = None) -> dict[str, Any]:
    """How tools should run right now."""
    machine = _machine()
    saved_device, saved_threads = stored_choice()
    choice = (device if device is not None else saved_device).strip().lower() or "best"
    known = {row["id"] for row in available_devices()}
    if choice not in known:
        choice = "best"
    cap = saved_threads if threads is None else max(0, int(threads))
    logical = int(machine["logical_cores"])
    usable = int(machine["usable"])
    worker_threads = usable if cap <= 0 else max(1, min(cap, logical))
    encode = _encode_for(choice, str(machine["encode_kind"]))
    speech = "cuda" if choice in {"best", "cuda"} and machine["encode_kind"] == "cuda" else "cpu"
    dub_jobs = int(machine["dub_jobs"])
    tts_workers = int(machine["tts_workers"])
    if cap > 0:
        dub_jobs = max(1, min(dub_jobs, cap))
        tts_workers = max(1, min(tts_workers, worker_threads))
    return {
        "device": choice,
        "logical_cores": logical,
        "physical_cores": int(machine["physical_cores"]),
        "threads": worker_threads,
        "threads_auto": cap <= 0,
        "dub_jobs": dub_jobs,
        "tts_workers": tts_workers,
        "encode": encode,
        "encode_label": _ENCODE_LABELS.get(encode, "CPU encode"),
        "speech_device": speech,
        "speech_compute": "float16" if speech == "cuda" else "int8",
    }


def _encode_for(choice: str, detected: str) -> str:
    if choice == "cpu":
        return "cpu"
    if choice == "best":
        return detected if detected != "cpu" else "cpu"
    if choice == detected:
        return detected
    return "cpu"


def describe_plan(plan: dict[str, Any] | None = None) -> str:
    row = plan or resource_plan()
    speech = "GPU" if row.get("speech_device") == "cuda" else "CPU"
    workers = "auto" if row.get("threads_auto") else "set"
    return (
        f"{int(row['logical_cores'])} cores · {int(row['threads'])} workers ({workers})"
        f" · {row['encode_label']} · speech on {speech}"
    )


def video_encode_args(*, quality: str = "finish", force_cpu: bool = False) -> list[str]:
    """FFmpeg video-encoder flags for the current plan."""
    plan = resource_plan()
    threads = str(max(1, int(plan["threads"])))
    finish = quality != "fast"
    preset = "medium" if finish else "veryfast"
    crf = "18" if finish else "20"
    cpu = [
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", crf,
        "-threads", threads,
        "-pix_fmt", "yuv420p",
    ]
    if force_cpu:
        return cpu
    kind = str(plan["encode"])
    if kind == "videotoolbox":
        bitrate = "8M" if finish else "6M"
        return ["-c:v", "h264_videotoolbox", "-allow_sw", "1", "-b:v", bitrate, "-pix_fmt", "yuv420p"]
    if kind == "cuda":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "19" if finish else "23", "-pix_fmt", "yuv420p"]
    if kind == "qsv":
        return ["-c:v", "h264_qsv", "-global_quality", crf, "-pix_fmt", "yuv420p"]
    if kind == "amf":
        return ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", crf, "-qp_p", crf, "-pix_fmt", "yuv420p"]
    if kind == "mf":
        return ["-c:v", "h264_mf", "-rate_control", "quality", "-quality", "75", "-pix_fmt", "yuv420p"]
    return cpu


def apply_process_threads(plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Publish the thread budget to this process, Qt, and later FFmpeg subprocesses."""
    row = plan or resource_plan()
    n = max(1, int(row["threads"]))
    os.environ["CLAYNEXT_WORKER_THREADS"] = str(n)
    os.environ["OMP_NUM_THREADS"] = str(n)
    try:
        import torch

        torch.set_num_threads(n)
    except Exception:
        pass
    try:
        from PySide6.QtCore import QThreadPool

        # Leave a second slot so a one-thread tool setting cannot freeze the UI pool.
        QThreadPool.globalInstance().setMaxThreadCount(max(2, n))
    except Exception:
        pass
    return row
