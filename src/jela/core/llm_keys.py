"""
Rolling LLM API key pool.

On HTTP 429 / RESOURCE_EXHAUSTED, the current key is put on cooldown and the
next enabled key is used. If every key is cooling, wait for the soonest one.
"""
from __future__ import annotations

import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from jela.core.store import get_store

PROVIDERS = (
    ("gemini", "Google Gemini"),
    ("huggingface", "Hugging Face"),
    ("openai", "OpenAI"),
)

_ENV_KEYS = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "huggingface": ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"),
    "openai": ("OPENAI_API_KEY",),
}


class RateLimitError(Exception):
    def __init__(self, message: str = "Rate limited", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class InvalidKeyError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def parse_retry_after(headers: Any = None, body: str = "") -> float:
    seconds = 20.0
    if headers:
        raw = ""
        try:
            raw = headers.get("Retry-After") or headers.get("retry-after") or ""
        except Exception:
            raw = ""
        if raw:
            try:
                seconds = float(raw)
            except ValueError:
                pass
    match = re.search(r"retry.*?(\d+(?:\.\d+)?)\s*(s|sec|second)", body, re.I)
    if match:
        seconds = max(seconds, float(match.group(1)))
    return max(5.0, min(120.0, seconds))


def is_rate_limit(status: int, body: str = "") -> bool:
    if status == 429:
        return True
    blob = (body or "").lower()
    return (
        "resource_exhausted" in blob
        or "rate limit" in blob
        or ("quota" in blob and "exceed" in blob)
    )


class ApiKeyPool:
    def __init__(self):
        self._lock = threading.Lock()
        self._cursor: dict[str, int] = {}
        store = get_store()
        store.migrate_legacy_api_keys()

    def list_keys(self, provider: str | None = None) -> list[dict[str, Any]]:
        return get_store().list_api_keys(provider)

    def add_key(self, provider: str, secret: str, label: str = "") -> int:
        return get_store().add_api_key(provider, secret, label)

    def remove_key(self, key_id: int):
        get_store().delete_api_key(key_id)

    def set_enabled(self, key_id: int, enabled: bool):
        get_store().set_api_key_enabled(key_id, enabled)

    def secrets(self, provider: str) -> list[str]:
        ready = []
        for row in self.list_keys(provider):
            if int(row.get("enabled") or 0) != 1:
                continue
            until = _parse_iso(row.get("cooldown_until"))
            if until and until > _now():
                continue
            secret = (row.get("secret") or "").strip()
            if secret:
                ready.append(secret)
        if ready:
            return ready
        for env in _ENV_KEYS.get(provider, ()):
            val = os.environ.get(env, "").strip()
            if val:
                return [val]
        return []

    def _ready_rows(self, provider: str) -> list[dict[str, Any]]:
        rows = []
        now = _now()
        for row in self.list_keys(provider):
            if int(row.get("enabled") or 0) != 1:
                continue
            until = _parse_iso(row.get("cooldown_until"))
            if until and until > now:
                continue
            if (row.get("secret") or "").strip():
                rows.append(row)
        return rows

    def acquire(self, provider: str) -> dict[str, Any] | None:
        with self._lock:
            rows = self._ready_rows(provider)
            if not rows:
                return None
            start = self._cursor.get(provider, 0) % len(rows)
            ordered = rows[start:] + rows[:start]
            chosen = ordered[0]
            self._cursor[provider] = (start + 1) % len(rows)
            get_store().update_api_key_state(int(chosen["id"]), last_used_at=_now().isoformat())
            return chosen

    def mark_ok(self, key_id: int):
        get_store().update_api_key_state(key_id, fail_count=0, clear_cooldown=True)

    def mark_rate_limited(self, key_id: int, retry_after: float | None = None):
        wait = max(8.0, min(120.0, float(retry_after or 25.0)))
        until = (_now() + timedelta(seconds=wait)).isoformat()
        row = next((r for r in self.list_keys() if int(r["id"]) == key_id), None)
        fails = int(row["fail_count"]) + 1 if row else 1
        get_store().update_api_key_state(key_id, cooldown_until=until, fail_count=fails)

    def soonest_cooldown(self, provider: str) -> float:
        now = _now()
        waits = []
        for row in self.list_keys(provider):
            if int(row.get("enabled") or 0) != 1:
                continue
            until = _parse_iso(row.get("cooldown_until"))
            if until and until > now:
                waits.append((until - now).total_seconds())
        return min(waits) if waits else 0.0

    def call_with_rotation(
        self,
        provider: str,
        fn: Callable[[str], Any],
        *,
        progress: Callable | None = None,
        max_wait: float = 40.0,
    ) -> Any:
        """
        Call fn(secret). On RateLimitError rotate keys. Wait once if all cooling.
        """
        tried: set[int] = set()
        waited = False
        while True:
            row = self.acquire(provider)
            if row is None:
                wait = self.soonest_cooldown(provider)
                if wait > 0 and not waited:
                    pause = min(max_wait, wait + 0.4)
                    if progress:
                        progress(0, f"Rate limited — waiting {pause:.0f}s then rotating keys…")
                    time.sleep(pause)
                    waited = True
                    continue
                env_keys = []
                for env in _ENV_KEYS.get(provider, ()):
                    val = os.environ.get(env, "").strip()
                    if val:
                        env_keys.append(val)
                if env_keys:
                    last_err = None
                    for secret in env_keys:
                        try:
                            return fn(secret)
                        except RateLimitError as exc:
                            last_err = exc
                            continue
                    if last_err:
                        raise last_err
                raise RuntimeError(
                    f"No available {provider} API keys. Add keys in Settings → API Keys."
                )

            key_id = int(row["id"])
            if key_id in tried and waited:
                raise RuntimeError(f"All {provider} keys are rate-limited right now.")
            tried.add(key_id)
            try:
                result = fn(str(row["secret"]))
                self.mark_ok(key_id)
                return result
            except RateLimitError as exc:
                self.mark_rate_limited(key_id, exc.retry_after)
                if progress:
                    progress(0, "Rate limit hit — rotating to the next API key…")
                continue
            except InvalidKeyError:
                get_store().set_api_key_enabled(key_id, False)
                if progress:
                    progress(0, "Disabled an invalid API key — trying the next one…")
                continue


_pool: ApiKeyPool | None = None
_pool_lock = threading.Lock()


def get_key_pool() -> ApiKeyPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ApiKeyPool()
        return _pool
