"""Dataset test-split evaluation. Fake translator and gateway; no network."""
from __future__ import annotations

import json
from pathlib import Path

from claynext.models.datasets.schema import Candidate, DialogueRecord
from claynext.models.evaluation import run_evaluation
from claynext.models.khmer_localization.skill import KhmerDialogueSession
from claynext.models.llm_gateway import ChatMessage, ChatRequest, OpenAICompatibleProvider, TraceLog
from claynext.prompts.registry import get_registry


def _record(text: str = "Go home.") -> DialogueRecord:
    return DialogueRecord(
        id="line-1",
        source_text=text,
        candidates=[Candidate(text="ទៅផ្ទះហើយ", style="natural")],
        speaker_id="mom",
        listener_id="child",
        relationship="parent_to_child",
        emotion="neutral",
        register="neutral",
        split="test",
    )


def test_translate_callable_writes_report(tmp: Path):
    report = run_evaluation(
        [_record(), DialogueRecord(id="train-only", source_text="skip", split="train",
                                   candidates=[Candidate(text="រំលង")])],
        translate=lambda rec: (rec.preferred_candidate().text, "trace-offline"),
        provider_id="offline",
        prompt_version="khmer-eval-1",
        dataset_version="v0001",
        out_dir=tmp,
    )
    assert report["evaluated"] == 1
    assert report["provider"] == "offline"
    assert report["prompt_version"] == "khmer-eval-1"
    assert report["dataset_version"] == "v0001"
    assert report["trace_ids"] == [{"id": "line-1", "trace_id": "trace-offline"}]
    assert "pronoun" in report and "postcheck" in report
    path = Path(report["path"])
    assert path.name == "v0001__offline__khmer-eval-1.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["evaluated"] == 1


def test_provider_path_records_gateway_trace(tmp: Path):
    body = {"choices": [{"message": {"content": "ទៅផ្ទះហើយ"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4}}
    calls = []

    def transport(url, headers, raw, timeout):
        calls.append(json.loads(raw))
        return 200, {}, json.dumps(body).encode("utf-8")

    provider = OpenAICompatibleProvider(
        "openai", transport=transport, key_runner=lambda _pid, fn: fn("sk-test"),
        trace=TraceLog(), sleep=lambda _s: None, backoff=0.001,
    )
    report = run_evaluation(
        [_record()],
        provider=provider,
        prompt_version="khmer-eval-1",
        dataset_version="v0002",
        out_dir=tmp,
    )
    assert report["trace_ids"] and report["trace_ids"][0]["trace_id"]
    assert calls and "Go home." in calls[0]["messages"][0]["content"]
    assert report["postcheck"]["violations"] >= 0


def test_khmer_chunk_keeps_trace_id():
    body = {"choices": [{"message": {"content": '{"lines":[]}'}}], "usage": {}}

    def transport(url, headers, raw, timeout):
        return 200, {}, json.dumps(body).encode("utf-8")

    provider = OpenAICompatibleProvider(
        "openai", transport=transport, key_runner=lambda _pid, fn: fn("sk-test"),
        trace=TraceLog(), sleep=lambda _s: None, backoff=0.001,
    )
    skill = get_registry().get("movie.khmer_natural_dialogue", "^0.1")
    session = KhmerDialogueSession(
        skill,
        segments=[{"id": "1", "text": "Go home.", "speaker": "mom"}],
        source_lang="English",
        target_lang="Khmer",
        provider=provider,
    )
    done = session.translate_chunk("Translate.", temperature=0.1)
    assert done["trace_id"]
    assert done["text"]
    request = ChatRequest(messages=[ChatMessage("user", "unused")])
    assert request.trace_id != done["trace_id"]


if __name__ == "__main__":
    import sys
    import tempfile
    import traceback

    failed = 0
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        tests = [
            ("test_translate_callable_writes_report", lambda: test_translate_callable_writes_report(tmp)),
            ("test_provider_path_records_gateway_trace", lambda: test_provider_path_records_gateway_trace(tmp)),
            ("test_khmer_chunk_keeps_trace_id", test_khmer_chunk_keeps_trace_id),
        ]
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
