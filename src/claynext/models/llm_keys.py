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
from claynext.models.llm_providers import CHAT_ORDER, CHAT_PROVIDERS

PROVIDERS = (
    ("gemini", "Google Gemini"),
    *((pid, CHAT_PROVIDERS[pid]["label"]) for pid in CHAT_ORDER),
    ("huggingface", "Hugging Face"),
    ("elevenlabs", "ElevenLabs"),
)

_ENV_KEYS = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "huggingface": ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"),
    "elevenlabs": ("ELEVENLABS_API_KEY",),
    **{pid: spec["env"] for pid, spec in CHAT_PROVIDERS.items()},
}

# Free-tier speed each key is held to. Rotation moves on before the provider returns 429.
PROVIDER_LIMITS = {
    "gemini": {"rpm": 15, "rpd": 1500, "model": "gemini-2.0-flash"},
    "huggingface": {"rpm": 30, "rpd": 1000, "model": ""},
    "elevenlabs": {"rpm": 20, "rpd": 10000, "model": "eleven_multilingual_v2"},
    **{
        pid: {"rpm": spec["rpm"], "rpd": spec["rpd"], "model": spec["model"]}
        for pid, spec in CHAT_PROVIDERS.items()
    },
}

_usage_local = threading.local()


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


def note_llm_usage(model: str, payload: dict | None = None, *, tokens_in: int = 0, tokens_out: int = 0) -> None:
    """Remember the model and token counts for the key that is running this call."""
    tin, tout = int(tokens_in or 0), int(tokens_out or 0)
    if isinstance(payload, dict):
        meta = payload.get("usageMetadata") or payload.get("usage") or {}
        if isinstance(meta, dict):
            tin = int(meta.get("promptTokenCount") or meta.get("prompt_tokens") or tin or 0)
            tout = int(meta.get("candidatesTokenCount") or meta.get("completion_tokens") or tout or 0)
    _usage_local.model = str(model or "")
    _usage_local.tokens_in = max(0, tin)
    _usage_local.tokens_out = max(0, tout)


def take_llm_usage() -> tuple[str, int, int]:
    model = str(getattr(_usage_local, "model", "") or "")
    tin = int(getattr(_usage_local, "tokens_in", 0) or 0)
    tout = int(getattr(_usage_local, "tokens_out", 0) or 0)
    _usage_local.model = ""
    _usage_local.tokens_in = 0
    _usage_local.tokens_out = 0
    return model, tin, tout


def compact_tokens(count: int) -> str:
    n = max(0, int(count or 0))
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}k"
    return f"{n / 1_000_000:.1f}m"


def describe_key(row: dict[str, Any], usage: dict[str, Any] | None = None, *, now: datetime | None = None) -> dict[str, str]:
    """Health, model, tokens, speed limit, and current speed for one stored key."""
    usage = usage or {}
    provider = str(row.get("provider") or "")
    limits = PROVIDER_LIMITS.get(provider, {"rpm": 60, "rpd": 10000, "model": ""})
    rpm = int(limits["rpm"])
    calls = int(usage.get("calls_minute") or 0)
    fails = int(row.get("fail_count") or 0)
    enabled = int(row.get("enabled") or 0) == 1
    moment = now or _now()
    until = _parse_iso(row.get("cooldown_until") if isinstance(row.get("cooldown_until"), str) else None)
    if not enabled:
        health = "Off"
    elif until and until > moment:
        health = f"Cooling {int((until - moment).total_seconds())}s"
    elif calls >= rpm:
        health = "Limited"
    elif fails >= 8:
        health = "Worn"
    elif fails >= 3:
        health = "Shaky"
    elif calls >= max(1, int(rpm * 0.8)):
        health = "Busy"
    else:
        health = "Healthy"
    model = str(usage.get("last_model") or limits.get("model") or "") or "—"
    tokens_min = int(usage.get("tokens_minute") or 0)
    if tokens_min > 0:
        speed = f"{compact_tokens(tokens_min)}/m"
    elif calls > 0:
        speed = f"{calls} rpm"
    else:
        speed = "idle"
    return {
        "health": health,
        "model": model,
        "tokens": compact_tokens(int(usage.get("tokens_day") or 0)),
        "limit": f"{min(calls, rpm)}/{rpm}",
        "speed": speed,
    }


