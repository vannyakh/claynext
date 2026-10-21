"""OpenAI-compatible chat provider (OpenAI, and any ``CHAT_PROVIDERS`` entry) over stdlib urllib.

- Keys come from the existing rotating pool (``llm_keys.get_key_pool``): 429 rotates keys,
  401/403 disables the bad key, exactly as ``llm_chat.chat_text`` does.
- Timeouts, 5xx, network errors, and replies that fail the JSON schema are retried with
  exponential backoff up to ``request.max_retries``.
- ``control`` is a ``JobControl``; it is checked before every attempt and during backoff.
  An HTTP call already in flight is bounded by ``request.timeout``, not interrupted.
- Keys never reach traces, errors, or logs; provider error text is redacted.
"""
from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from claynext.models.llm_gateway.base import (
    ChatRequest,
    ChatResponse,
    Pricing,
    ProviderError,
    TraceLog,
    Transport,
    Usage,
)
from claynext.utils.job_control import JobCancelled

# Providers known to accept response_format json_schema; others get json_object.
JSON_SCHEMA_PROVIDERS = frozenset({"openai"})
_KEY_PATTERN = re.compile(r"\b(sk|gsk|xai)-[A-Za-z0-9_\-\*\.]{4,}")

KeyRunner = Callable[[str, Callable[[str], Any]], Any]


def urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()) if exc.headers else {}, exc.read()
    except (socket.timeout, TimeoutError) as exc:
        raise ProviderError("request timed out", code="timeout", provider="http") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise ProviderError("request timed out", code="timeout", provider="http") from exc
        raise ProviderError(f"network error: {exc.reason}", code="network", provider="http") from exc


def _pool_runner(provider: str, fn: Callable[[str], Any]) -> Any:
    from claynext.models.llm_keys import get_key_pool

    return get_key_pool().call_with_rotation(provider, fn)


def redact(text: str, secret: str = "") -> str:
    out = text.replace(secret, "***") if secret else text
    return _KEY_PATTERN.sub(lambda m: f"{m.group(1)}-***", out)


def _retry_after(headers: dict[str, str]) -> float | None:
    for name, value in headers.items():
        if name.lower() == "retry-after":
            try:
                return float(value)
            except ValueError:
                return None
    return None


