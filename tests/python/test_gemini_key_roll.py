"""Gemini key rotation and Jev ranking. Fakes only. No network and no live key.

Run:
  KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python tests/python/test_gemini_key_roll.py
"""
from __future__ import annotations

import io
import json
import os
import urllib.error
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from claynext.models.jev_decisions import rank_khmer_candidates
from claynext.models.khmer_spoken.providers.google_gemini_provider import GeminiTeacherProvider
from claynext.models.khmer_spoken.schema import DialogueExample, TranslationCandidate
from claynext.models.khmer_spoken.training.ranked_export import export_ranked_training
from claynext.models.llm_keys import ApiKeyPool, InvalidKeyError, RateLimitError, is_rate_limit
from claynext.models.training.config import CONFIG_DIR
from claynext.models.training.trainer import start


class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def migrate_legacy_api_keys(self):
        return None

    def list_api_keys(self, provider=None):
        if provider:
            return [row for row in self.rows if row["provider"] == provider]
        return list(self.rows)

    def update_api_key_state(self, key_id, **kwargs):
        for row in self.rows:
            if int(row["id"]) != int(key_id):
                continue
            if kwargs.get("clear_cooldown"):
                row["cooldown_until"] = None
            elif kwargs.get("cooldown_until") is not None:
                row["cooldown_until"] = kwargs["cooldown_until"]
            if kwargs.get("fail_count") is not None:
                row["fail_count"] = kwargs["fail_count"]
            if kwargs.get("last_used_at") is not None:
                row["last_used_at"] = kwargs["last_used_at"]

    def set_api_key_enabled(self, key_id, enabled):
        for row in self.rows:
            if int(row["id"]) == int(key_id):
                row["enabled"] = 1 if enabled else 0

    def llm_usage(self, provider):
        return {}

    def log_llm_call(self, *args, **kwargs):
        return None


class FakeAdapter:
    def acquire_llm_key(self, keys, provider):
        return None

    def soonest_cooldown(self, keys, provider):
        return 0.0

    def parse_retry_after(self, status, header=None, body=""):
        return False, 20.0


def _iso_after(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _row(key_id: int, secret: str, *, cooldown: str | None = None) -> dict:
    return {
        "id": key_id,
        "provider": "gemini",
        "label": f"slot-{key_id}",
        "secret": secret,
        "enabled": 1,
        "cooldown_until": cooldown,
        "fail_count": 0,
        "last_used_at": None,
    }


def _call(rows, fn, *, on_sleep=None):
    sleeps: list[float] = []
    store = FakeStore(rows)

    def _sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if on_sleep:
            on_sleep(store)

    with patch("claynext.models.llm_keys.get_store", return_value=store), patch(
        "claynext.models.llm_keys.time.sleep", side_effect=_sleep
    ), patch("claynext.adapters.ai.get_ai_adapter", return_value=FakeAdapter()), patch.dict(
        os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=False
    ):
        pool = ApiKeyPool()
        try:
            result = pool.call_with_rotation("gemini", fn)
        except RuntimeError as exc:
            return sleeps, str(exc), None
        return sleeps, "", result


def test_503_and_overload_text_roll_keys():
    assert is_rate_limit(503, "UNAVAILABLE") is True
    assert is_rate_limit(503, "") is True
    assert is_rate_limit(429, "") is True
    assert is_rate_limit(200, "The model is overloaded. high demand") is True
    assert is_rate_limit(400, "invalid argument") is False


def test_cooling_key_is_skipped():
    seen: list[str] = []

    def fn(secret: str) -> str:
        seen.append(secret)
        return "ok"

    sleeps, err, result = _call(
        [
            _row(1, "cooling-slot", cooldown=_iso_after(90)),
            _row(2, "ready-slot"),
        ],
        fn,
    )
    assert err == ""
    assert result == "ok"
    assert seen == ["ready-slot"]
    assert sleeps == []


def test_all_cooling_waits_once_then_uses_a_key():
    seen: list[str] = []

    def fn(secret: str) -> str:
        seen.append(secret)
        return "ok"

    def _clear(store: FakeStore) -> None:
        for row in store.rows:
            row["cooldown_until"] = None

    sleeps, err, result = _call(
        [
            _row(1, "slot-a", cooldown=_iso_after(70)),
            _row(2, "slot-b", cooldown=_iso_after(120)),
        ],
        fn,
        on_sleep=_clear,
    )
    assert err == ""
    assert result == "ok"
    assert len(sleeps) == 1
    assert 60 <= sleeps[0] <= 80
    assert seen == ["slot-a"]


def test_all_cooling_does_not_spin_or_claim_no_key():
    def fn(secret: str) -> str:
        raise RateLimitError("busy", retry_after=30)

    sleeps, err, result = _call(
        [_row(1, "slot-a"), _row(2, "slot-b"), _row(3, "slot-c"), _row(4, "slot-d")],
        fn,
    )
    assert result is None
    assert len(sleeps) == 1
    assert sleeps[0] <= 180
    assert "cooling" in err
    assert "No available" not in err
    assert "slot-a" not in err


def test_untried_ready_key_runs_before_the_cooldown_wait():
    """A picker that prefers low fail counts must still reach the other ready key."""
    rows = [_row(1, "worn-slot"), _row(2, "fresh-a"), _row(3, "fresh-b")]
    rows[0]["fail_count"] = 10
    seen: list[str] = []

    def fn(secret: str) -> str:
        seen.append(secret)
        if secret != "worn-slot":
            raise RateLimitError("busy", retry_after=30)
        return "ok"

    store = FakeStore(rows)

    def prefer_low_failures(self, provider):
        del self, provider
        ready = []
        now = datetime.now(timezone.utc)
        for row in store.rows:
            until = row.get("cooldown_until")
            if until:
                moment = datetime.fromisoformat(until)
                if moment.tzinfo is None:
                    moment = moment.replace(tzinfo=timezone.utc)
                if moment > now:
                    continue
            ready.append(row)
        if not ready:
            return None
        ready.sort(key=lambda row: (int(row["fail_count"]), int(row["id"])))
        return ready[0]

    with patch("claynext.models.llm_keys.get_store", return_value=store), patch(
        "claynext.models.llm_keys.time.sleep"
    ) as sleep, patch("claynext.adapters.ai.get_ai_adapter", return_value=FakeAdapter()), patch(
        "claynext.models.llm_keys.ApiKeyPool.acquire", prefer_low_failures
    ), patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=False):
        result = ApiKeyPool().call_with_rotation("gemini", fn)
    assert result == "ok"
    assert seen == ["fresh-a", "fresh-b", "worn-slot"]
    assert sleep.call_count == 0


