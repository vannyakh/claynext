"""
Preflight checks for optional packages and model weights before dub / TTS runs.

Returns structured gaps so the GUI can alert the user to install or download.
"""
from __future__ import annotations

from typing import Any

from claynext.models.features import (
    feature_status,
    get_feature_setting,
    stem_backend,
    stem_separation_mode,
)


def _tts_engine():
    from claynext.models.tts_service import TTSEngine

    return TTSEngine


def collect_job_gaps(
    *,
    voice_id: str | None = None,
    secondary_voice_id: str | None = None,
    asr_model: str | None = None,
    check_stems: bool = True,
) -> list[dict[str, Any]]:
    """
    Inspect the selected cast / engine options for missing environment pieces.

    Each gap dict:
      id, label, detail, kind (package|model), command, blocking, repo (optional)
    """
    gaps: list[dict[str, Any]] = []
    TTSEngine = _tts_engine()
    voices = [str(v or "") for v in (voice_id, secondary_voice_id) if v]
    needs_voxcpm = any(TTSEngine._is_voxcpm_voice(v) for v in voices)

    if needs_voxcpm:
        st = feature_status("voxcpm")
        if not st.get("installed"):
            gaps.append(
                {
                    "id": "voxcpm",
                    "label": "VoxCPM TTS",
                    "kind": "package",
                    "blocking": True,
                    "command": "uv sync --extra voxcpm",
                    "detail": (
                        "Selected voice needs the VoxCPM package.\n"
                        "Install it, then restart Claynext."
                    ),
                    "repo": "",
                }
            )
        else:
            repo = TTSEngine.VOXCPM_DEFAULT_MODEL
            try:
                from claynext.models.hf_hub import is_model_downloaded

                if not is_model_downloaded(repo):
                    gaps.append(
                        {
                            "id": "voxcpm_weights",
                            "label": "VoxCPM model weights",
                            "kind": "model",
                            "blocking": False,
                            "command": "",
                            "detail": (
                                f"{repo} is not in the local cache yet.\n"
                                "Download it before the first VoxCPM synthesis, "
                                "or let the job pull it automatically."
                            ),
                            "repo": repo,
                        }
                    )
            except Exception:
                pass

    if any(TTSEngine._is_kitten_voice(v) for v in voices):
        kitten_id = "KittenML/kitten-tts-nano-0.8-fp32"
        try:
            if not TTSEngine.is_kitten_model_downloaded(kitten_id):
                gaps.append(
                    {
                        "id": "kitten_weights",
                        "label": "KittenTTS model",
                        "kind": "model",
                        "blocking": False,
                        "command": "",
                        "detail": f"{kitten_id} weights are not downloaded yet.",
                        "repo": kitten_id,
                    }
                )
        except Exception:
            pass

    model = str(asr_model or "").strip().lower()
    if model and "gemini" not in model:
        try:
            import faster_whisper  # noqa: F401
        except Exception:
            gaps.append(
                {
                    "id": "faster_whisper",
                    "label": "Faster-Whisper ASR",
                    "kind": "package",
                    "blocking": True,
                    "command": "uv sync",
                    "detail": "Local transcription needs faster-whisper. Sync dependencies, then retry.",
                    "repo": "",
                }
            )

    if get_feature_setting("prefer_whisperx", "0") == "1":
        st = feature_status("whisperx")
        if not st.get("installed"):
            gaps.append(
                {
                    "id": "whisperx",
                    "label": "WhisperX",
                    "kind": "package",
                    "blocking": False,
                    "command": "uv sync --extra whisperx",
                    "detail": "Prefer WhisperX is on, but WhisperX is not installed. Dub will use Faster-Whisper.",
                    "repo": "",
                }
            )

    if check_stems and stem_separation_mode() == "demucs" and stem_backend() is None:
        gaps.append(
            {
                "id": "demucs",
                "label": "Demucs stem bed",
                "kind": "package",
                "blocking": True,
                "command": "uv sync --extra demucs",
                "detail": (
                    "Stem separation is set to Demucs, but no Demucs backend is installed.\n"
                    "Install Demucs (or Demucs MLX on Apple Silicon), or switch stems to Auto / FFmpeg."
                ),
                "repo": "",
            }
        )

    # De-dupe by id
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for g in gaps:
        gid = str(g.get("id") or "")
        if gid in seen:
            continue
        seen.add(gid)
        unique.append(g)
    return unique


def format_gaps_message(gaps: list[dict[str, Any]]) -> str:
    if not gaps:
        return ""
    lines = ["This job needs pieces that are not ready yet:\n"]
    for g in gaps:
        mark = "•" if g.get("blocking") else "○"
        lines.append(f"{mark} {g.get('label')}")
        detail = str(g.get("detail") or "").strip()
        if detail:
            for part in detail.splitlines():
                lines.append(f"  {part}")
        cmd = str(g.get("command") or "").strip()
        if cmd:
            lines.append(f"  Install: {cmd}")
        repo = str(g.get("repo") or "").strip()
        if repo and g.get("kind") == "model":
            lines.append(f"  Model: {repo}")
        lines.append("")
    lines.append("Install or download the missing environment, then try again.")
    return "\n".join(lines).strip()


def primary_install_command(gaps: list[dict[str, Any]]) -> str:
    for g in gaps:
        cmd = str(g.get("command") or "").strip()
        if cmd:
            return cmd
    return ""


def has_blocking_gaps(gaps: list[dict[str, Any]]) -> bool:
    return any(bool(g.get("blocking")) for g in gaps)
