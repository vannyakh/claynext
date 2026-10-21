"""On-disk dataset workspace and immutable version snapshots.

Layout under ``DATASETS_DIR`` (``data/datasets``)::

    <name>/working/records.jsonl     editable working set (canonical JSONL, sorted by id)
    <name>/working/rejects.jsonl     rows refused on import, with reasons
    <name>/working/imports.jsonl     one line per import (file, sha256, counts, time)
    <name>/working/dedupe.json       last duplicate report
    <name>/working/split.json        last split report
    <name>/versions/v0001/           records.jsonl + manifest.json, read-only once written
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claynext.models.datasets.io import ImportResult, import_file, read_records, write_records
from claynext.models.datasets.schema import SCHEMA_VERSION, DialogueRecord, Issue

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_VERSION = re.compile(r"^v(\d{4,})$")
READ_ONLY = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH


def default_root() -> Path:
    from claynext.utils.paths import DATASETS_DIR

    return DATASETS_DIR


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def record_counts(records: list[DialogueRecord]) -> dict[str, dict[str, int]]:
    def tally(values) -> dict[str, int]:
        return dict(sorted(Counter(v if v is not None else "(none)" for v in values).items()))

    return {
        "status": tally(r.status for r in records),
        "origin": tally(r.origin for r in records),
        "split": tally(r.split for r in records),
        "category": tally(r.category for r in records),
    }


class DatasetStore:
    def __init__(self, name: str, root: str | Path | None = None):
        if not _NAME.match(name or ""):
            raise ValueError("Dataset name must be 1-64 chars of letters, digits, '.', '_' or '-'.")
        self.name = name
        self.root = Path(root) if root else default_root()
        self.dir = self.root / name
        self.working_dir = self.dir / "working"
        self.versions_dir = self.dir / "versions"

    @property
    def working_path(self) -> Path:
        return self.working_dir / "records.jsonl"

    def exists(self) -> bool:
        return self.working_path.is_file()

    def load_working(self) -> list[DialogueRecord]:
        if not self.exists():
            raise FileNotFoundError(f"Dataset {self.name!r} has no working set. Run 'claynext dataset import' first.")
        return read_records(self.working_path)

    def save_working(self, records: list[DialogueRecord]) -> Path:
        return write_records(self.working_path, records)

    def save_report(self, kind: str, data: dict[str, Any]) -> Path:
        path = self.working_dir / f"{kind}.json"
        _write_json(path, data)
        return path

    def load_report(self, kind: str) -> dict[str, Any] | None:
        path = self.working_dir / f"{kind}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def import_file(self, path: str | Path, *, replace: bool = False, source_name: str = "") -> ImportResult:
        src = Path(path).expanduser().resolve()
        result = import_file(src, dataset=source_name or src.parent.name)
        existing = [] if replace or not self.exists() else self.load_working()
        taken = {r.id for r in existing}
        fresh = []
        for rec in result.records:
            if rec.id in taken:
                issue = Issue("error", "duplicate_id", "id", f"Id {rec.id} is already in the working set.")
                result.rejects.append({"row": None, "id": rec.id, "codes": [issue.code], "issues": [issue.to_dict()]})
            else:
                taken.add(rec.id)
                fresh.append(rec)
        result.records = fresh
        self.save_working(existing + fresh)
        if replace:
            for stale in ("rejects.jsonl", "dedupe.json", "split.json"):
                (self.working_dir / stale).unlink(missing_ok=True)
        at = now_iso()
        _append_jsonl(self.working_dir / "rejects.jsonl",
                      [{**r, "file": src.name, "imported_at": at} for r in result.rejects])
        _append_jsonl(self.working_dir / "imports.jsonl", [{
            "file": str(src),
            "sha256": sha256_file(src),
            "imported_at": at,
            "replace": replace,
            **result.summary(),
        }])
        return result

    def imports(self) -> list[dict[str, Any]]:
        path = self.working_dir / "imports.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # ── Versions ───────────────────────────────────────────────────────

    def list_versions(self) -> list[str]:
        if not self.versions_dir.is_dir():
            return []
        found = [p.name for p in self.versions_dir.iterdir() if p.is_dir() and _VERSION.match(p.name)]
        return sorted(found, key=lambda v: int(_VERSION.match(v).group(1)))

    def latest_version(self) -> str | None:
        versions = self.list_versions()
        return versions[-1] if versions else None

    def manifest(self, version: str) -> dict[str, Any]:
        path = self.versions_dir / version / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"Version {version!r} of {self.name!r} not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def load_version(self, version: str) -> list[DialogueRecord]:
        self.manifest(version)
        return read_records(self.versions_dir / version / "records.jsonl")

    def verify_version(self, version: str) -> bool:
        """True when records.jsonl still matches the hash in the manifest."""
        manifest = self.manifest(version)
        return sha256_file(self.versions_dir / version / "records.jsonl") == manifest["sha256"]

    def create_version(self, *, note: str = "", allow_unchanged: bool = False) -> dict[str, Any]:
        records = self.load_working()
        parent = self.latest_version()
        digest = sha256_file(self.working_path)
        if parent and not allow_unchanged and self.manifest(parent)["sha256"] == digest:
            raise ValueError(f"Working set is identical to {parent}; nothing to snapshot.")
        number = int(_VERSION.match(parent).group(1)) + 1 if parent else 1
        version = f"v{number:04d}"
        target = self.versions_dir / version
        target.mkdir(parents=True, exist_ok=False)
        data_path = target / "records.jsonl"
        data_path.write_bytes(self.working_path.read_bytes())
        manifest = {
            "dataset": self.name,
            "version": version,
            "parent": parent,
            "created_at": now_iso(),
            "schema_version": SCHEMA_VERSION,
            "record_count": len(records),
            "sha256": sha256_file(data_path),
            "counts": record_counts(records),
            "training_eligible": sum(1 for r in records if r.status in ("reviewed", "gold")),
            "note": note,
            "sources": [{k: i.get(k) for k in ("file", "sha256", "imported_at", "imported", "rejected")}
                        for i in self.imports()],
            "dedupe": (self.load_report("dedupe") or {}).get("summary"),
            "split": (self.load_report("split") or {}).get("split"),
        }
        _write_json(target / "manifest.json", manifest)
        for path in (data_path, target / "manifest.json"):
            os.chmod(path, READ_ONLY)
        return manifest
