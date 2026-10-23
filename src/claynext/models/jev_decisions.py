"""Jev decisions for movie dubbing.

Jev (TypeSafe System One) judges a line. It does not write the translation.
Code keeps the local cast and the current translator when no key is set,
when confidence is low, or when the call fails.

Key: Settings → API Keys → TypeSafe Jev, or the ``TYPESAFE_API_KEY`` environment variable.
"""
from __future__ import annotations

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

_MODEL = "jev-latest"
_CHOICE_FLOOR = 0.6
_MEANING_FLOOR = 0.35
_NATURAL_FLOOR = 0.35
_CAST_BATCH = 6
_CAST_LIMIT = 48
_TRANSLATE_BATCH = 4
_TRANSLATE_LIMIT = 32

_INTENTS = {
    "question": "The speaker is asking the other person something",
    "answer": "The speaker is answering the previous turn",
    "command": "The speaker is ordering, warning, or demanding",
    "plea": "The speaker is begging, apologizing, or asking for mercy",
    "aside": "The speaker is whispering, muttering, or speaking aside",
    "narration": "Narrator voice-over, not a character talking to someone in the scene",
    "statement": "Ordinary dialogue that is none of the above",
}
_EXPRESSIONS = {
    "plain": "Plain speech with no special delivery",
    "laugh": "The line is said while laughing",
    "sigh": "The line is said with a sigh",
    "whisper": "The line is whispered",
    "sad": "The line is sad or crying",
    "shout": "The line is shouted",
    "angry": "The line is angry",
    "gasp": "The line is a gasp or shock",
    "excited": "The line is excited",
    "calm": "The line is calm and steady",
}


def jev_available() -> bool:
    return jev_key_configured()


def jev_key_configured() -> bool:
    """True when a TypeSafe key is stored or set in the environment. Does not print it."""
    try:
        from claynext.models.llm_keys import get_key_pool

        if get_key_pool().has_enabled("typesafe"):
            return True
    except Exception:
        pass
    return bool(os.environ.get("TYPESAFE_API_KEY", "").strip())


def _api_key() -> str:
    try:
        from claynext.models.llm_keys import get_key_pool

        secret = get_key_pool().first_secret("typesafe")
        if secret:
            return secret
    except Exception:
        pass
    return os.environ.get("TYPESAFE_API_KEY", "").strip()


def _ping(progress: Callable | None, pct: int, msg: str) -> None:
    if progress is None:
        return
    try:
        progress(pct, msg)
    except Exception:
        pass


def _ask(state: dict, questions: dict[str, dict]) -> dict[str, dict] | None:
    """One System One call. Returns flattened answers, or None when Jev cannot answer."""
    key = _api_key()
    if not key or not questions:
        return None
    try:
        from typesafe_sdk import Choice, Noul, RetryPolicy, Score, TypeSafeClient

        built = {}
        for qid, spec in questions.items():
            kind = spec.get("type")
            if kind == "choice":
                built[qid] = Choice(instructions=spec["instructions"], criteria=spec["criteria"])
            elif kind == "noul":
                built[qid] = Noul(instructions=spec["instructions"])
            elif kind == "score":
                built[qid] = Score(instructions=spec["instructions"], criteria=spec["criteria"])
        with TypeSafeClient(
            api_key=key,
            model=_MODEL,
            retry=RetryPolicy(max_retries=2, timeout=30.0),
        ) as client:
            result = client.system_one(state=state, questions=built)
        flat: dict[str, dict] = {}
        for qid, ans in dict(getattr(result, "choices", {}) or {}).items():
            flat[qid] = {
                "type": "choice",
                "choice": str(getattr(ans, "choice", "") or ""),
                "confidence": float(getattr(ans, "confidence", 0) or 0),
            }
        for qid, ans in dict(getattr(result, "nouls", {}) or {}).items():
            flat[qid] = {"type": "noul", "noul": float(getattr(ans, "noul", 0) or 0)}
        for qid, ans in dict(getattr(result, "scores", {}) or {}).items():
            flat[qid] = {
                "type": "score",
                "score": float(getattr(ans, "score", 0) or 0),
                "confidence": float(getattr(ans, "confidence", 0) or 0),
            }
        return flat or None
    except Exception:
        return _ask_http(key, state, questions)