def test_rejected_keys_stop_without_the_secret():
    def fn(secret: str) -> str:
        raise InvalidKeyError("rejected")

    sleeps, err, result = _call([_row(1, "slot-a"), _row(2, "slot-b")], fn)
    assert result is None
    assert sleeps == []
    assert "rejected" in err
    assert "slot-a" not in err
    assert "slot-b" not in err


def test_provider_sees_enabled_keys_while_they_cool():
    store = FakeStore([_row(1, "slot-a", cooldown=_iso_after(30))])
    with patch("claynext.models.llm_keys.get_store", return_value=store), patch.dict(
        os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=False
    ):
        pool = ApiKeyPool()
        assert pool.has_enabled("gemini") is True
        assert pool.secrets("gemini") == []
        with patch("claynext.models.llm_keys.get_key_pool", return_value=pool):
            assert GeminiTeacherProvider().available() is True


class _Resp:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_http_503_tries_the_next_key():
    tried: list[str] = []

    class Pool:
        def call_with_rotation(self, provider, fn, **kwargs):
            last = None
            for secret in ("slot-a", "slot-b"):
                tried.append(secret)
                try:
                    return fn(secret)
                except RateLimitError as exc:
                    last = exc
            raise last

    state = {"n": 0}

    def urlopen(req, timeout=90):
        state["n"] += 1
        if state["n"] == 1:
            raise urllib.error.HTTPError(
                req.full_url,
                503,
                "unavailable",
                Message(),
                io.BytesIO(b'{"error":{"status":"UNAVAILABLE","message":"high demand"}}'),
            )
        return _Resp({
            "candidates": [{"content": {"parts": [{"text": "សួស្តី"}]}}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2},
        })

    with patch("claynext.models.llm_keys.get_key_pool", return_value=Pool()), patch(
        "urllib.request.urlopen", urlopen
    ), patch(
        "claynext.models.translate_service.TranslateEngine._pace_gemini",
        staticmethod(lambda api_key="": None),
    ):
        text = GeminiTeacherProvider._generate_text(
            "gemini-flash-latest", "hello", generation={"temperature": 0.2}, progress_callback=None
        )
    assert text == "សួស្តី"
    assert tried == ["slot-a", "slot-b"]
    assert "slot-a" not in text


def test_read_timeout_tries_the_next_key():
    tried: list[str] = []

    class Pool:
        def call_with_rotation(self, provider, fn, **kwargs):
            last = None
            for secret in ("slot-a", "slot-b"):
                tried.append(secret)
                try:
                    return fn(secret)
                except RateLimitError as exc:
                    last = exc
            raise last

    state = {"n": 0}

    class _TimeoutResp:
        def read(self):
            raise TimeoutError("The read operation timed out")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def urlopen(req, timeout=90):
        state["n"] += 1
        if state["n"] == 1:
            return _TimeoutResp()
        return _Resp({
            "candidates": [{"content": {"parts": [{"text": "សួស្តី"}]}}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2},
        })

    with patch("claynext.models.llm_keys.get_key_pool", return_value=Pool()), patch(
        "urllib.request.urlopen", urlopen
    ), patch(
        "claynext.models.translate_service.TranslateEngine._pace_gemini",
        staticmethod(lambda api_key="": None),
    ):
        text = GeminiTeacherProvider._generate_text(
            "gemini-flash-latest", "hello", generation={"temperature": 0.2}, progress_callback=None
        )
    assert text == "សួស្តី"
    assert tried == ["slot-a", "slot-b"]
    assert "slot-a" not in text


