"""
Rolling LLM API key pool.

On HTTP 429 / RESOURCE_EXHAUSTED, the current key is put on cooldown and the
next enabled key is used. If every key is cooling, wait for the soonest one.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from claynext.controllers.store import get_store

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
    raw = ""
    if headers:
        try:
            raw = headers.get("Retry-After") or headers.get("retry-after") or ""
        except Exception:
            raw = ""
    from claynext.adapters.ai import get_ai_adapter

    _, retry_after = get_ai_adapter().parse_retry_after(429, header=raw, body=body)
    return retry_after


def is_rate_limit(status: int, body: str = "") -> bool:
    from claynext.adapters.ai import get_ai_adapter

    limited, _ = get_ai_adapter().parse_retry_after(status, body=body)
    return limited


def keys_for_rust(rows: list[dict[str, Any]], *, provider: str = "") -> list[dict[str, Any]]:
    """Normalize store rows for claynext-ai (bool enabled, epoch cooldowns)."""
    out: list[dict[str, Any]] = []
    for row in rows:
        secret = str(row.get("secret") or "").strip()
        if not secret:
            continue
        cooldown = _parse_iso(row.get("cooldown_until") if isinstance(row.get("cooldown_until"), str) else None)
        last_used = _parse_iso(row.get("last_used_at") if isinstance(row.get("last_used_at"), str) else None)
        # Already-normalized epoch floats pass through.
        raw_cd = row.get("cooldown_until")
        raw_lu = row.get("last_used_at")
        if isinstance(raw_cd, (int, float)):
            cd_epoch = float(raw_cd)
        else:
            cd_epoch = cooldown.timestamp() if cooldown else None
        if isinstance(raw_lu, (int, float)):
            lu_epoch = float(raw_lu)
        else:
            lu_epoch = last_used.timestamp() if last_used else None
        enabled = row.get("enabled", 1)
        out.append(
            {
                "id": int(row["id"]),
                "provider": str(row.get("provider") or provider or ""),
                "secret": secret,
                "label": str(row.get("label") or ""),
                "enabled": bool(int(enabled)) if not isinstance(enabled, bool) else enabled,
                "cooldown_until": cd_epoch,
                "fail_count": int(row.get("fail_count") or 0),
                "last_used_at": lu_epoch,
            }
        )
    return out


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

    def ready_count(self, provider: str) -> int:
        return len(self._ready_rows(provider)) or len(
            [e for env in _ENV_KEYS.get(provider, ()) if (e := os.environ.get(env, "").strip())]
        )

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
            from claynext.adapters.ai import get_ai_adapter

            prepared = keys_for_rust(rows, provider=provider)
            rust_chosen = get_ai_adapter().acquire_llm_key(prepared, provider)
            if rust_chosen and rust_chosen.get("id") is not None:
                # Map back to store row (keep original secret/metadata).
                chosen_id = int(rust_chosen["id"])
                chosen = next((r for r in rows if int(r["id"]) == chosen_id), rows[0])
            else:
                start = self._cursor.get(provider, 0) % len(rows)
                ordered = rows[start:] + rows[:start]
                chosen = ordered[0]
                self._cursor[provider] = (start + 1) % len(rows)

            get_store().update_api_key_state(int(chosen["id"]), last_used_at=_now().isoformat())
            return chosen

    def mark_ok(self, key_id: int):
        get_store().update_api_key_state(key_id, fail_count=0, clear_cooldown=True)

    def mark_rate_limited(self, key_id: int, retry_after: float | None = None):
        row = next((r for r in self.list_keys() if int(r["id"]) == key_id), None)
        fails = int(row["fail_count"]) + 1 if row else 1
        # Exponential backoff grows with repeated hits on the same key.
        base = float(retry_after or 20.0)
        wait = max(6.0, min(180.0, base * (1.35 ** max(0, fails - 1))))
        until = (_now() + timedelta(seconds=wait)).isoformat()
        get_store().update_api_key_state(key_id, cooldown_until=until, fail_count=fails)

    def soonest_cooldown(self, provider: str) -> float:
        from claynext.adapters.ai import get_ai_adapter

        prepared = keys_for_rust(self.list_keys(provider), provider=provider)
        rust_wait = get_ai_adapter().soonest_cooldown(prepared, provider)
        if rust_wait > 0:
            return rust_wait

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
        max_wait: float = 45.0,
        max_cooldown_waits: int = 3,
    ) -> Any:
        """
        Call fn(secret). On RateLimitError rotate keys. Wait for cooldown a few
        times if the whole pool is cooling — keeps long translate jobs moving.
        """
        tried: set[int] = set()
        waits_used = 0
        while True:
            row = self.acquire(provider)
            if row is None:
                wait = self.soonest_cooldown(provider)
                if wait > 0 and waits_used < max_cooldown_waits:
                    pause = min(max_wait, wait + 0.35)
                    if progress:
                        progress(
                            0,
                            f"Rate limited — waiting {pause:.0f}s then rotating keys "
                            f"({waits_used + 1}/{max_cooldown_waits})…",
                        )
                    time.sleep(pause)
                    waits_used += 1
                    tried.clear()
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
            if key_id in tried and waits_used >= max_cooldown_waits:
                raise RuntimeError(f"All {provider} keys are rate-limited right now.")
            if key_id in tried:
                # Already tried this key in this wave — wait for a cooler key.
                wait = self.soonest_cooldown(provider)
                if wait > 0 and waits_used < max_cooldown_waits:
                    pause = min(max_wait, wait + 0.35)
                    if progress:
                        progress(0, f"Rotating keys — brief pause {pause:.0f}s…")
                    time.sleep(pause)
                    waits_used += 1
                    tried.clear()
                    continue
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
