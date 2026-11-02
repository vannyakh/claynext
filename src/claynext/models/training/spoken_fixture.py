"""Spoken-Khmer fixture translator.

Looks up a stored Jev line from the approved SFT export. It does not generate
text, load weights, or fine-tune. Holdout ids kp-1001–kp-2000 are refused.
A source that is not in the loaded rows is reported as not in the test set.

This is a test double for the benchmark runner, not a trained LLM.
``trainer.start`` is not called.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from claynext.models.khmer_spoken.paths import VERSIONS_DIR

MODEL_ID = "spoken-khmer-jev-lookup-20261026-b"
KIND = "fixture_lookup"
NOT_IN_TEST_SET = "source is not in the test set"
HOLDOUT_REFUSAL = "refused holdout id kp-1001–kp-2000"
HOLDOUT_FIRST = 1001
HOLDOUT_LAST = 2000
DEFAULT_SFT_PATH = (
    VERSIONS_DIR
    / "translate-sft-spoken-20261026-b"
    / "sft-train-approved.jsonl"
)

_KP_ID = re.compile(r"^kp-(\d+)$", re.IGNORECASE)


class FixtureDataError(ValueError):
    """The fixture rows cannot be served as the approved train lookup."""


@dataclass(frozen=True)
class FixtureLookup:
    """One lookup. ``text`` is the stored Jev line only on a hit."""

    ok: bool
    status: str
    text: str
    row_id: str
    message: str
    source: str = ""
    licence: str = ""
    owner_training_approved: bool = False
    model_id: str = MODEL_ID
    trained: bool = False
    generates: bool = False
    promoted: bool = False
    kind: str = KIND

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def kp_number(row_id: str) -> int | None:
    match = _KP_ID.match(str(row_id or "").strip())
    if match is None:
        return None
    return int(match.group(1))


def canonical_row_id(row_id: str) -> str:
    text = str(row_id or "").strip()
    match = _KP_ID.match(text)
    if match is None:
        return text
    return f"kp-{match.group(1)}"


def is_holdout_id(row_id: str) -> bool:
    number = kp_number(row_id)
    return number is not None and HOLDOUT_FIRST <= number <= HOLDOUT_LAST


def load_sft_rows(path: str | Path) -> list[dict[str, Any]]:
    """Read JSONL rows. Does not read API keys or the live spoken workspace."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"spoken Khmer SFT file is missing: {file_path}")
    rows: list[dict[str, Any]] = []
    with file_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise FixtureDataError(f"{file_path}:{line_number} is not json") from exc
            if not isinstance(item, dict):
                raise FixtureDataError(f"{file_path}:{line_number} is not an object")
            rows.append(item)
    return rows


def _normalize_row(item: dict[str, Any]) -> dict[str, Any]:
    row_id = canonical_row_id(str(item.get("id") or ""))
    source = str(item.get("source") or "").strip()
    khmer = str(item.get("khmer") or "").strip()
    if not row_id or not source or not khmer:
        raise FixtureDataError("a fixture row needs id, source, and khmer")
    approved = item.get("owner_training_approved") is True
    split = str(item.get("split") or "").strip()
    if is_holdout_id(row_id):
        raise FixtureDataError(f"{row_id} is a holdout id and cannot be loaded")
    if split != "train":
        raise FixtureDataError(f"{row_id} is not a train row")
    if not approved:
        raise FixtureDataError(f"{row_id} is not owner_training_approved")
    return {
        "id": row_id,
        "source": source,
        "khmer": khmer,
        "licence": str(item.get("licence") or item.get("license_type") or ""),
        "owner_training_approved": True,
        "split": "train",
    }


def index_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_source: dict[str, str] = {}
    ordered: list[dict[str, Any]] = []
    for item in items:
        row = _normalize_row(item)
        if row["id"] in by_id:
            raise FixtureDataError(f"duplicate id {row['id']}")
        if row["source"] in by_source:
            raise FixtureDataError(f"duplicate source on {row['id']}")
        by_id[row["id"]] = row
        by_source[row["source"]] = row["id"]
        ordered.append(row)
    return ordered


def _miss(row_id: str = "", source: str = "") -> FixtureLookup:
    return FixtureLookup(
        ok=False,
        status="not_in_test_set",
        text="",
        row_id=row_id,
        source=source,
        message=NOT_IN_TEST_SET,
    )


def _holdout(row_id: str) -> FixtureLookup:
    return FixtureLookup(
        ok=False,
        status="refused_holdout",
        text="",
        row_id=canonical_row_id(row_id),
        message=HOLDOUT_REFUSAL,
    )


def _hit(row: dict[str, Any]) -> FixtureLookup:
    return FixtureLookup(
        ok=True,
        status="hit",
        text=row["khmer"],
        row_id=row["id"],
        source=row["source"],
        message="",
        licence=row["licence"],
        owner_training_approved=True,
    )


class SpokenKhmerFixture:
    """Lookup of approved Jev lines. Not a weight update and not promoted."""

    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        path: str | Path | None = None,
    ) -> None:
        if rows is not None and path is not None:
            raise ValueError("pass rows or path, not both")
        if rows is None:
            self.path: Path | None = Path(path) if path is not None else DEFAULT_SFT_PATH
            loaded = load_sft_rows(self.path)
        else:
            self.path = None
            loaded = list(rows)
        ordered = index_rows(loaded)
        self._by_id = {row["id"]: row for row in ordered}
        self._by_source = {row["source"]: row for row in ordered}

    @property
    def row_count(self) -> int:
        return len(self._by_id)

    def lookup(self, row_id: str = "", source: str = "") -> FixtureLookup:
        """Return the stored Jev line for a train id or an exact source string.

        A holdout id is refused even when ``source`` matches a train row.
        When ``row_id`` is set and is not a holdout, the source is not used
        as a fallback. An unknown source, or an id whose stored source does
        not match, returns ``not_in_test_set``.
        """
        query_id = canonical_row_id(row_id) if str(row_id or "").strip() else ""
        query_source = str(source or "").strip()
        if query_id and is_holdout_id(query_id):
            return _holdout(query_id)
        if query_id:
            row = self._by_id.get(query_id)
            if row is None:
                return _miss(query_id, query_source)
            if query_source and query_source != row["source"]:
                return _miss(query_id, query_source)
            return _hit(row)
        if query_source:
            row = self._by_source.get(query_source)
            if row is None:
                return _miss("", query_source)
            return _hit(row)
        return _miss()

    def translate_row(self, row: Any) -> dict[str, Any]:
        """Benchmark-runner shape. ``text`` is empty unless the row is a hit.

        ``coerce_output`` keeps only ``text``. Read ``status`` and ``message``
        on this dict before coercing. A miss is not a generated translation.
        """
        if isinstance(row, dict):
            row_id = str(row.get("id") or "")
            source = str(row.get("source") or row.get("source_text") or "")
        else:
            row_id = str(getattr(row, "id", "") or "")
            source = str(getattr(row, "source_text", "") or getattr(row, "source", "") or "")
        return self.lookup(row_id=row_id, source=source).to_dict()

    def __call__(self, row: Any) -> dict[str, Any]:
        return self.translate_row(row)
