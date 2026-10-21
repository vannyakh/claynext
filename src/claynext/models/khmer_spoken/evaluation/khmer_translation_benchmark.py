"""Offline Khmer translation quality harness (+ optional Gemini-as-judge).

Compares provider slots (stubs OK): gemini_teacher / untuned / other / gold.
Writes reproducible result files under ``data/khmer_spoken/evals/``.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from claynext.models.khmer_spoken.paths import EVALS_DIR, ensure_khmer_spoken_dirs
from claynext.models.khmer_spoken.schema import DialogueExample

ProgressCb = Callable[[int, str], None] | None

_KHMER_RE = re.compile(r"[\u1780-\u17FF]+")


@dataclass
class ExampleScore:
    id: str
    provider: str
    hypothesis: str
    reference: str
    has_khmer: bool
    char_len: int
    overlap_ratio: float
    judge_score: float | None = None
    judge_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkReport:
    created_at: str
    n_examples: int
    providers: list[str]
    offline: bool
    gemini_judge: bool
    scores: list[ExampleScore] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "n_examples": self.n_examples,
            "providers": self.providers,
            "offline": self.offline,
            "gemini_judge": self.gemini_judge,
            "summary": self.summary,
            "scores": [s.to_dict() for s in self.scores],
            "path": self.path,
        }


def _khmer_chars(text: str) -> str:
    return "".join(_KHMER_RE.findall(text or ""))


def _overlap_ratio(hyp: str, ref: str) -> float:
    a = set(_khmer_chars(hyp))
    b = set(_khmer_chars(ref))
    if not a and not b:
        return 1.0 if (hyp or "") == (ref or "") else 0.0
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _hypothesis_for(ex: DialogueExample, provider: str) -> str:
    if provider == "gold":
        return ex.approved_text or ex.preferred_khmer()
    if provider == "stub":
        return ex.stub_khmer
    if provider in {"gemini_teacher", "untuned", "other"}:
        # Prefer candidates tagged with that provider; else preferred_khmer.
        for cand in ex.candidates:
            if cand.provider in {"gemini_teacher", "gemini"} and provider == "gemini_teacher":
                return cand.text
        if provider == "untuned":
            return ex.stub_khmer or (ex.candidates[0].text if ex.candidates else "")
        return ex.preferred_khmer()
    return ex.preferred_khmer()


def run_benchmark(
    examples: list[DialogueExample],
    *,
    providers: list[str] | None = None,
    use_gemini_judge: bool = False,
    out_dir: str | Path | None = None,
    progress_callback: ProgressCb = None,
) -> BenchmarkReport:
    """Run offline metrics; optionally call Gemini-as-judge when key present."""
    ensure_khmer_spoken_dirs()
    providers = providers or ["gemini_teacher", "untuned", "gold"]
    scores: list[ExampleScore] = []
    judge_used = False
    total = max(1, len(examples) * len(providers))
    step = 0

    for ex in examples:
        ref = ex.approved_text or ex.stub_khmer or ex.preferred_khmer()
        for provider in providers:
            step += 1
            if progress_callback:
                progress_callback(int(100 * step / total), f"Scoring {ex.id}/{provider}")
            hyp = _hypothesis_for(ex, provider)
            row = ExampleScore(
                id=ex.id,
                provider=provider,
                hypothesis=hyp,
                reference=ref,
                has_khmer=bool(_khmer_chars(hyp)),
                char_len=len(hyp),
                overlap_ratio=round(_overlap_ratio(hyp, ref), 4),
            )
            if use_gemini_judge and hyp and ref:
                judged = _gemini_judge(hyp, ref, source=ex.source_text)
                if judged is not None:
                    judge_used = True
                    row.judge_score, row.judge_notes = judged
            scores.append(row)

    by_provider: dict[str, list[ExampleScore]] = {}
    for s in scores:
        by_provider.setdefault(s.provider, []).append(s)

    summary: dict[str, Any] = {}
    for prov, rows in by_provider.items():
        overlaps = [r.overlap_ratio for r in rows]
        khmer_rate = sum(1 for r in rows if r.has_khmer) / max(1, len(rows))
        judges = [r.judge_score for r in rows if r.judge_score is not None]
        summary[prov] = {
            "n": len(rows),
            "mean_overlap": round(sum(overlaps) / max(1, len(overlaps)), 4),
            "khmer_script_rate": round(khmer_rate, 4),
            "mean_judge": round(sum(judges) / len(judges), 3) if judges else None,
        }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(out_dir) if out_dir else EVALS_DIR
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"benchmark_{stamp}.json"
    report = BenchmarkReport(
        created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        n_examples=len(examples),
        providers=providers,
        offline=not judge_used,
        gemini_judge=judge_used,
        scores=scores,
        summary=summary,
        path=str(path),
    )
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if progress_callback:
        progress_callback(100, "Benchmark written")
    return report


def _gemini_judge(hyp: str, ref: str, *, source: str) -> tuple[float, str] | None:
    """Optional Gemini-as-judge; returns None when key missing or call fails."""
    try:
        from claynext.models.khmer_spoken.providers.google_gemini_provider import (
            GeminiTeacherProvider,
        )

        teacher = GeminiTeacherProvider()
        if not teacher.available():
            return None
        prompt = (
            "Score the Khmer hypothesis vs reference for film dialogue (0-5).\n"
            "Return JSON: {\"score\": <number>, \"notes\": \"...\"}\n"
            f"source: {source}\nreference: {ref}\nhypothesis: {hyp}\n"
        )
        result = teacher.complete(prompt, temperature=0.1)
        if not result.ok:
            return None
        data = json.loads(result.text)
        return float(data.get("score", 0)), str(data.get("notes") or "")
    except Exception:
        return None
