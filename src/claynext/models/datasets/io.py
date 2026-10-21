"""Read CSV / JSON / JSONL dialogue files into ``DialogueRecord`` and write canonical JSONL.

Three row shapes are recognised per row:

- canonical: rows written by this package (``candidates`` list present);
- KSLD: Khmer Spoken Language Dataset v0.1/v1.0 (``scene_id`` + ``target_text`` + ``variation_method``);
- flat: one column per field (see ``FLAT_COLUMNS`` in the docs).

Rows that fail to parse or validate with errors are returned as rejects with reasons, never
silently dropped.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from claynext.models.datasets.schema import (
    QUALITY_DIMENSIONS,
    Candidate,
    DialogueRecord,
    Issue,
    Provenance,
    Quality,
    Regional,
    Review,
    has_errors,
    validate_record,
)

SUPPORTED_SUFFIXES = (".csv", ".json", ".jsonl")

KSLD_REQUIRED = frozenset({"scene_id", "source_text", "target_text", "variation_method"})
# KSLD genre -> schema CATEGORIES. care / surprise / excited were mapped by product decision
# (Oct 2026); any genre not listed stays uncategorized (missing_category warning), never guessed.
KSLD_GENRE_CATEGORY = {
    "daily": "everyday",
    "argument": "argument",
    "romance": "romance",
    "comedy": "comedy_sarcasm",
    "fear": "fear_sadness",
    "sad": "fear_sadness",
    "care": "family",
    "surprise": "everyday",
    "excited": "comedy_sarcasm",
}
KSLD_STATUS = {"needs_native_review": "draft", "approved": "reviewed", "rejected": "rejected"}
_UNSPECIFIED = {"", "unspecified", "unknown", "none", "null", "n/a"}


@dataclass
class ImportResult:
    records: list[DialogueRecord] = field(default_factory=list)
    rejects: list[dict[str, Any]] = field(default_factory=list)
    warnings: dict[str, int] = field(default_factory=dict)
    shape_counts: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "imported": len(self.records),
            "rejected": len(self.rejects),
            "shapes": dict(self.shape_counts),
            "warnings": dict(sorted(self.warnings.items())),
            "reject_reasons": _count(code for r in self.rejects for code in r["codes"]),
        }


def _count(items: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return dict(sorted(out.items()))


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _unspecified(value: Any) -> str | None:
    text = _str(value)
    return None if text.lower() in _UNSPECIFIED else text


def read_rows(path: str | Path) -> list[dict[str, Any]]:
    """Raw dict rows from a CSV (UTF-8, BOM tolerated), JSON list / {records: [...]}, or JSONL."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        with p.open("r", encoding="utf-8-sig", newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    if suffix == ".jsonl":
        rows = []
        with p.open("r", encoding="utf-8-sig") as fh:
            for n, line in enumerate(fh, 1):
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        rows.append({"__parse_error__": f"line {n}: {exc}"})
        return rows
    if suffix == ".json":
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("records") or data.get("data") or []
        if not isinstance(data, list):
            raise ValueError(f"{p.name}: expected a JSON list or an object with 'records'.")
        return data
    raise ValueError(f"Unsupported file type {suffix!r}; use one of {SUPPORTED_SUFFIXES}.")


def detect_shape(row: dict[str, Any]) -> str:
    if isinstance(row.get("candidates"), list):
        return "canonical"
    if KSLD_REQUIRED <= row.keys():
        return "ksld"
    return "flat"


