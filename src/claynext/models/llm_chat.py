"""One chat call through a stored provider key, with the same rotation as Gemini."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from claynext.models.llm_keys import (
    InvalidKeyError,
    RateLimitError,
    get_key_pool,
    is_rate_limit,
    note_llm_usage,
    parse_retry_after,
)
from claynext.models.llm_providers import CHAT_PROVIDERS


def json_from_text(text: str):
    """Parse a model reply that is JSON, or JSON inside a fence."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
        raw = raw.strip()
    return json.loads(raw)


def chat_text(provider: str, prompt: str, *, progress=None, temperature: float = 0.4) -> str:
    """Send one prompt. The pool rotates keys and logs the model and tokens."""
    spec = CHAT_PROVIDERS.get(provider)
    if not spec:
        raise RuntimeError(f"Unknown LLM provider: {provider}")
    model = str(spec["model"])
    url = str(spec["base"]).rstrip("/") + "/chat/completions"

    def _do(api_key: str) -> str:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in (401, 403):
                raise InvalidKeyError(f"{model}: {exc.code}") from exc
            if is_rate_limit(exc.code, detail):
                raise RateLimitError(
                    f"{model}: rate limited", parse_retry_after(exc.headers, detail)
                ) from exc
            raise RuntimeError(f"{model}: {exc.code} {detail[:400]}") from exc
        note_llm_usage(model, raw if isinstance(raw, dict) else None)
        try:
            return str(raw["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"{model} returned no text.") from exc

    return get_key_pool().call_with_rotation(provider, _do, progress=progress)
