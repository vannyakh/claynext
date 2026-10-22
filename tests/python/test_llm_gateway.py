"""Tests for the LLM provider gateway. Fake transport and key runner; no network, no paid calls.

Run: PYTHONPATH=src .venv/bin/python tests/python/test_llm_gateway.py
"""
from __future__ import annotations

import json

from claynext.models.llm_chat import chat_through, last_chat
from claynext.models.llm_keys import InvalidKeyError
from claynext.models.llm_gateway import (
    ChatMessage,
    ChatRequest,
    OpenAICompatibleProvider,
    Pricing,
    ProviderError,
    TraceLog,
    get_provider,
)
from claynext.models.llm_providers import CHAT_PROVIDERS
from claynext.utils.job_control import JobCancelled, JobControl

SECRET = "sk-test-DO-NOT-LOG-1234567890"
SCHEMA = {
    "type": "object",
    "required": ["khmer"],
    "properties": {"khmer": {"type": "string", "minLength": 1}},
}


def _ok(content: str, tokens=(120, 30)) -> tuple[int, dict, bytes]:
    body = {"choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]}}
    return 200, {}, json.dumps(body).encode("utf-8")


class FakeTransport:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _runner(provider, fn):
    return fn(SECRET)


def _provider(transport, provider_id="openai", **kw) -> OpenAICompatibleProvider:
    sleeps: list[float] = []
    p = OpenAICompatibleProvider(provider_id, transport=transport, key_runner=_runner,
                                 sleep=sleeps.append, backoff=0.001, trace=TraceLog(), **kw)
    p.sleeps = sleeps
    return p


def _request(**kw) -> ChatRequest:
    return ChatRequest(messages=[ChatMessage("system", "Localize to Khmer."), ChatMessage("user", "Go home.")], **kw)


def _no_secret(provider: OpenAICompatibleProvider) -> None:
    assert SECRET not in json.dumps(provider.trace.events())


def test_openai_is_already_a_chat_provider():
    assert "openai" in CHAT_PROVIDERS and CHAT_PROVIDERS["openai"]["base"] == "https://api.openai.com/v1"
    assert get_provider("openai").model == CHAT_PROVIDERS["openai"]["model"]
    try:
        get_provider("nope")
        raise AssertionError("unknown provider must fail")
    except ValueError:
        pass


def test_structured_reply_usage_cost_and_trace():
    t = FakeTransport(_ok('{"khmer": "ទៅផ្ទះ"}'))
    p = _provider(t, pricing={"gpt-test": Pricing(1.0, 4.0)})
    resp = p.complete(_request(json_schema=SCHEMA, model="gpt-test", tags={"job": "unit"}))
    assert resp.parsed == {"khmer": "ទៅផ្ទះ"} and resp.attempts == 1
    assert (resp.usage.tokens_in, resp.usage.tokens_out) == (120, 30)
    assert abs(resp.usage.cost_usd - (120 * 1.0 + 30 * 4.0) / 1e6) < 1e-12
    call = t.calls[0]
    assert call["url"] == "https://api.openai.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert call["body"]["response_format"]["type"] == "json_schema"
    assert call["body"]["response_format"]["json_schema"]["schema"] == SCHEMA
    events = p.trace.events(resp.trace_id)
    assert [e["event"] for e in events] == ["ok"] and events[0]["job"] == "unit"
    assert "Go home" not in json.dumps(events) and len(events[0]["prompt_sha256"]) == 64
    assert p.trace.totals()["tokens_in"] == 120
    _no_secret(p)


def test_cost_is_unknown_without_pricing():
    p = _provider(FakeTransport(_ok("ទៅផ្ទះ")))
    assert p.complete(_request()).usage.cost_usd is None


def test_invalid_output_is_retried_then_accepted():
    t = FakeTransport(_ok("not json"), _ok('{"khmer": ""}'), _ok('{"khmer": "បាទ"}'))
    p = _provider(t)
    resp = p.complete(_request(json_schema=SCHEMA, max_retries=2))
    assert resp.parsed == {"khmer": "បាទ"} and resp.attempts == 3
    codes = [e.get("code") for e in p.trace.events() if e["event"] == "error"]
    assert codes == ["invalid_output", "invalid_output"] and p.sleeps


def test_server_errors_exhaust_retries():
    t = FakeTransport(*[(503, {}, b"overloaded")] * 3)
    p = _provider(t)
    try:
        p.complete(_request(max_retries=2))
        raise AssertionError("expected ProviderError")
    except ProviderError as exc:
        assert exc.code == "server"
    assert len(t.calls) == 3 and p.trace.events()[-1]["final"] is True


def test_timeouts_are_retried():
    t = FakeTransport(ProviderError("timed out", code="timeout", provider="http"), _ok("ok"))
    p = _provider(t)
    assert p.complete(_request()).attempts == 2


def test_bad_request_is_not_retried_and_key_is_redacted():
    body = json.dumps({"error": {"message": f"Incorrect API key provided: {SECRET}"}}).encode()
    t = FakeTransport((400, {}, body))
    p = _provider(t)
    try:
        p.complete(_request())
        raise AssertionError("expected ProviderError")
    except ProviderError as exc:
        assert exc.code == "bad_request" and SECRET not in str(exc)
    assert len(t.calls) == 1
    _no_secret(p)


def test_rate_limit_and_auth_map_to_provider_errors():
    for status, code in ((429, "rate_limit"), (401, "auth")):
        p = _provider(FakeTransport((status, {"Retry-After": "7"}, b"{}")))
        try:
            p.complete(_request())
            raise AssertionError("expected ProviderError")
        except ProviderError as exc:
            assert exc.code == code
            if code == "rate_limit":
                assert exc.retry_after == 7.0


def test_cancellation_before_and_during_backoff():
    control = JobControl()
    control.cancel()
    t = FakeTransport(_ok("x"))
    try:
        _provider(t).complete(_request(), control=control)
        raise AssertionError("expected JobCancelled")
    except JobCancelled:
        assert t.calls == []

    control = JobControl()
    t = FakeTransport((500, {}, b""), _ok("x"))
    p = OpenAICompatibleProvider("openai", transport=t, key_runner=_runner, backoff=5.0,
                                 sleep=lambda s: control.cancel())
    try:
        p.complete(_request(), control=control)
        raise AssertionError("expected JobCancelled")
    except JobCancelled:
        assert len(t.calls) == 1


def test_chat_through_returns_text_and_trace():
    t = FakeTransport(_ok("ទៅផ្ទះ"))
    provider = _provider(t)
    text = chat_through(provider, "Go home.", temperature=0.2)
    assert text == "ទៅផ្ទះ"
    last = last_chat()
    assert last is not None and last.trace_id
    assert t.calls[0]["body"]["temperature"] == 0.2
    assert t.calls[0]["body"]["messages"][0]["content"] == "Go home."


def test_chat_through_maps_auth_to_invalid_key():
    class Boom:
        def complete(self, request, control=None):
            raise ProviderError("no key", code="auth", provider="openai")

    try:
        chat_through(Boom(), "x")
        raise AssertionError("expected InvalidKeyError")
    except InvalidKeyError as exc:
        assert "no key" in str(exc)


def test_other_providers_use_json_object_mode():
    t = FakeTransport(_ok('{"khmer": "បាទ"}'))
    p = _provider(t, provider_id="deepseek")
    p.complete(_request(json_schema=SCHEMA))
    assert t.calls[0]["body"]["response_format"] == {"type": "json_object"}
    assert t.calls[0]["url"].startswith(CHAT_PROVIDERS["deepseek"]["base"])


if __name__ == "__main__":
    import sys
    import traceback

    failed = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