def from_ksld(row: dict[str, Any], *, dataset: str, file: str) -> DialogueRecord:
    """Map one Khmer Spoken Language Dataset row. Every KSLD row is a synthetic draft."""
    target = _str(row.get("target_text"))
    tts = _str(row.get("tts_text"))
    genre = _str(row.get("genre"))
    status = _str(row.get("review_status"))
    region = _unspecified(row.get("region"))
    metadata: dict[str, Any] = {
        "source_genre": genre or None,
        "source_review_status": status or None,
        "source_split": _str(row.get("split")) or None,
        "variation_method": _str(row.get("variation_method")) or None,
        "base_source": _str(row.get("base_source")) or None,
        "base_target": _str(row.get("base_target")) or None,
        "speaker_age_group": _str(row.get("speaker_age_group")) or None,
        "notes": _str(row.get("notes")) or None,
    }
    if tts and tts == target:
        metadata["tts_text_placeholder"] = True
    quality = Quality()
    raw_score = _str(row.get("quality_score"))
    if raw_score:
        quality.extra["source_quality_score"] = float(raw_score)
    reviewer = _str(row.get("reviewer_id")) or None
    return DialogueRecord(
        id=_str(row.get("id")),
        source_text=_str(row.get("source_text")),
        source_lang=_str(row.get("source_language")) or "en",
        target_lang=_str(row.get("target_language")) or "km",
        candidates=[Candidate(text=target, style="unspecified", origin="synthetic")] if target else [],
        tts_text=tts if tts and tts != target else None,
        speaker_id=_str(row.get("character_id")) or None,
        listener_id=_str(row.get("listener_id")) or None,
        relationship=_str(row.get("relationship")) or None,
        emotion=_str(row.get("emotion")) or None,
        register=_str(row.get("speech_register")) or None,
        slang_level=int(float(row["slang_level"])) if _str(row.get("slang_level")) else None,
        profanity_level=int(float(row["profanity_level"])) if _str(row.get("profanity_level")) else None,
        category=KSLD_GENRE_CATEGORY.get(genre),
        regional=Regional(region=region, verified=_bool(row.get("regional_verified"))),
        provenance=Provenance(dataset=dataset, file=file, source_id=_str(row.get("id")) or None),
        origin="synthetic",
        review=Review(status=KSLD_STATUS.get(status, status or "draft"), reviewer_id=reviewer,
                      reviewer_type="human" if reviewer else None),
        quality=quality,
        groups={"dialogue_family": _str(row.get("scene_id"))},
        metadata={k: v for k, v in metadata.items() if v is not None},
    )


def from_flat(row: dict[str, Any], *, dataset: str, file: str) -> DialogueRecord:
    """One column per field. Candidate columns: khmer_natural, khmer_literal, target_text / khmer."""
    candidates = []
    for column, style in (("khmer_natural", "natural"), ("khmer_literal", "literal"),
                          ("target_text", "unspecified"), ("khmer", "unspecified")):
        text = _str(row.get(column))
        if text and all(c.text != text for c in candidates):
            candidates.append(Candidate(text=text, style=style, origin=_str(row.get("origin")) or None))
    scores = {d: float(row[d]) for d in QUALITY_DIMENSIONS if _str(row.get(d))}
    return DialogueRecord(
        id=_str(row.get("id")),
        source_text=_str(row.get("source_text") or row.get("source")),
        source_lang=_str(row.get("source_lang") or row.get("source_language")) or "en",
        target_lang=_str(row.get("target_lang") or row.get("target_language")) or "km",
        candidates=candidates,
        tts_text=_str(row.get("tts_text")) or None,
        speaker_id=_str(row.get("speaker_id") or row.get("character_id")) or None,
        listener_id=_str(row.get("listener_id")) or None,
        relationship=_str(row.get("relationship")) or None,
        emotion=_str(row.get("emotion")) or None,
        intensity=int(float(row["intensity"])) if _str(row.get("intensity")) else None,
        register=_str(row.get("register") or row.get("speech_register")) or None,
        slang_level=int(float(row["slang_level"])) if _str(row.get("slang_level")) else None,
        profanity_level=int(float(row["profanity_level"])) if _str(row.get("profanity_level")) else None,
        category=_str(row.get("category")) or None,
        regional=Regional(
            region=_unspecified(row.get("region")),
            verified=_bool(row.get("region_verified") or row.get("regional_verified")),
            provenance=_str(row.get("region_provenance")) or None,
            confidence=float(row["region_confidence"]) if _str(row.get("region_confidence")) else None,
        ),
        provenance=Provenance(
            dataset=_str(row.get("dataset")) or dataset,
            file=file,
            source_id=_str(row.get("source_id") or row.get("id")) or None,
            license=_str(row.get("license")) or None,
            attribution=_str(row.get("attribution")) or None,
        ),
        origin=_str(row.get("origin")) or "synthetic",
        review=Review(
            status=_str(row.get("review_status") or row.get("status")) or "draft",
            reviewer_id=_str(row.get("reviewer_id")) or None,
            reviewer_type=_str(row.get("reviewer_type")) or None,
            reviewed_at=_str(row.get("reviewed_at")) or None,
        ),
        quality=Quality(scores=scores, scored_by=_str(row.get("scored_by")) or None),
        groups={k: _str(row.get(k)) for k in ("film_id", "script_id", "dialogue_family", "speaker_id")
                if _str(row.get(k))},
    )


