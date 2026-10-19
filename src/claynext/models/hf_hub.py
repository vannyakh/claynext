"""
Claynext Hugging Face Model Hub Manager.
Provides discovery, download/pull with progress tracking, local caching, and status tracking
for Translation, TTS, and ASR models from Hugging Face.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from claynext.models.llm_keys import get_key_pool
from claynext.utils.config import MODELS_DIR

_download_lock = threading.Lock()
_CATALOG_PATH = Path(__file__).with_name("models.json")


def _load_catalog() -> list[dict[str, Any]]:
    """Model and LLM list from models.json."""
    try:
        payload = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("models") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict) and row.get("id") and row.get("name"):
            item = dict(row)
            item.setdefault("install", "hf")
            item.setdefault("category", "")
            item.setdefault("description", "")
            item.setdefault("size_label", "")
            out.append(item)
    return out


HF_MODEL_REGISTRY: list[dict[str, Any]] = _load_catalog()


def _hf_token() -> Optional[str]:
    """Retrieve Hugging Face token if configured in key pool or environment."""
    keys = get_key_pool().secrets("huggingface")
    if keys:
        return keys[0]
    return os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")


def get_model_meta(repo_id: str) -> Optional[dict[str, Any]]:
    """Return model metadata from registry, or generate default entry for custom repo."""
    for item in HF_MODEL_REGISTRY:
        if item["id"].lower() == repo_id.lower():
            return item
    return None


def get_model_registry(category: Optional[str] = None) -> list[dict[str, Any]]:
    """Return model entries, optionally filtered by category ('translate', 'tts', 'asr', 'llm')."""
    pulled = _ollama_names()
    out = []
    for item in HF_MODEL_REGISTRY:
        if category and item["category"] != category:
            continue
        entry = dict(item)
        state = model_install_state(entry, pulled)
        entry.update(state)
        entry["is_downloaded"] = state["ready"]
        out.append(entry)
    return out


def model_install_state(item: dict[str, Any], ollama_names: set[str] | None = None) -> dict[str, Any]:
    """How the settings row should offer this model on the current machine."""
    from claynext.models.features import feature_for_extra

    extra = str(item.get("extra") or "")
    if extra:
        feature = feature_for_extra(extra)
        if feature is not None and not feature.get("supported"):
            return {
                "ready": False,
                "action": "unsupported",
                "status": "Unsupported",
                "hint": feature.get("hint") or "Not available on this platform.",
            }
    kind = str(item.get("install") or "hf")
    if kind == "cloud":
        return {
            "ready": False,
            "action": "cloud",
            "status": "Cloud",
            "hint": item.get("description") or "Uses an API key. Nothing is downloaded.",
        }
    if kind == "ollama":
        name = str(item.get("ollama") or item.get("id") or "")
        names = ollama_names if ollama_names is not None else _ollama_names()
        pulled = name in names
        return {
            "ready": pulled,
            "action": "ready" if pulled else "install",
            "status": "Downloaded" if pulled else "Available",
            "hint": item.get("description") or "",
        }
    downloaded = is_model_downloaded(str(item.get("id") or ""))
    return {
        "ready": downloaded,
        "action": "ready" if downloaded else "install",
        "status": "Downloaded" if downloaded else "Available",
        "hint": item.get("description") or "",
    }


def _ollama_names() -> set[str]:
    if shutil.which("ollama") is None:
        return set()
    import subprocess

    try:
        proc = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    names: set[str] = set()
    for line in (proc.stdout or "").splitlines()[1:]:
        token = line.split()
        if token:
            names.add(token[0])
    return names


def _candidate_cache_dirs(repo_id: str) -> list[Path]:
    """List directory locations where this Hugging Face model might reside."""
    norm_name = repo_id.replace("/", "--")
    hf_folder_name = f"models--{norm_name}"

    candidates: list[Path] = [
        # 1. Project models directory (data/models/models--owner--repo)
        MODELS_DIR / hf_folder_name,
        # 2. Project models directory direct subfolder (data/models/repo)
        MODELS_DIR / repo_id.split("/")[-1],
        MODELS_DIR / repo_id,
        # 3. Default user Hugging Face cache directory (~/.cache/huggingface/hub/models--owner--repo)
        Path.home() / ".cache" / "huggingface" / "hub" / hf_folder_name,
    ]
    return candidates


def is_model_downloaded(repo_id: str) -> bool:
    """Check if the Hugging Face model is already downloaded locally."""
    meta = get_model_meta(repo_id)
    essential = (meta or {}).get("essential_file")

    for cand in _candidate_cache_dirs(repo_id):
        if not cand.is_dir():
            continue

        # Look in snapshots if present (standard HF hub layout)
        snapshots = cand / "snapshots"
        if snapshots.is_dir():
            snaps = [s for s in snapshots.iterdir() if s.is_dir()]
            if snaps:
                latest = snaps[0]
                if essential:
                    if (latest / essential).is_file():
                        return True
                else:
                    if any(latest.iterdir()):
                        return True

        # Check direct directory
        if essential:
            if (cand / essential).is_file():
                return True
        else:
            if any(cand.iterdir()):
                return True

    return False


def get_local_model_path(repo_id: str) -> Optional[str]:
    """
    Return the resolved local filesystem directory path for a downloaded model.
    Returns None if not downloaded.
    """
    meta = get_model_meta(repo_id)
    essential = (meta or {}).get("essential_file")

    for cand in _candidate_cache_dirs(repo_id):
        if not cand.is_dir():
            continue

        snapshots = cand / "snapshots"
        if snapshots.is_dir():
            snaps = [s for s in snapshots.iterdir() if s.is_dir()]
            if snaps:
                latest = snaps[0]
                if essential:
                    if (latest / essential).is_file():
                        return str(latest)
                else:
                    return str(latest)

        if essential:
            if (cand / essential).is_file():
                return str(cand)
        elif any(cand.iterdir()):
            return str(cand)

    return None


def pull_model(
    repo_id: str,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> str:
    """
    Download/pull a model from Hugging Face into data/models.
    Reports progress via progress_callback(percentage, message).
    Returns the resolved local model path on success.
    """
    from huggingface_hub import snapshot_download

    token = _hf_token()
    meta = get_model_meta(repo_id)
    display_name = meta["name"] if meta else repo_id

    if progress_callback:
        progress_callback(5, f"Connecting to Hugging Face for {display_name}…")

    with _download_lock:
        # Check if already present
        cached = get_local_model_path(repo_id)
        if cached:
            if progress_callback:
                progress_callback(100, f"{display_name} is already available.")
            return cached

        if progress_callback:
            progress_callback(20, f"Downloading {display_name} weights from Hugging Face…")

        try:
            local_path = snapshot_download(
                repo_id=repo_id,
                cache_dir=str(MODELS_DIR),
                token=token,
                tqdm_class=_progress_tqdm(progress_callback, display_name),
            )
            if progress_callback:
                progress_callback(100, f"Installed {display_name}")
            return str(local_path)
        except Exception as e:
            if progress_callback:
                progress_callback(0, f"Failed to install {display_name}: {e}")
            raise RuntimeError(f"Could not install Hugging Face model '{repo_id}': {e}") from e


def _progress_tqdm(progress_callback, display_name: str):
    """tqdm stand-in that reports byte progress without drawing a bar."""
    from tqdm.auto import tqdm

    class _Tqdm(tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = True
            super().__init__(*args, **kwargs)

        def update(self, n=1):
            shown = super().update(n)
            total = self.total or 0
            if progress_callback and total > 0:
                pct = 15 + int(min(1.0, (self.n or 0) / total) * 80)
                progress_callback(pct, f"Installing {display_name}… {pct}%")
            return shown

    return _Tqdm


def _ensure_feature(extra: str, progress_callback) -> None:
    from claynext.models.features import feature_for_extra, install_uv_extra

    feature = feature_for_extra(extra)
    if feature is None:
        return
    if not feature.get("supported"):
        raise RuntimeError(feature.get("hint") or "This feature cannot be installed on this platform.")
    if feature.get("installed"):
        return

    def _mapped(pct: int, msg: str) -> None:
        if progress_callback:
            progress_callback(max(0, min(40, int(pct) * 40 // 100)), msg)

    install_uv_extra(extra, progress_callback=_mapped)


def _pull_ollama(name: str, progress_callback) -> str:
    import subprocess

    if shutil.which("ollama") is None:
        raise RuntimeError("Ollama is not installed. Install Ollama, then pull this model.")
    if progress_callback:
        progress_callback(8, f"Pulling {name}…")
    proc = subprocess.Popen(
        ["ollama", "pull", name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    last = f"Pulling {name}…"
    for raw in proc.stdout:
        line = raw.strip()
        if line:
            last = line[:140]
            if progress_callback:
                progress_callback(50, last)
    code = proc.wait()
    if code != 0:
        raise RuntimeError(last or f"ollama pull {name} failed")
    if progress_callback:
        progress_callback(100, f"Installed {name}")
    return name


def install_model(
    repo_id: str,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> str:
    """Install a catalog model. Hugging Face weights run in a child process."""
    import subprocess
    import sys

    repo_id = (repo_id or "").strip()
    if not repo_id:
        raise ValueError("Missing model id")
    meta = get_model_meta(repo_id) or {}
    kind = str(meta.get("install") or "hf")
    extra = str(meta.get("extra") or "")
    if extra:
        _ensure_feature(extra, progress_callback)
    if kind == "cloud":
        raise RuntimeError("This model runs in the cloud. Add an API key in Settings. Nothing is downloaded.")
    if kind == "ollama":
        return _pull_ollama(str(meta.get("ollama") or repo_id), progress_callback)

    def _progress(pct: int, msg: str) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(max(0, min(100, int(pct))), str(msg or ""))
        except Exception:
            pass

    _progress(2, f"Starting install · {repo_id}")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    cmd = [sys.executable, "-m", "claynext.models.hf_hub", "--install", repo_id]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    path = ""
    error = ""
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.strip()
        if line.startswith("PROGRESS\t"):
            parts = line.split("\t", 2)
            pct = parts[1] if len(parts) > 1 else "0"
            msg = parts[2] if len(parts) > 2 else ""
            try:
                _progress(int(float(pct)), msg)
            except ValueError:
                _progress(0, msg)
        elif line.startswith("RESULT\t"):
            path = line.split("\t", 1)[1].strip()
        elif line.startswith("ERROR\t"):
            error = line.split("\t", 1)[1].strip()
    code = proc.wait()
    if code != 0 or not path:
        raise RuntimeError(error or f"Install failed for {repo_id}")
    _progress(100, f"Installed {repo_id}")
    return path


def _install_cli(repo_id: str) -> int:
    def _emit(pct: int, msg: str) -> None:
        print(f"PROGRESS\t{int(pct)}\t{msg}", flush=True)

    try:
        path = pull_model(repo_id, progress_callback=_emit)
    except Exception as exc:
        print(f"ERROR\t{exc}", flush=True)
        return 1
    print(f"RESULT\t{path}", flush=True)
    return 0


def delete_local_model(repo_id: str) -> bool:
    """Remove local cache of a model from data/models."""
    norm_name = repo_id.replace("/", "--")
    target = MODELS_DIR / f"models--{norm_name}"
    if target.is_dir():
        try:
            shutil.rmtree(target)
            return True
        except OSError:
            return False
    return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "--install":
        raise SystemExit(_install_cli(sys.argv[2]))