class OpenAICompatibleProvider:
    def __init__(
        self,
        provider_id: str = "openai",
        *,
        model: str | None = None,
        base_url: str | None = None,
        transport: Transport | None = None,
        key_runner: KeyRunner | None = None,
        pricing: dict[str, Pricing] | None = None,
        trace: TraceLog | None = None,
        backoff: float = 1.5,
        sleep: Callable[[float], None] = time.sleep,
    ):
        from claynext.models.llm_providers import CHAT_PROVIDERS

        spec = CHAT_PROVIDERS.get(provider_id)
        if spec is None and not (model and base_url):
            raise ValueError(f"Unknown chat provider {provider_id!r}; pass model and base_url.")
        spec = spec or {}
        self.provider_id = provider_id
        self.model = model or str(spec["model"])
        self.base_url = (base_url or str(spec["base"])).rstrip("/")
        self._transport = transport or urllib_transport
        self._key_runner = key_runner or _pool_runner
        self.pricing = dict(pricing or {})
        self.trace = trace or TraceLog()
        self._backoff = backoff
        self._sleep = sleep

    def available(self) -> bool:
        from claynext.models.llm_keys import get_key_pool

        return get_key_pool().ready_count(self.provider_id) > 0

    def _body(self, request: ChatRequest, model: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens:
            body["max_tokens"] = request.max_tokens
        if request.json_schema is not None:
            if self.provider_id in JSON_SCHEMA_PROVIDERS:
                body["response_format"] = {"type": "json_schema", "json_schema": {
                    "name": request.schema_name, "schema": request.json_schema, "strict": False}}
            else:
                body["response_format"] = {"type": "json_object"}
        return body

    def _send(self, api_key: str, body: dict[str, Any], timeout: float) -> tuple[str, dict[str, Any]]:
        from claynext.models.llm_keys import InvalidKeyError, RateLimitError, note_llm_usage

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        try:
            status, resp_headers, raw = self._transport(
                f"{self.base_url}/chat/completions", headers, json.dumps(body).encode("utf-8"), timeout)
        except ProviderError as exc:
            raise ProviderError(str(exc), code=exc.code, provider=self.provider_id) from None
        detail = redact(raw.decode("utf-8", errors="replace")[:400], api_key)
        if status in (401, 403):
            raise InvalidKeyError(f"{self.provider_id}: {status}")
        if status == 429:
            raise RateLimitError(f"{self.provider_id}: rate limited", _retry_after(resp_headers))
        if status >= 500:
            raise ProviderError(f"{status} {detail}", code="server", provider=self.provider_id)
        if status >= 400:
            raise ProviderError(f"{status} {detail}", code="bad_request", provider=self.provider_id)
        try:
            payload = json.loads(raw.decode("utf-8"))
            text = str(payload["choices"][0]["message"]["content"] or "")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("reply has no message content", code="server", provider=self.provider_id) from exc
        note_llm_usage(body["model"], payload)
        return text, payload

    def _parse(self, text: str, request: ChatRequest) -> Any:
        from claynext.models.llm_chat import json_from_text
        from claynext.prompts.validator import schema_errors

        try:
            parsed = json_from_text(text)
        except ValueError as exc:
            raise ProviderError(f"reply is not JSON: {exc}", code="invalid_output", provider=self.provider_id) from exc
        errors = schema_errors(request.json_schema or {}, parsed)
        if errors:
            raise ProviderError("reply failed schema: " + "; ".join(errors[:3]),
                                code="invalid_output", provider=self.provider_id)
        return parsed

    def _wait(self, seconds: float, control: Any) -> None:
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            if control is not None:
                control.checkpoint()
            self._sleep(min(0.2, left))

    def complete(self, request: ChatRequest, *, control: Any = None) -> ChatResponse:
        from claynext.models.llm_keys import InvalidKeyError, RateLimitError

        model = request.model or self.model
        body = self._body(request, model)
        base_event = {"trace_id": request.trace_id, "provider": self.provider_id, "model": model,
                      "prompt_sha256": request.prompt_sha256(), **request.tags}
        started = time.perf_counter()
        attempt = 0
        while True:
            if control is not None:
                control.checkpoint()
            attempt += 1
            t0 = time.perf_counter()
            try:
                text, payload = self._key_runner(
                    self.provider_id, lambda key: self._send(key, body, request.timeout))
                parsed = self._parse(text, request) if request.json_schema is not None else None
            except ProviderError as exc:
                err = exc
            except RateLimitError as exc:
                err = ProviderError(str(exc), code="rate_limit", provider=self.provider_id,
                                    retry_after=exc.retry_after)
            except InvalidKeyError as exc:
                err = ProviderError(str(exc), code="auth", provider=self.provider_id)
            except JobCancelled:
                raise
            except RuntimeError as exc:
                # Raised by the key pool when no key is usable.
                err = ProviderError(redact(str(exc)), code="auth", provider=self.provider_id)
            else:
                meta = payload.get("usage") or {}
                usage = Usage(int(meta.get("prompt_tokens") or 0), int(meta.get("completion_tokens") or 0))
                price = self.pricing.get(model)
                usage.cost_usd = price.cost(usage.tokens_in, usage.tokens_out) if price else None
                latency = int((time.perf_counter() - started) * 1000)
                self.trace.record(event="ok", attempt=attempt, tokens_in=usage.tokens_in,
                                  tokens_out=usage.tokens_out, cost_usd=usage.cost_usd,
                                  latency_ms=int((time.perf_counter() - t0) * 1000), **base_event)
                return ChatResponse(text=text, parsed=parsed, provider=self.provider_id, model=model,
                                    usage=usage, trace_id=request.trace_id, attempts=attempt, latency_ms=latency)
            final = not err.retryable or attempt > request.max_retries
            self.trace.record(event="error", attempt=attempt, code=err.code, error=str(err)[:300],
                              final=final, latency_ms=int((time.perf_counter() - t0) * 1000), **base_event)
            if final:
                raise err
            self._wait(self._backoff * (2 ** (attempt - 1)), control)
