"""Provider-neutral chat request / response types, errors, and request tracing.

Translation code talks to ``LlmProvider.complete``; which platform answers is a detail of the
provider instance. Traces record ids, model, attempts, latency, tokens, and cost. They never
record API keys or prompt text (only a SHA-256 of the prompt).
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

# (url, headers, body bytes, timeout seconds) -> (status, headers, body bytes)
Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, dict[str, str], bytes]]

ERROR_CODES = ("auth", "rate_limit", "timeout", "server", "bad_request", "invalid_output", "network")
RETRYABLE = frozenset({"timeout", "server", "invalid_output", "network"})


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, code: str, provider: str, retry_after: float | None = None):
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass
class ChatRequest:
    messages: list[ChatMessage]
    model: str | None = None
    temperature: float = 0.3
    max_tokens: int | None = None
    # JSON Schema subset (see claynext.prompts.validator). When set, the reply must parse and validate.
    json_schema: dict[str, Any] | None = None
    schema_name: str = "reply"
    timeout: float = 90.0
    max_retries: int = 2
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    tags: dict[str, str] = field(default_factory=dict)

    def prompt_sha256(self) -> str:
        blob = json.dumps([asdict(m) for m in self.messages], ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float | None = None


@dataclass
class ChatResponse:
    text: str
    parsed: Any
    provider: str
    model: str
    usage: Usage
    trace_id: str
    attempts: int
    latency_ms: int


@dataclass(frozen=True)
class Pricing:
    """USD per one million tokens. Supplied by the caller; the gateway ships no price list."""
    input_per_million: float
    output_per_million: float

    def cost(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in * self.input_per_million + tokens_out * self.output_per_million) / 1_000_000


class LlmProvider(Protocol):
    provider_id: str

    def available(self) -> bool: ...

    def complete(self, request: ChatRequest, *, control: Any = None) -> ChatResponse: ...


class TraceLog:
    """Thread-safe in-memory trace, optionally appended to a JSONL file."""

    def __init__(self, path: str | Path | None = None, *, keep: int = 500):
        self.path = Path(path) if path else None
        self.keep = keep
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def record(self, **event: Any) -> None:
        event = {"at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **event}
        with self._lock:
            self._events.append(event)
            del self._events[:-self.keep]
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def events(self, trace_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self._events if trace_id is None or e.get("trace_id") == trace_id]

    def totals(self) -> dict[str, Any]:
        done = [e for e in self.events() if e.get("event") == "ok"]
        costs = [e["cost_usd"] for e in done if e.get("cost_usd") is not None]
        return {
            "calls": len(done),
            "tokens_in": sum(int(e.get("tokens_in") or 0) for e in done),
            "tokens_out": sum(int(e.get("tokens_out") or 0) for e in done),
            "cost_usd": round(sum(costs), 6) if costs else None,
            "failures": sum(1 for e in self.events() if e.get("event") == "error"),
        }