def parse_row(row: dict[str, Any], *, dataset: str, file: str) -> tuple[str, DialogueRecord]:
    dataset, file = dataset or None, file or None
    shape = detect_shape(row)
    if shape == "canonical":
        rec = DialogueRecord.from_dict(row)
        if not rec.provenance.dataset:
            rec.provenance.dataset = dataset
        return shape, rec
    if shape == "ksld":
        return shape, from_ksld(row, dataset=dataset, file=file)
    return shape, from_flat(row, dataset=dataset, file=file)


def import_rows(rows: list[dict[str, Any]], *, dataset: str, file: str = "") -> ImportResult:
    result = ImportResult()
    seen_ids: set[str] = set()
    for n, row in enumerate(rows, 1):
        if not isinstance(row, dict) or "__parse_error__" in row:
            reason = row.get("__parse_error__") if isinstance(row, dict) else "row is not an object"
            result.rejects.append({"row": n, "id": None, "codes": ["parse_error"], "issues": [reason]})
            continue
        try:
            shape, rec = parse_row(row, dataset=dataset, file=file)
        except (TypeError, ValueError) as exc:
            result.rejects.append({"row": n, "id": row.get("id"), "codes": ["parse_error"], "issues": [str(exc)]})
            continue
        result.shape_counts[shape] = result.shape_counts.get(shape, 0) + 1
        issues = validate_record(rec)
        if rec.id and rec.id in seen_ids:
            issues.append(Issue("error", "duplicate_id", "id", f"Id {rec.id} appears more than once."))
        if has_errors(issues):
            errors = [i for i in issues if i.severity == "error"]
            result.rejects.append({
                "row": n, "id": rec.id or None,
                "codes": [i.code for i in errors],
                "issues": [i.to_dict() for i in errors],
            })
            continue
        seen_ids.add(rec.id)
        for issue in issues:
            result.warnings[issue.code] = result.warnings.get(issue.code, 0) + 1
        result.records.append(rec)
    return result


def import_file(path: str | Path, *, dataset: str = "") -> ImportResult:
    p = Path(path)
    return import_rows(read_rows(p), dataset=dataset or p.parent.name, file=p.name)


def canonical_line(rec: DialogueRecord) -> str:
    return json.dumps(rec.to_dict(), ensure_ascii=False, sort_keys=True)


def write_records(path: str | Path, records: Iterable[DialogueRecord]) -> Path:
    """Canonical JSONL sorted by id (stable bytes for hashing), written atomically."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in sorted(records, key=lambda r: r.id):
            fh.write(canonical_line(rec) + "\n")
    tmp.replace(p)
    return p


def read_records(path: str | Path) -> list[DialogueRecord]:
    p = Path(path)
    out = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                out.append(DialogueRecord.from_dict(json.loads(line)))
    return out