def _ask_http(key: str, state: dict, questions: dict[str, dict]) -> dict[str, dict] | None:
    body = json.dumps({"state": state, "model": _MODEL, "questions": questions}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.typesafe.ai/v1/systemone",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    answers = payload.get("answers") if isinstance(payload, dict) else None
    return answers if isinstance(answers, dict) else None


def apply_cast_judgment(
    seg: dict[str, Any],
    answers: dict[str, dict],
    index: int,
) -> bool:
    """Write a confident Jev judgment onto one line. Low confidence leaves the line alone."""
    changed = False
    intent = answers.get(f"intent_{index}") or {}
    if (
        intent.get("type") == "choice"
        and intent.get("choice") in _INTENTS
        and float(intent.get("confidence") or 0) >= _CHOICE_FLOOR
    ):
        seg["intent"] = intent["choice"]
        seg["intent_source"] = "jev"
        changed = True

    expr = answers.get(f"expression_{index}") or {}
    if (
        not seg.get("expression_manual")
        and expr.get("type") == "choice"
        and expr.get("choice") in _EXPRESSIONS
        and float(expr.get("confidence") or 0) >= _CHOICE_FLOOR
    ):
        choice = str(expr["choice"])
        if choice == "plain":
            if seg.get("expression_source") != "manual":
                seg["expression"] = ""
                seg["expression_source"] = "jev"
                changed = True
        else:
            seg["expression"] = choice
            seg["expression_source"] = "jev"
            changed = True

    gender = answers.get(f"gender_{index}") or {}
    choice = str(gender.get("choice") or "")
    conf = float(gender.get("confidence") or 0)
    if (
        not seg.get("gender_manual")
        and gender.get("type") == "choice"
        and choice in {"Male", "Female"}
        and conf >= (0.8 if seg.get("gender_source") == "audio" else _CHOICE_FLOOR)
    ):
        seg["gender"] = choice
        seg["gender_source"] = "jev"
        changed = True
    return changed


def _cast_questions(count: int) -> dict[str, dict]:
    questions: dict[str, dict] = {}
    for index in range(count):
        questions[f"intent_{index}"] = {
            "type": "choice",
            "instructions": (
                f"What is the speaker doing in `lines[{index}].text`, "
                f"given `lines[{index}].previous` when it is present?"
            ),
            "criteria": _INTENTS,
        }
        questions[f"expression_{index}"] = {
            "type": "choice",
            "instructions": f"How should an actor deliver `lines[{index}].text`?",
            "criteria": _EXPRESSIONS,
        }
        questions[f"gender_{index}"] = {
            "type": "choice",
            "instructions": (
                f"Is the person speaking `lines[{index}].text` male or female? "
                "Use the words in the line, not the actor you would prefer."
            ),
            "criteria": {
                "Male": "The speaker is male",
                "Female": "The speaker is female",
                "Unknown": "The line does not show the speaker's gender",
            },
        }
    return questions


def refine_cast(
    segments: list[dict[str, Any]],
    *,
    progress_callback: Callable | None = None,
) -> int:
    """Judge up to 48 lines. Returns how many lines Jev changed."""
    if not segments or not jev_available():
        return 0
    picked = list(enumerate(segments))[:_CAST_LIMIT]
    batches = [picked[i:i + _CAST_BATCH] for i in range(0, len(picked), _CAST_BATCH)]
    _ping(progress_callback, 30, f"Jev · judging delivery for {len(picked)} line(s)…")

    def _one(batch: list[tuple[int, dict]]) -> int:
        lines = []
        for _src, seg in batch:
            lines.append({
                "speaker": str(seg.get("speaker") or ""),
                "text": str(seg.get("text") or seg.get("original_text") or "")[:500],
                "previous": str(seg.get("previous_text") or "")[:240],
            })
        answers = _ask(
            {"task": "Decide how each film line should be performed.", "lines": lines},
            _cast_questions(len(lines)),
        )
        if not answers:
            return 0
        changed = 0
        for local, (_src, seg) in enumerate(batch):
            if apply_cast_judgment(seg, answers, local):
                changed += 1
        return changed

    total = 0
    workers = min(3, len(batches))
    if workers <= 1:
        for batch in batches:
            total += _one(batch)
        return total
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for count in pool.map(_one, batches):
            total += int(count or 0)
    return total


def translation_failed(meaning: float, natural: float) -> bool:
    """A line fails when Jev says it lost the meaning or cannot be spoken."""
    return meaning < _MEANING_FLOOR or natural < _NATURAL_FLOOR


def _suspect_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flagged: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for row in rows:
        source = str(row.get("original_text") or row.get("text") or "").strip()
        translated = str(row.get("translated_text") or "").strip()
        if not translated or (len(source) >= 8 and translated == source):
            flagged.append(row)
            continue
        if len(source) >= 12 and (
            len(translated) > len(source) * 1.8 or len(translated) < len(source) * 0.35
        ):
            flagged.append(row)
            continue
        rest.append(row)
    ordered = flagged + rest
    return ordered[:_TRANSLATE_LIMIT]


def weak_translation_ids(
    rows: list[dict[str, Any]],
    *,
    target_lang: str,
    source_lang: str = "",
    progress_callback: Callable | None = None,
) -> set[str]:
    """Line ids Jev would not send to the dub stage. Empty when Jev is not used."""
    if not rows or not jev_available():
        return set()
    sample = _suspect_rows(rows)
    if not sample:
        return set()
    _ping(progress_callback, 90, f"Jev · checking {len(sample)} translated line(s)…")
    batches = [sample[i:i + _TRANSLATE_BATCH] for i in range(0, len(sample), _TRANSLATE_BATCH)]

    def _one(batch: list[dict]) -> set[str]:
        lines = []
        for row in batch:
            lines.append({
                "source": str(row.get("original_text") or row.get("text") or "")[:500],
                "translation": str(row.get("translated_text") or "")[:500],
            })
        questions: dict[str, dict] = {}
        for index in range(len(lines)):
            questions[f"meaning_{index}"] = {
                "type": "noul",
                "instructions": (
                    f"`lines[{index}].translation` says the same thing as "
                    f"`lines[{index}].source` for a film dub"
                ),
            }
            questions[f"natural_{index}"] = {
                "type": "noul",
                "instructions": (
                    f"`lines[{index}].translation` is natural spoken {target_lang or 'dialogue'} "
                    "an actor can say, not a word-for-word glossary"
                ),
            }
        answers = _ask(
            {
                "source_language": source_lang or "unknown",
                "target_language": target_lang,
                "lines": lines,
            },
            questions,
        )
        if not answers:
            return set()
        failed: set[str] = set()
        for index, row in enumerate(batch):
            meaning = answers.get(f"meaning_{index}") or {}
            natural = answers.get(f"natural_{index}") or {}
            if meaning.get("type") != "noul" or natural.get("type") != "noul":
                continue
            if translation_failed(float(meaning.get("noul") or 0), float(natural.get("noul") or 0)):
                key = str(row.get("id") or "")
                if key:
                    failed.add(key)
        return failed

    weak: set[str] = set()
    workers = min(3, len(batches))
    if workers <= 1:
        for batch in batches:
            weak |= _one(batch)
        return weak
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for found in pool.map(_one, batches):
            weak |= set(found or ())
    return weak


def rank_khmer_candidates(example: Any, *, ask: Callable | None = None) -> dict[str, Any]:
    """Rank or drop Gemini candidates on one dialogue row.

    Jev judges. It does not write a new translation and it does not change
    approved text, review status, licence, or reviewer notes. No key, or a
    failed call, leaves the row untouched. Never raises.
    """
    try:
        return _rank_khmer_candidates(example, ask=ask or _ask)
    except Exception:
        return {"applied": False, "reason": "error"}


def _rank_khmer_candidates(example: Any, *, ask: Callable) -> dict[str, Any]:
    if not jev_key_configured():
        return {"applied": False, "reason": "no_key"}
    candidates = [cand for cand in list(getattr(example, "candidates", []) or []) if str(getattr(cand, "text", "") or "").strip()]
    if len(candidates) < 2:
        return {"applied": False, "reason": "too_few"}
    source = str(getattr(example, "source_text", "") or "")[:500]
    speaker = str(getattr(example, "speaker_id", "") or "speaker")
    listener = str(getattr(example, "listener_id", "") or "listener")
    relation = str(getattr(example, "relationship", "") or "unspecified")
    lines = []
    for index, cand in enumerate(candidates):
        lines.append({
            "index": index,
            "text": str(cand.text)[:500],
            "style": str(getattr(cand, "style", "") or ""),
        })
    questions: dict[str, dict] = {}
    criteria: dict[str, str] = {}
    for index, line in enumerate(lines):
        text = line["text"]
        questions[f"meaning_{index}"] = {
            "type": "noul",
            "instructions": (
                f"The Khmer line “{text}” says the same thing as the source “{source}” "
                f"for a film dub."
            ),
        }
        questions[f"natural_{index}"] = {
            "type": "noul",
            "instructions": (
                f"The Khmer line “{text}” is natural spoken Khmer an actor can say "
                f"for the source “{source}”, not a word-for-word glossary."
            ),
        }
        questions[f"pronoun_{index}"] = {
            "type": "noul",
            "instructions": (
                f"The Khmer line “{text}” uses pronouns and address that fit "
                f"{speaker} talking to {listener} ({relation}) "
                f"while keeping the meaning of “{source}”."
            ),
        }
        criteria[str(index)] = (
            f"Best line is “{text}”. It keeps the meaning of “{source}” "
            f"and fits {speaker} speaking to {listener}."
        )
    questions["best"] = {
        "type": "choice",
        "instructions": (
            f"Which Khmer line best keeps the meaning of the source “{source}”, "
            f"fits {speaker} talking to {listener}, and sounds natural to say?"
        ),
        "criteria": criteria,
    }
    answers = ask(
        {
            "task": "Rank Khmer dub candidates. Do not write a new line.",
            "source": source,
            "speaker": speaker,
            "listener": listener,
            "relationship": relation,
            "lines": lines,
        },
        questions,
    )
    if not answers:
        return {"applied": False, "reason": "no_answer"}

    scores: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        meaning = _noul_value(answers.get(f"meaning_{index}"))
        natural = _noul_value(answers.get(f"natural_{index}"))
        pronoun = _noul_value(answers.get(f"pronoun_{index}"))
        failed = (
            meaning is None
            or natural is None
            or pronoun is None
            or meaning < _MEANING_FLOOR
            or natural < _NATURAL_FLOOR
            or pronoun < _MEANING_FLOOR
        )
        scores.append({
            "index": index,
            "text": line["text"],
            "meaning": meaning,
            "natural": natural,
            "pronoun": pronoun,
            "keep": not failed,
        })
    kept = [row for row in scores if row["keep"]]
    choice = answers.get("best") or {}
    choice_id = str(choice.get("choice") or "")
    choice_conf = float(choice.get("confidence") or 0)
    preferred: dict[str, Any] | None = None
    if (
        choice.get("type") == "choice"
        and choice_conf >= _CHOICE_FLOOR
        and choice_id.isdigit()
    ):
        picked = next((row for row in kept if row["index"] == int(choice_id)), None)
        if picked is not None:
            preferred = picked
    if preferred is None and kept:
        preferred = max(
            kept,
            key=lambda row: float(row["meaning"] or 0) + float(row["natural"] or 0) + float(row["pronoun"] or 0),
        )
    record = {
        "applied": preferred is not None,
        "provider": "typesafe",
        "model": _MODEL,
        "preferred_index": None if preferred is None else preferred["index"],
        "preferred_text": "" if preferred is None else preferred["text"],
        "choice": choice_id,
        "choice_confidence": choice_conf,
        "scores": scores,
    }
    metadata = getattr(example, "metadata", None)
    if isinstance(metadata, dict):
        metadata["jev"] = record
    return record


def _noul_value(answer: Any) -> float | None:
    if not isinstance(answer, dict) or answer.get("type") != "noul":
        return None
    try:
        return float(answer.get("noul"))
    except (TypeError, ValueError):
        return None
