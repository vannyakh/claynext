"""Contract tests for the SGLang-Omni provider. No live server."""
from __future__ import annotations

import json
import socket
import urllib.error
from unittest.mock import patch

from claynext.models.ai_provider import ProviderError
from claynext.models.sglang_omni import SGLangOmniProvider, reset_provider
from claynext.utils.job_control import JobCancelled, JobControl


class _Body:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _models(*ids: str) -> _Body:
    data = {"data": [{"id": item} for item in ids]}
    return _Body(json.dumps(data).encode())


def _provider() -> SGLangOmniProvider:
    reset_provider()
    return SGLangOmniProvider("http://sglang.test")


def test_whisper_only_server_transcribes_and_does_not_translate():
    provider = _provider()
    with patch("claynext.models.sglang_omni.urllib.request.urlopen", return_value=_models("openai/whisper-large-v3")):
        caps = provider.capabilities()
    assert caps.transcribe == "openai/whisper-large-v3"
    assert caps.translate is None
    assert caps.speak is None
    try:
        provider.complete("translate this")
        raise AssertionError("chat should be refused")
    except ProviderError as exc:
        assert exc.code == "capability"


def test_timeout_is_retried_once():
    provider = _provider()
    calls = {"n": 0}

    def _open(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _models("Qwen/Qwen2.5-7B-Instruct")
        if calls["n"] == 2:
            raise socket.timeout("slow")
        return _Body(json.dumps({
            "choices": [{"message": {"content": "{\"lines\":[]}"}}],
        }).encode())

    with patch("claynext.models.sglang_omni.urllib.request.urlopen", side_effect=_open):
        assert provider.capabilities().translate == "Qwen/Qwen2.5-7B-Instruct"
        text = provider.complete("hello")
    assert calls["n"] == 3
    assert "lines" in text


def test_cancel_before_the_request():
    provider = _provider()
    with patch("claynext.models.sglang_omni.urllib.request.urlopen", return_value=_models("Qwen/Qwen2.5-7B-Instruct")):
        provider.capabilities()
    control = JobControl()
    control.cancel()
    try:
        provider.complete("hello", control=control)
        raise AssertionError("cancel should stop the call")
    except JobCancelled:
        pass


def test_down_server_is_unavailable():
    provider = _provider()
    with patch(
        "claynext.models.sglang_omni.urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        assert provider.available() is False
        assert provider.capabilities().models == ()