def keys_for_rust(rows: list[dict[str, Any]], *, provider: str = "", usage: dict[int, dict] | None = None) -> list[dict[str, Any]]:
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
        slot = (usage or {}).get(int(row["id"]), {})
        prov = str(row.get("provider") or provider or "")
        out.append(
            {
                "id": int(row["id"]),
                "provider": prov,
                "secret": secret,
                "label": str(row.get("label") or ""),
                "enabled": bool(int(enabled)) if not isinstance(enabled, bool) else enabled,
                "cooldown_until": cd_epoch,
                "fail_count": int(row.get("fail_count") or 0),
                "last_used_at": lu_epoch,
                "calls_minute": int(slot.get("calls_minute") or 0),
                "rpm_limit": int(PROVIDER_LIMITS.get(prov, {}).get("rpm") or 0),
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

    def update_key(self, key_id: int, *, provider: str, label: str, secret: str = "") -> None:
        get_store().update_api_key(
            key_id,
            provider=provider,
            label=label,
            secret=(secret or "").strip() or None,
        )

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

    def _under_limit(self, provider: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keys that still have speed left this minute. Saturated keys rotate off."""
        rpm = int(PROVIDER_LIMITS.get(provider, {}).get("rpm") or 0)
        if rpm <= 0:
            return rows
        usage = get_store().llm_usage(provider)
        open_rows = []
        for row in rows:
            calls = int(usage.get(int(row["id"]), {}).get("calls_minute") or 0)
            if calls < rpm:
                open_rows.append(row)
        return open_rows

    def _rpm_wait(self, provider: str) -> float:
        """Seconds until the busiest key frees one request in its minute window."""
        usage = get_store().llm_usage(provider)
        rpm = int(PROVIDER_LIMITS.get(provider, {}).get("rpm") or 0)
        if rpm <= 0:
            return 0.0
        now = _now()
        waits = []
        for row in self._ready_rows(provider):
            slot = usage.get(int(row["id"]), {})
            if int(slot.get("calls_minute") or 0) < rpm:
                return 0.0
            oldest = _parse_iso(slot.get("oldest_minute"))
            if oldest:
                waits.append(max(0.5, 60.0 - (now - oldest).total_seconds()))
        return min(waits) if waits else 0.0

    def acquire(self, provider: str) -> dict[str, Any] | None:
        with self._lock:
            rows = self._under_limit(provider, self._ready_rows(provider))
            if not rows:
                return None
            from claynext.adapters.ai import get_ai_adapter

            usage = get_store().llm_usage(provider)
            prepared = keys_for_rust(rows, provider=provider, usage=usage)
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
        rpm_wait = self._rpm_wait(provider)
        if rpm_wait > 0 and (rust_wait <= 0 or rpm_wait < rust_wait):
            return rpm_wait
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
            take_llm_usage()
            started = time.perf_counter()
            try:
                result = fn(str(row["secret"]))
                model, tokens_in, tokens_out = take_llm_usage()
                self.mark_ok(key_id)
                self._log_call(
                    key_id, provider, model, tokens_in, tokens_out,
                    ok=True, latency_ms=int((time.perf_counter() - started) * 1000),
                )
                return result
            except RateLimitError as exc:
                model, tokens_in, tokens_out = take_llm_usage()
                self.mark_rate_limited(key_id, exc.retry_after)
                self._log_call(
                    key_id, provider, model, tokens_in, tokens_out,
                    ok=False, latency_ms=int((time.perf_counter() - started) * 1000),
                )
                if progress:
                    progress(0, "Rate limit hit — rotating to the next API key…")
                continue
            except InvalidKeyError:
                get_store().set_api_key_enabled(key_id, False)
                if progress:
                    progress(0, "Disabled an invalid API key — trying the next one…")
                continue

    def _log_call(
        self, key_id: int, provider: str, model: str, tokens_in: int, tokens_out: int,
        *, ok: bool, latency_ms: int,
    ) -> None:
        try:
            get_store().log_llm_call(
                key_id, provider, model=model, tokens_in=tokens_in, tokens_out=tokens_out,
                ok=ok, latency_ms=latency_ms,
            )
        except Exception:
            return


_pool: ApiKeyPool | None = None
_pool_lock = threading.Lock()


def get_key_pool() -> ApiKeyPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ApiKeyPool()
        return _pool
