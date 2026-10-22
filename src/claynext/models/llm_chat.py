"""One chat call through a stored provider key, with the same rotation as Gemini.

The call goes through the provider gateway (retries, schema checks, traces). The
return value is still the reply text. ``last_chat()`` is the gateway response for
the call on this thread, including its trace id.
"""
from __future__ import annotations

import contextvars
import json

from claynext.models.llm_keys import (
    InvalidKeyError,
    RateLimitError,
    get_key_pool,
)

_LAST: contextvars.ContextVar = contextvars.ContextVar("claynext_last_chat", default=None)


def last_chat():
    """Gateway response from the latest ``chat_text`` on this thread, or None."""
    return _LAST.get()


def json_from_text(text: str):
    """Parse a model reply that is JSON, or JSON inside a fence."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
        raw = raw.strip()
    return json.loads(raw)


def chat_through(gateway, prompt: str, *, temperature: float = 0.4) -> str:
    """One prompt through an existing gateway provider. Same text result as ``chat_text``."""
    from claynext.models.llm_gateway import ChatMessage, ChatRequest
    from claynext.models.llm_gateway.base import ProviderError

    request = ChatRequest(
        messages=[ChatMessage("user", prompt)],
        temperature=temperature,
    )
    try:
        response = gateway.complete(request)
    except ProviderError as exc:
        raise _legacy_error(exc) from exc
    _LAST.set(response)
    return response.text


def chat_text(provider: str, prompt: str, *, progress=None, temperature: float = 0.4) -> str:
    """Send one prompt. The pool rotates keys; the gateway retries and records a trace."""
    from claynext.models.llm_gateway import get_provider

    def runner(provider_id: str, fn):
        return get_key_pool().call_with_rotation(provider_id, fn, progress=progress)

    return chat_through(get_provider(provider, key_runner=runner), prompt, temperature=temperature)


def _legacy_error(exc) -> Exception:
    """Map a gateway error back to the exceptions ``chat_text`` callers already catch."""
    if exc.code == "rate_limit":
        return RateLimitError(str(exc), exc.retry_after)
    if exc.code == "auth":
        return InvalidKeyError(str(exc))
    return RuntimeError(str(exc))