def _draft(**kwargs) -> DialogueExample:
    base = dict(
        id="kp-test",
        source_text="I am going home.",
        speaker_id="child",
        listener_id="mother",
        relationship="child_to_parent",
        origin="gemini_teacher",
        license_type="unknown",
        review_status="approved",
        approved_text="ខ្ញុំទៅផ្ទះ",
        candidates=[
            TranslationCandidate(text="ខ្ញុំទៅផ្ទះ", style="natural", provider="gemini_teacher"),
            TranslationCandidate(text="ចៅទៅផ្ទះហើយ", style="character", provider="gemini_teacher"),
            TranslationCandidate(text="ទៅផ្ទះ", style="slang", provider="gemini_teacher"),
        ],
    )
    base.update(kwargs)
    return DialogueExample(**base)


def _answers(choice="1", confidence=0.91, weak=None) -> dict:
    weak = weak or set()
    out = {
        "best": {"type": "choice", "choice": choice, "confidence": confidence},
    }
    for index in range(3):
        low = index in weak
        value = 0.2 if low else 0.8 + (0.05 * (index == 1))
        for name in ("meaning", "natural", "pronoun"):
            out[f"{name}_{index}"] = {"type": "noul", "noul": value}
    return out


def test_jev_ranks_without_overriding_approved_text():
    ex = _draft()
    seen: dict = {}

    def ask(state, questions):
        seen["questions"] = questions
        return _answers()

    result = rank_khmer_candidates(ex, ask=ask)
    assert result["applied"] is True
    assert result["preferred_text"] == "ចៅទៅផ្ទះហើយ"
    assert ex.approved_text == "ខ្ញុំទៅផ្ទះ"
    assert ex.review_status == "approved"
    assert ex.license_type == "unknown"
    assert [cand.text for cand in ex.candidates] == ["ខ្ញុំទៅផ្ទះ", "ចៅទៅផ្ទះហើយ", "ទៅផ្ទះ"]
    assert ex.preferred_khmer() == "ខ្ញុំទៅផ្ទះ"
    assert ex.training_khmer() == "ចៅទៅផ្ទះហើយ"
    for spec in seen["questions"].values():
        assert "I am going home." in spec["instructions"]
        assert "meaning_0" not in spec["instructions"]


def test_jev_drops_a_low_noul_and_ignores_a_weak_choice():
    ex = _draft(approved_text="")
    result = rank_khmer_candidates(ex, ask=lambda state, questions: _answers(choice="0", confidence=0.2, weak={0}))
    assert result["applied"] is True
    assert result["preferred_index"] != 0
    assert ex.metadata["jev"]["scores"][0]["keep"] is False
    assert ex.approved_text == ""


def test_jev_failure_and_missing_key_leave_the_row():
    ex = _draft()

    def ask(state, questions):
        raise RuntimeError("down")

    failed = rank_khmer_candidates(ex, ask=ask)
    assert failed["reason"] == "error"
    assert "jev" not in ex.metadata
    assert ex.approved_text == "ខ្ញុំទៅផ្ទះ"
    with patch("claynext.models.jev_decisions.jev_key_configured", return_value=False):
        missing = rank_khmer_candidates(ex)
    assert missing["reason"] == "no_key"
    assert "jev" not in ex.metadata


def test_ranked_export_uses_the_jev_line_and_14b_stays_refused(tmp: Path):
    ex = _draft()
    rank_khmer_candidates(ex, ask=lambda state, questions: _answers())
    dest = tmp / "ranked.jsonl"
    report = export_ranked_training([ex], dest)
    line = json.loads(dest.read_text(encoding="utf-8").splitlines()[0])
    assert report["count"] == 1
    assert report["weights_written"] is False
    assert line["target"] == "ចៅទៅផ្ទះហើយ"
    assert line["license_type"] == "unknown"
    refused = start(CONFIG_DIR / "qlora_14b.yaml", approval=True)
    assert refused["status"] == "refused"
    assert refused["started"] is False
    assert refused["weights"] is None


if __name__ == "__main__":
    import sys
    import tempfile
    import traceback

    failed = 0
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        for name, fn in tests:
            try:
                if name == "test_ranked_export_uses_the_jev_line_and_14b_stays_refused":
                    fn(tmp)
                else:
                    fn()
                print(f"PASS {name}")
            except Exception:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
