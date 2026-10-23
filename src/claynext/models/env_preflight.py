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


def _dev_install_command() -> str:
    from claynext.models.features import dev_environment_sync_command

    return dev_environment_sync_command()


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
                    "label": "VoxCPM2",
                    "kind": "package",
                    "blocking": True,
                    "command": _dev_install_command(),
                    "detail": (
                        "Selected voice needs VoxCPM2 (openbmb/VoxCPM2).\n"
                        "Install the voxcpm extra, then restart Claynext."
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

    needs_omnivoice = any(TTSEngine._is_omnivoice_voice(v) for v in voices)
    if needs_omnivoice:
        st = feature_status("omnivoice")
        if not st.get("installed"):
            gaps.append(
                {
                    "id": "omnivoice",
                    "label": "OmniVoice",
                    "kind": "package",
                    "blocking": True,
                    "command": _dev_install_command(),
                    "detail": (
                        "Selected voice needs OmniVoice (k2-fsa/OmniVoice).\n"
                        "Install the omnivoice extra, then restart Claynext."
                    ),
                    "repo": "",
                }
            )
        else:
            repo = TTSEngine.OMNIVOICE_DEFAULT_MODEL
            try:
                from claynext.models.hf_hub import is_model_downloaded

                if not is_model_downloaded(repo):
                    gaps.append(
                        {
                            "id": "omnivoice_weights",
                            "label": "OmniVoice model weights",
                            "kind": "model",
                            "blocking": False,
                            "command": "",
                            "detail": (
                                f"{repo} is not in the local cache yet.\n"
                                "Download it before the first OmniVoice synthesis, "
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
                    "command": _dev_install_command(),
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
                    "command": _dev_install_command(),
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
                "command": _dev_install_command(),
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
    commands: list[str] = []
    for g in gaps:
        mark = "•" if g.get("blocking") else "○"
        lines.append(f"{mark} {g.get('label')}")
        detail = str(g.get("detail") or "").strip()
        if detail:
            for part in detail.splitlines():
                lines.append(f"  {part}")
        cmd = str(g.get("command") or "").strip()
        if cmd and cmd not in commands:
            commands.append(cmd)
        repo = str(g.get("repo") or "").strip()
        if repo and g.get("kind") == "model":
            lines.append(f"  Model: {repo}")
        lines.append("")
    if commands:
        lines.append("Install:")
        lines.extend(commands)
        lines.append("")
    lines.append("Install or download the missing environment, then try again.")
    return "\n".join(lines).strip()


def primary_install_command(gaps: list[dict[str, Any]]) -> str:
    """Command for every package gap: one inexact sync of the full extra set."""
    if any(str(g.get("kind") or "") == "package" and str(g.get("command") or "").strip() for g in gaps):
        return _dev_install_command()
    for g in gaps:
        cmd = str(g.get("command") or "").strip()
        if cmd:
            return cmd
    return ""


def has_blocking_gaps(gaps: list[dict[str, Any]]) -> bool:
    return any(bool(g.get("blocking")) for g in gaps)
