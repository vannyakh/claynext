"""Score a dataset test split and write a report under ``data/outputs/eval``.

The translator is either a callable ``(record) -> text`` or ``(record) -> (text, trace_id)``,
or a gateway provider. Scoring reuses the Khmer evaluator (resolver + post-check). No prices
are invented: cost is whatever the provider trace already recorded.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from claynext.models.datasets.schema import DialogueRecord
from claynext.models.khmer_localization.evaluator import case_context, evaluate_case
from claynext.models.khmer_localization.lexicon import load_inventory
from claynext.models.khmer_localization.pronouns import PronounResolver
from claynext.models.llm_gateway.base import ChatMessage, ChatRequest

TranslateFn = Callable[[DialogueRecord], Any]


def record_to_case(record: DialogueRecord, resolver: PronounResolver) -> dict[str, Any]:
    """Evaluator case for one dataset row. Allowed pronouns are the resolver's plan."""
    review = record.review
    reviewed = review.status in {"reviewed", "gold"} and review.reviewer_id and review.reviewed_at
    preferred = record.preferred_candidate()
    case: dict[str, Any] = {
        "id": record.id,
        "category": record.category or "everyday",
        "source_language": record.source_lang or "en",
        "source_text": record.source_text,
        "speaker": {"id": record.speaker_id or "speaker"},
        "relationship": {
            "relation": record.relationship or "",
            "source": "dataset",
            "confidence": 1.0,
        },
        "scene": {"id": "", "formality": "neutral"},
        "register": record.register or "neutral",
        "emotion": record.emotion or "neutral",
        "expected": {
            "first_person": {"allowed": [], "forbidden": []},
            "second_person": {"allowed": [], "forbidden": []},
            "max_profanity_level": record.profanity_level,
        },
        "reference_khmer": preferred.text if preferred is not None else "",
        "notes": "",
        "review": {
            "status": "reviewed" if reviewed else "pending_native_review",
            "reviewer": review.reviewer_id or "",
            "reviewed_at": review.reviewed_at or "",
        },
    }
    if record.listener_id:
        case["listener"] = {"id": record.listener_id}
    decision = resolver.resolve(case_context(case))
    if decision.first_person:
        case["expected"]["first_person"]["allowed"] = [decision.first_person]
    if decision.second_person:
        case["expected"]["second_person"]["allowed"] = [decision.second_person]
    if record.profanity_level is None:
        case["expected"].pop("max_profanity_level", None)
    return case


def _translated(value: Any) -> tuple[str, str]:
    if isinstance(value, tuple):
        text = str(value[0] if value else "")
        trace_id = str(value[1] if len(value) > 1 else "")
        return text.strip(), trace_id
    return str(value or "").strip(), ""


def provider_translate(provider) -> TranslateFn:
    """One dataset line through a gateway provider. Returns text and trace id."""

    def translate(record: DialogueRecord) -> tuple[str, str]:
        request = ChatRequest(
            messages=[ChatMessage(
                "user",
                "Translate this line to natural spoken Khmer. Reply with the Khmer line only.\n"
                + record.source_text,
            )],
            temperature=0.2,
            tags={"dataset_id": record.id, "skill": "khmer_eval"},
        )
        response = provider.complete(request)
        return response.text.strip(), response.trace_id

    return translate


def run_evaluation(
    records: list[DialogueRecord],
    *,
    translate: TranslateFn | None = None,
    provider=None,
    provider_id: str = "",
    prompt_version: str = "khmer-eval-1",
    dataset_version: str = "working",
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Score the test split and write the report JSON. Returns the report."""
    if translate is None:
        if provider is None:
            raise ValueError("Pass translate or a gateway provider.")
        translate = provider_translate(provider)
    name = provider_id or getattr(provider, "provider_id", "") or "offline"
    test = [row for row in records if (row.split or "") == "test"]
    inventory = load_inventory()
    resolver = PronounResolver(inventory)
    outputs: dict[str, str] = {}
    traces: list[dict[str, str]] = []
    for record in test:
        text, trace_id = _translated(translate(record))
        outputs[record.id] = text
        if trace_id:
            traces.append({"id": record.id, "trace_id": trace_id})
    results = [
        evaluate_case(
            record_to_case(record, resolver),
            resolver=resolver,
            inventory=inventory,
            output_text=outputs.get(record.id, ""),
        )
        for record in test
    ]
    cost = None
    trace = getattr(provider, "trace", None)
    if trace is not None and hasattr(trace, "totals"):
        cost = trace.totals().get("cost_usd")
    violations = sum(len((row.get("failures") or {}).get("output") or []) for row in results)
    pronoun_failed = [row["id"] for row in results if (row.get("failures") or {}).get("resolver")]
    report = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_version": dataset_version,
        "provider": name,
        "prompt_version": prompt_version,
        "split": "test",
        "evaluated": len(results),
        "pronoun": {
            "passed": len(results) - len(pronoun_failed),
            "failed": pronoun_failed,
        },
        "postcheck": {
            "violations": violations,
            "failed": [row["id"] for row in results if (row.get("failures") or {}).get("output")],
        },
        "cost_usd": cost,
        "trace_ids": traces,
        "passed": sum(1 for row in results if row.get("passed")),
        "results": results,
    }
    folder = Path(out_dir) if out_dir else _default_dir()
    folder.mkdir(parents=True, exist_ok=True)
    safe = f"{dataset_version}__{name}__{prompt_version}".replace("/", "-")
    path = folder / f"{safe}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["path"] = str(path)
    return report


def _default_dir() -> Path:
    from claynext.utils.paths import OUTPUTS_DIR

    return OUTPUTS_DIR / "eval"
