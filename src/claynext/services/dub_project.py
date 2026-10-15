"""Lightweight Studio project + overlay template presets."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claynext.utils.config import PRESET_DIR, PROJECT_DIR

RECENT_PATH = PROJECT_DIR / ".recent.json"
RECENT_LIMIT = 24
PROJECT_GLOB = "*.claynext.json"

DEFAULT_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "Clean": [],
    "Lower third": [
        {
            "kind": "caption",
            "x": 0.08,
            "y": 0.82,
            "w": 0.55,
            "h": 0.10,
            "rotation": 0,
            "color": "#f8fafc",
            "opacity": 100,
            "text": "Caption",
            "font_size": 22,
            "live": True,
        }
    ],
    "Corner logo": [
        {
            "kind": "logo",
            "x": 0.86,
            "y": 0.08,
            "w": 0.12,
            "h": 0.12,
            "rotation": 0,
            "color": "#ffffff",
            "opacity": 90,
            "text": "LOGO",
            "font_size": 14,
            "live": False,
        }
    ],
    "Title card": [
        {
            "kind": "text",
            "x": 0.5,
            "y": 0.42,
            "w": 0.7,
            "h": 0.14,
            "rotation": 0,
            "color": "#fbbf24",
            "opacity": 100,
            "text": "Movie Title",
            "font_size": 32,
            "live": False,
        },
        {
            "kind": "caption",
            "x": 0.5,
            "y": 0.58,
            "w": 0.6,
            "h": 0.08,
            "rotation": 0,
            "color": "#e2e8f0",
            "opacity": 100,
            "text": "Khmer Dub",
            "font_size": 16,
            "live": False,
        },
    ],
}


def _write(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_default_presets():
    for name, overlays in DEFAULT_TEMPLATES.items():
        path = PRESET_DIR / f"{name.lower().replace(' ', '_')}.json"
        if not path.is_file():
            _write(path, {"name": name, "overlays": overlays, "kind": "template"})


def list_presets() -> list[dict[str, Any]]:
    ensure_default_presets()
    rows = []
    for path in sorted(PRESET_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append({"name": data.get("name") or path.stem, "path": str(path), "data": data})
    return rows


def save_preset(name: str, overlays: list[dict], extra: dict | None = None) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_") or "preset"
    path = PRESET_DIR / f"{slug}.json"
    payload = {"name": name.strip() or slug, "overlays": overlays, "kind": "template"}
    if extra:
        payload.update(extra)
    _write(path, payload)
    return str(path)


def _slug(name: str, fallback: str = "project") -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_") or fallback


def project_body(name: str, payload: dict) -> dict:
    return {
        "format": "claynext-studio-lite",
        "version": 2,
        "name": name.strip() or "Untitled",
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **payload,
    }


def save_project(name: str, payload: dict) -> str:
    slug = _slug(name)
    path = PROJECT_DIR / f"{slug}.claynext.json"
    _write(path, project_body(name.strip() or slug, payload))
    remember_project(path)
    return str(path)


def write_project(path: str | Path, name: str, payload: dict) -> str:
    dest = Path(path)
    _write(dest, project_body(name, payload))
    remember_project(dest)
    return str(dest)


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_project(path: str | Path) -> dict[str, Any]:
    """Load a project file and normalize core fields."""
    dest = Path(path)
    data = load_json(dest)
    if not isinstance(data, dict):
        raise ValueError("Invalid project file")
    name = str(data.get("name") or dest.stem.replace(".claynext", "") or "Untitled")
    data["name"] = name
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    project = dict(project)
    project.setdefault("name", name)
    project["path"] = str(dest.resolve())
    data["project"] = project
    return data


def update_project(
    path: str | Path,
    *,
    name: str | None = None,
    settings: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    rename_file: bool = False,
) -> str:
    """
    Update an existing project file.
    - name/settings update metadata in-place
    - payload replaces studio state fields when provided
    - rename_file moves the .claynext.json when the display name changes
    """
    dest = Path(path)
    if not dest.is_file():
        raise FileNotFoundError(f"Project not found: {dest}")

    data = load_project(dest)
    clean_name = (name if name is not None else str(data.get("name") or "Untitled")).strip() or "Untitled"
    data["name"] = clean_name

    project = dict(data.get("project") or {})
    if settings:
        project.update(settings)
    project["name"] = clean_name
    project["path"] = str(dest.resolve())
    project.setdefault("save_to", str(dest.parent))
    data["project"] = project

    if payload:
        for key, value in payload.items():
            if key in {"format", "version", "name", "saved_at"}:
                continue
            data[key] = value

    data["saved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["format"] = data.get("format") or "claynext-studio-lite"
    data["version"] = data.get("version") or 2

    target = dest
    if rename_file:
        candidate = dest.with_name(f"{_slug(clean_name)}.claynext.json")
        if candidate.resolve() != dest.resolve():
            if candidate.exists():
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                candidate = dest.with_name(f"{_slug(clean_name)}_{stamp}.claynext.json")
            _write(candidate, data)
            try:
                dest.unlink(missing_ok=True)
            except TypeError:
                if dest.exists():
                    dest.unlink()
            forget_project(dest)
            target = candidate
            data["project"]["path"] = str(target.resolve())
            _write(target, data)
        else:
            _write(target, data)
    else:
        _write(target, data)

    remember_project(target)
    return str(target)


def delete_project(path: str | Path, *, delete_file: bool = True) -> bool:
    """Remove a project from recent list and optionally delete the file."""
    dest = Path(path)
    forget_project(dest)
    if not delete_file:
        return True
    if not dest.is_file():
        return False
    dest.unlink()
    return True


def create_blank_project(
    name: str,
    *,
    save_to: str | Path | None = None,
    settings: dict[str, Any] | None = None,
) -> str:
    """Create an empty studio project file and return its path."""
    clean = (name or "Untitled").strip() or "Untitled"
    folder = Path(save_to) if save_to else PROJECT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_slug(clean)}.claynext.json"
    if path.is_file():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = folder / f"{_slug(clean)}_{stamp}.claynext.json"
    meta = dict(settings or {})
    meta.setdefault("name", clean)
    meta["path"] = str(path)
    meta.setdefault("save_to", str(folder))

    media = str(meta.get("media") or "").strip()
    if media and Path(media).is_file():
        if meta.get("import_mode") == "copy":
            import shutil
            media_dir = folder / "media"
            media_dir.mkdir(parents=True, exist_ok=True)
            target_media = media_dir / Path(media).name
            if target_media.resolve() != Path(media).resolve():
                if not target_media.exists():
                    try:
                        shutil.copy2(media, target_media)
                        media = str(target_media)
                        meta["media"] = media
                    except Exception:
                        pass

    language = str(meta.get("language") or meta.get("target_lang") or "").strip()
    source_language = str(meta.get("source_language") or meta.get("source_lang") or "").strip()

    payload = {
        "project": meta,
        "compositions": [],
        "composition_index": -1,
        "tasks": [],
        "media": media,
        "language": language,
        "source_language": source_language,
        "segments": [],
        "overlays": [],
        "fx": [],
        "tracks": [],
        "footage": [{"path": media, "name": Path(media).name}] if media and Path(media).is_file() else [],
        "takes": [],
    }
    _write(path, project_body(clean, payload))
    remember_project(path)
    return str(path)


def project_card(path: str | Path) -> dict[str, Any] | None:
    """Metadata card for home / recent lists."""
    dest = Path(path)
    if not dest.is_file():
        return None
    name = dest.stem.replace(".claynext", "").replace("_", " ").strip() or dest.stem
    saved_at = ""
    media = ""
    try:
        data = load_json(dest)
        name = str(data.get("name") or name)
        saved_at = str(data.get("saved_at") or "")
        media = str(data.get("media") or "")
        project = data.get("project") if isinstance(data.get("project"), dict) else {}
        if project.get("name"):
            name = str(project["name"])
    except Exception:
        data = {}
    try:
        mtime = dest.stat().st_mtime
    except OSError:
        mtime = 0.0
    return {
        "name": name,
        "path": str(dest),
        "saved_at": saved_at,
        "media": media,
        "mtime": mtime,
        "exists": True,
    }


def list_projects(folder: str | Path | None = None) -> list[dict[str, Any]]:
    root = Path(folder) if folder else PROJECT_DIR
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in root.glob(PROJECT_GLOB):
        card = project_card(path)
        if card:
            rows.append(card)
    rows.sort(key=lambda row: row.get("mtime") or 0.0, reverse=True)
    return rows


def _read_recent() -> list[str]:
    if not RECENT_PATH.is_file():
        return []
    try:
        data = json.loads(RECENT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [str(item) for item in data if item]
    if isinstance(data, dict) and isinstance(data.get("paths"), list):
        return [str(item) for item in data["paths"] if item]
    return []


def remember_project(path: str | Path) -> None:
    dest = str(Path(path).resolve())
    paths = [p for p in _read_recent() if p != dest]
    paths.insert(0, dest)
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    _write(RECENT_PATH, {"paths": paths[:RECENT_LIMIT]})


def forget_project(path: str | Path) -> None:
    dest = str(Path(path).resolve())
    paths = [p for p in _read_recent() if p != dest]
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    _write(RECENT_PATH, {"paths": paths[:RECENT_LIMIT]})


def list_recent_projects(limit: int = RECENT_LIMIT) -> list[dict[str, Any]]:
    """Recent projects (existing files first), then fill with projects folder."""
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for raw in _read_recent():
        card = project_card(raw)
        if not card:
            continue
        key = str(Path(card["path"]).resolve())
        if key in seen:
            continue
        seen.add(key)
        rows.append(card)
        if len(rows) >= limit:
            return rows
    for card in list_projects():
        key = str(Path(card["path"]).resolve())
        if key in seen:
            continue
        seen.add(key)
        rows.append(card)
        if len(rows) >= limit:
            break
    return rows
