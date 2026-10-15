"""
SQLite persistence for Claynext Studio tool data and media library.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claynext.utils.config import DATA_DIR

DB_PATH = DATA_DIR / "claynext.db"

_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}
_AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}

_SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS media_files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    path          TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    kind          TEXT    NOT NULL DEFAULT 'media',
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    in_library    INTEGER NOT NULL DEFAULT 1,
    added_at      TEXT    NOT NULL,
    last_opened_at TEXT
);

CREATE TABLE IF NOT EXISTS asr_jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id      INTEGER REFERENCES media_files(id) ON DELETE SET NULL,
    media_path    TEXT    NOT NULL,
    model         TEXT    NOT NULL,
    language      TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'running',
    error         TEXT,
    created_at    TEXT    NOT NULL,
    finished_at   TEXT
);

CREATE TABLE IF NOT EXISTS asr_segments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        INTEGER NOT NULL REFERENCES asr_jobs(id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,
    start_ts      TEXT    NOT NULL,
    end_ts        TEXT    NOT NULL,
    speaker       TEXT    NOT NULL DEFAULT '',
    text          TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_asr_jobs_path ON asr_jobs(media_path, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_asr_segments_job ON asr_segments(job_id, seq);

CREATE TABLE IF NOT EXISTS api_keys (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    provider       TEXT    NOT NULL,
    label          TEXT    NOT NULL DEFAULT '',
    secret         TEXT    NOT NULL,
    enabled        INTEGER NOT NULL DEFAULT 1,
    cooldown_until TEXT,
    last_used_at   TEXT,
    fail_count     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_api_keys_provider ON api_keys(provider, enabled);

CREATE TABLE IF NOT EXISTS tool_settings (
    tool          TEXT NOT NULL,
    key           TEXT NOT NULL,
    value         TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (tool, key)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _kind_for(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in _VIDEO_EXTS:
        return "video"
    if ext in _AUDIO_EXTS:
        return "audio"
    return "media"


class StudioStore:
    """Thread-safe SQLite store used by ASR and other tools."""

    def __init__(self, db_path: Path | str | None = None):
        self._path = Path(db_path or DB_PATH)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self):
        with self._lock:
            self._conn.close()

    def _execute(self, sql: str, params: tuple = (), *, fetch: str | None = None):
        with self._lock:
            cur = self._conn.execute(sql, params)
            if fetch == "one":
                row = cur.fetchone()
                self._conn.commit()
                return row
            if fetch == "all":
                rows = cur.fetchall()
                self._conn.commit()
                return rows
            self._conn.commit()
            return cur

    # ─── Settings ────────────────────────────────────────────────────

    def get_setting(self, tool: str, key: str, default: str = "") -> str:
        row = self._execute(
            "SELECT value FROM tool_settings WHERE tool = ? AND key = ?",
            (tool, key),
            fetch="one",
        )
        return default if row is None else str(row["value"])

    def set_setting(self, tool: str, key: str, value: str):
        self._execute(
            """
            INSERT INTO tool_settings (tool, key, value) VALUES (?, ?, ?)
            ON CONFLICT(tool, key) DO UPDATE SET value = excluded.value
            """,
            (tool, key, value),
        )

    # ─── Media library ───────────────────────────────────────────────

    def upsert_media(self, path: str) -> int:
        abs_path = os.path.abspath(path)
        name = os.path.basename(abs_path)
        kind = _kind_for(abs_path)
        try:
            size = os.path.getsize(abs_path) if os.path.isfile(abs_path) else 0
        except OSError:
            size = 0
        self._execute(
            """
            INSERT INTO media_files (path, name, kind, size_bytes, in_library, added_at)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(path) DO UPDATE SET
                name = excluded.name,
                kind = excluded.kind,
                size_bytes = excluded.size_bytes,
                in_library = 1
            """,
            (abs_path, name, kind, size, _now()),
        )
        row = self._execute(
            "SELECT id FROM media_files WHERE path = ?", (abs_path,), fetch="one"
        )
        return int(row["id"])

    def mark_opened(self, path: str):
        self._execute(
            "UPDATE media_files SET last_opened_at = ? WHERE path = ?",
            (_now(), os.path.abspath(path)),
        )

    def set_in_library(self, path: str, in_library: bool):
        self._execute(
            "UPDATE media_files SET in_library = ? WHERE path = ?",
            (1 if in_library else 0, os.path.abspath(path)),
        )

    def sync_library(self, paths: list[str]):
        abs_paths = [os.path.abspath(p) for p in paths]
        for path in abs_paths:
            self.upsert_media(path)
        if abs_paths:
            placeholders = ",".join("?" * len(abs_paths))
            self._execute(
                f"UPDATE media_files SET in_library = 0 WHERE path NOT IN ({placeholders})",
                tuple(abs_paths),
            )
        else:
            self._execute("UPDATE media_files SET in_library = 0")

    def list_library(self) -> list[dict[str, Any]]:
        rows = self._execute(
            """
            SELECT id, path, name, kind, size_bytes, last_opened_at
            FROM media_files
            WHERE in_library = 1
            ORDER BY added_at ASC
            """,
            fetch="all",
        )
        return [dict(r) for r in rows]

    def last_opened_path(self) -> str:
        row = self._execute(
            """
            SELECT path FROM media_files
            WHERE in_library = 1 AND last_opened_at IS NOT NULL
            ORDER BY last_opened_at DESC LIMIT 1
            """,
            fetch="one",
        )
        return str(row["path"]) if row else ""

    def media_id_for(self, path: str) -> int | None:
        row = self._execute(
            "SELECT id FROM media_files WHERE path = ?",
            (os.path.abspath(path),),
            fetch="one",
        )
        return int(row["id"]) if row else None

    # ─── ASR jobs ────────────────────────────────────────────────────

    def create_job(self, media_path: str, model: str, language: str) -> int:
        abs_path = os.path.abspath(media_path)
        media_id = self.upsert_media(abs_path)
        cur = self._execute(
            """
            INSERT INTO asr_jobs (media_id, media_path, model, language, status, created_at)
            VALUES (?, ?, ?, ?, 'running', ?)
            """,
            (media_id, abs_path, model, language, _now()),
        )
        return int(cur.lastrowid)

    def finish_job(self, job_id: int, segments: list[dict[str, Any]]):
        with self._lock:
            self._conn.execute(
                "DELETE FROM asr_segments WHERE job_id = ?", (job_id,)
            )
            self._conn.executemany(
                """
                INSERT INTO asr_segments (job_id, seq, start_ts, end_ts, speaker, text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        job_id,
                        int(seg.get("id", i + 1)),
                        str(seg.get("start", "")),
                        str(seg.get("end", "")),
                        str(seg.get("speaker", "")),
                        str(seg.get("text", "")),
                    )
                    for i, seg in enumerate(segments)
                ],
            )
            self._conn.execute(
                "UPDATE asr_jobs SET status = 'done', finished_at = ?, error = NULL WHERE id = ?",
                (_now(), job_id),
            )
            self._conn.commit()

    def fail_job(self, job_id: int, error: str):
        self._execute(
            "UPDATE asr_jobs SET status = 'error', finished_at = ?, error = ? WHERE id = ?",
            (_now(), error, job_id),
        )

    def latest_job_for(self, media_path: str) -> dict[str, Any] | None:
        row = self._execute(
            """
            SELECT id, media_path, model, language, status, created_at, finished_at
            FROM asr_jobs
            WHERE media_path = ? AND status = 'done'
            ORDER BY id DESC LIMIT 1
            """,
            (os.path.abspath(media_path),),
            fetch="one",
        )
        return dict(row) if row else None

    def segments_for_job(self, job_id: int) -> list[dict[str, Any]]:
        rows = self._execute(
            """
            SELECT seq AS id, start_ts AS start, end_ts AS end, speaker, text
            FROM asr_segments
            WHERE job_id = ?
            ORDER BY seq ASC
            """,
            (job_id,),
            fetch="all",
        )
        return [dict(r) for r in rows]

    def update_segment(self, job_id: int, seq: int, **fields: str):
        allowed = {"start": "start_ts", "end": "end_ts", "speaker": "speaker", "text": "text"}
        sets = []
        values: list[Any] = []
        for key, column in allowed.items():
            if key in fields:
                sets.append(f"{column} = ?")
                values.append(fields[key])
        if not sets:
            return
        values.extend([job_id, seq])
        self._execute(
            f"UPDATE asr_segments SET {', '.join(sets)} WHERE job_id = ? AND seq = ?",
            tuple(values),
        )

    # ─── API keys (LLM rotation) ─────────────────────────────────────

    def list_api_keys(self, provider: str | None = None) -> list[dict[str, Any]]:
        if provider:
            rows = self._execute(
                """
                SELECT id, provider, label, secret, enabled, cooldown_until,
                       last_used_at, fail_count, created_at
                FROM api_keys WHERE provider = ? ORDER BY id ASC
                """,
                (provider,),
                fetch="all",
            )
        else:
            rows = self._execute(
                """
                SELECT id, provider, label, secret, enabled, cooldown_until,
                       last_used_at, fail_count, created_at
                FROM api_keys ORDER BY provider ASC, id ASC
                """,
                fetch="all",
            )
        return [dict(r) for r in rows]

    def add_api_key(self, provider: str, secret: str, label: str = "") -> int:
        secret = (secret or "").strip()
        if not secret:
            raise ValueError("API key is empty.")
        existing = self._execute(
            "SELECT id FROM api_keys WHERE provider = ? AND secret = ?",
            (provider, secret),
            fetch="one",
        )
        if existing:
            return int(existing["id"])
        cur = self._execute(
            """
            INSERT INTO api_keys (provider, label, secret, enabled, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (provider, (label or "").strip(), secret, _now()),
        )
        return int(cur.lastrowid)

    def delete_api_key(self, key_id: int):
        self._execute("DELETE FROM api_keys WHERE id = ?", (key_id,))

    def set_api_key_enabled(self, key_id: int, enabled: bool):
        self._execute(
            "UPDATE api_keys SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, key_id),
        )

    def update_api_key_state(
        self,
        key_id: int,
        *,
        cooldown_until: str | None = None,
        last_used_at: str | None = None,
        fail_count: int | None = None,
        clear_cooldown: bool = False,
    ):
        sets = []
        values: list[Any] = []
        if clear_cooldown:
            sets.append("cooldown_until = NULL")
        elif cooldown_until is not None:
            sets.append("cooldown_until = ?")
            values.append(cooldown_until)
        if last_used_at is not None:
            sets.append("last_used_at = ?")
            values.append(last_used_at)
        if fail_count is not None:
            sets.append("fail_count = ?")
            values.append(fail_count)
        if not sets:
            return
        values.append(key_id)
        self._execute(f"UPDATE api_keys SET {', '.join(sets)} WHERE id = ?", tuple(values))

    def migrate_legacy_api_keys(self):
        gem = self.get_setting("dub", "gemini_key", "")
        if gem.strip():
            self.add_api_key("gemini", gem.strip(), "Imported Gemini")
            self.set_setting("dub", "gemini_key", "")
        hf = self.get_setting("dub", "hf_token", "")
        if hf.strip():
            self.add_api_key("huggingface", hf.strip(), "Imported Hugging Face")
            self.set_setting("dub", "hf_token", "")


_store: StudioStore | None = None
_store_lock = threading.Lock()


def get_store() -> StudioStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = StudioStore()
        return _store
