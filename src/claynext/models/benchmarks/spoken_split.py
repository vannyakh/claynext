"""Spoken-row splits.

``plan_spoken_split`` is the 500 / 100 plan: when 500 rows exist, train is
exactly 100 and the other 400 stay locked. That plan is unchanged.

``plan_scale_holdout`` is the later owner table. Once a file has at least
1,000 kp ids, the last 1,000 ids are the locked benchmark and earlier ids
are the train pool. Until then, every id outside the historical train pool
stays locked. The function records the cut. It does not generate dialogue,
call a model, or start training.
"""
from __future__ import annotations

import random
from typing import Any

from claynext.models.benchmarks.leakage import LeakageError
from claynext.models.benchmarks.schema import (
    DEPLOYABLE_LICENCES,
    BenchmarkRow,
    SplitLockError,
    assign_split,
)

TRAIN_CAP = 100
TARGET_TOTAL = 500
LOCKED_WHEN_COMPLETE = 400
DEFAULT_SEED = 13
SPEC_RELATIVE = "data/khmer_spoken/versions/spoken-500-train100-spec-20261023/split.json"
PRIOR_PLAN_VERSION = "heldout-locked-20261023-kp081-100"
GENERATION_SPLIT = "data/khmer_spoken/versions/train100-locked400-20261023"

INCOMPLETE_NOTE = (
    "Until kp-101–kp-500 exist, the locked pool is incomplete and must not "
    "be treated as the 1,000–2,000 native gold benchmark."
)
WHEN_COMPLETE_RULE = (
    "When 500 rows exist, train is exactly 100 rows, the other 400 are locked "
    "and must not be used to train or tune."
)
NOT_NATIVE_GOLD_NOTE = (
    "A finished 500-row pool is still not the 1,000–2,000 native-reviewed "
    "gold benchmark. 10,000–30,000 reviewed training examples remain a target."
)


class SplitPlanError(ValueError):
    """The 500/100 plan cannot be applied without breaking a rule."""


class OverlapError(SplitPlanError):
    """The same row id was placed in train and in the locked pool."""


class LockedPoolError(SplitPlanError):
    """A locked row was requested for training or tuning."""


def _id(row: BenchmarkRow | dict[str, Any]) -> str:
    if isinstance(row, dict):
        return str(row.get("id") or "").strip()
    return str(row.id or "").strip()


def _family(row: BenchmarkRow | dict[str, Any]) -> str:
    if isinstance(row, dict):
        value = row.get("dialogue_family_id")
    else:
        value = row.dialogue_family_id
    text = "" if value is None else str(value).strip()
    if not text:
        raise SplitPlanError(f"{_id(row) or '<missing id>'} is missing dialogue_family_id")
    return text


def _is_locked_test(row: BenchmarkRow | dict[str, Any]) -> bool:
    if isinstance(row, dict):
        return row.get("split") == "test" and bool(row.get("locked"))
    return row.split == "test" and bool(row.locked)


def _reference(row: BenchmarkRow | dict[str, Any]) -> str:
    if isinstance(row, dict):
        for key in ("reference_khmer", "approved_text"):
            text = str(row.get(key) or "").strip()
            if text:
                return text
        return ""
    return str(row.reference_khmer or "").strip()


def _kp_number(row_id: str) -> int | None:
    if not row_id.startswith("kp-"):
        return None
    tail = row_id[3:]
    if not tail.isdigit():
        return None
    return int(tail)


def _is_native_gold(row: BenchmarkRow | dict[str, Any]) -> bool:
    if isinstance(row, BenchmarkRow):
        return row.is_gold_reference()
    origin = str(row.get("origin") or "")
    status = str(row.get("review_status") or "")
    licence = str(row.get("licence") or row.get("license_type") or "")
    if row.get("synthetic_only") or origin in {"synthetic", "gemini_teacher"}:
        return False
    if status != "gold" or origin not in {"human_authored", "human_reviewed"}:
        return False
    if not row.get("reviewer_id") or not row.get("reviewed_at"):
        return False
    return licence in DEPLOYABLE_LICENCES


def incomplete_split_spec() -> dict[str, Any]:
    """Policy spec for the current corpus. Does not read or write dialogue rows."""
    return {
        "schema": "spoken-split-spec-1",
        "version": "spoken-500-train100-spec-20261023",
        "seed": DEFAULT_SEED,
        "dialogue_family_safe": True,
        "train_cap": TRAIN_CAP,
        "target_total": TARGET_TOTAL,
        "locked_when_complete": LOCKED_WHEN_COMPLETE,
        "when_complete_rule": WHEN_COMPLETE_RULE,
        "locked_must_not_be_used_to_train_or_tune": True,
        "locked_pool": "incomplete",
        "locked_pool_complete": False,
        "kp_101_through_kp_500": "incomplete",
        "assignment": None,
        "native_gold_benchmark": False,
        "not_the_1000_to_2000_native_gold_benchmark": True,
        "note": INCOMPLETE_NOTE,
        "reviewed_training_examples_target": {
            "min": 10000,
            "max": 30000,
            "status": "target_not_current",
        },
        "native_benchmark_rows_target": {
            "min": 1000,
            "max": 2000,
            "status": "target_not_current",
        },
        "current_jev_ranked_rows": {
            "count": 100,
            "origin": "synthetic/gemini_teacher",
            "licence": "unknown",
            "promotion": "not_promoted",
            "is_gold": False,
        },
        "prior_plan": {
            "version": PRIOR_PLAN_VERSION,
            "path": f"data/khmer_spoken/versions/{PRIOR_PLAN_VERSION}",
            "train": 80,
            "test": 20,
            "deleted": False,
            "replaced_as_plan_only": True,
        },
        "generation_workspace": {
            "path": GENERATION_SPLIT,
            "owned_by_this_spec": False,
            "note": (
                "A separate process fills kp-101 onward and writes that directory. "
                "This spec does not edit it and does not start generation."
            ),
        },
        "promotion": "not_promoted",
    }


def assert_assignment_disjoint(
    train_ids: list[str],
    locked_ids: list[str],
    family_of: dict[str, str],
) -> None:
    """Refuse an id or a dialogue family that sits in both sides."""
    id_overlap = sorted(set(train_ids) & set(locked_ids))
    if id_overlap:
        raise OverlapError("row id in both train and locked: " + ", ".join(id_overlap))
    train_families = {family_of[row_id] for row_id in train_ids if row_id in family_of}
    locked_families = {family_of[row_id] for row_id in locked_ids if row_id in family_of}
    leaked = sorted(train_families & locked_families)
    if leaked:
        raise LeakageError(leaked)


def _select_families(
    order: list[str],
    sizes: dict[str, int],
    train_size: int,
    *,
    exact: bool,
) -> list[str]:
    """Pick whole families whose sizes sum to at most train_size.

    Preference follows ``order``, which the caller has already shuffled with the seed.
    A family larger than the remaining room stays out of train.
    """
    cap = train_size
    chosen_at: list[tuple[int, ...] | None] = [None] * (cap + 1)
    chosen_at[0] = ()
    for index, family in enumerate(order):
        size = sizes[family]
        if size <= 0 or size > cap:
            continue
        for total in range(cap - size, -1, -1):
            if chosen_at[total] is None:
                continue
            nxt = total + size
            if chosen_at[nxt] is None:
                chosen_at[nxt] = chosen_at[total] + (index,)
    if exact:
        if chosen_at[cap] is None:
            raise SplitPlanError(
                "cannot select exactly 100 train rows without splitting a dialogue family"
            )
        picked = chosen_at[cap]
    else:
        best = 0
        for total in range(cap, -1, -1):
            if chosen_at[total] is not None:
                best = total
                break
        picked = chosen_at[best] or ()
    return [order[index] for index in picked]


def _missing_locked_ids(ids: set[str]) -> list[str]:
    missing: list[str] = []
    for number in range(101, 501):
        row_id = f"kp-{number:03d}"
        if row_id not in ids:
            missing.append(row_id)
    return missing


def plan_spoken_split(
    rows: list[BenchmarkRow | dict[str, Any]],
    *,
    seed: int = DEFAULT_SEED,
    train_size: int = TRAIN_CAP,
    target_total: int = TARGET_TOTAL,
) -> dict[str, Any]:
    """Assign whole dialogue families. Train never exceeds 100 rows."""
    if not rows:
        raise SplitPlanError("no rows")
    capped = min(int(train_size), TRAIN_CAP)
    if capped < 1:
        raise SplitPlanError("train size must be at least 1 and at most 100")
    if len(rows) >= target_total:
        capped = TRAIN_CAP

    groups: dict[str, list[BenchmarkRow | dict[str, Any]]] = {}
    family_of: dict[str, str] = {}
    seen: set[str] = set()
    for row in rows:
        row_id = _id(row)
        if not row_id:
            raise SplitPlanError("row is missing id")
        if row_id in seen:
            raise SplitPlanError(f"duplicate id {row_id}")
        seen.add(row_id)
        family = _family(row)
        family_of[row_id] = family
        groups.setdefault(family, []).append(row)

    order = sorted(groups)
    random.Random(seed).shuffle(order)
    locked_families = {
        family for family, members in groups.items() if any(_is_locked_test(row) for row in members)
    }
    eligible = [family for family in order if family not in locked_families]
    sizes = {family: len(groups[family]) for family in groups}
    exact = len(rows) >= target_total
    selected = set(
        _select_families(eligible, sizes, capped, exact=exact and bool(eligible))
    )
    if locked_families & selected:
        raise LeakageError(sorted(locked_families & selected))

    train_ids: list[str] = []
    locked_ids: list[str] = []
    for family, members in groups.items():
        dest = train_ids if family in selected else locked_ids
        dest.extend(_id(row) for row in members)
    train_ids.sort()
    locked_ids.sort()
    if len(train_ids) > TRAIN_CAP:
        raise SplitPlanError("train cap is 100")
    assert_assignment_disjoint(train_ids, locked_ids, family_of)

    ids = set(family_of)
    missing = _missing_locked_ids(ids)
    references_ready = True
    for row in rows:
        number = _kp_number(_id(row))
        if number is not None and 101 <= number <= 500 and not _reference(row):
            references_ready = False
            break
    pool_complete = not missing and len(rows) >= target_total and references_ready
    native_gold = bool(rows) and all(_is_native_gold(row) for row in rows)
    if pool_complete and len(train_ids) != TRAIN_CAP:
        raise SplitPlanError("a complete 500-row pool must put exactly 100 rows in train")
    if pool_complete and len(locked_ids) != len(rows) - TRAIN_CAP:
        raise SplitPlanError("locked rows must be the remainder after the 100-row train cap")

    return {
        "schema": "spoken-split-plan-1",
        "seed": seed,
        "dialogue_family_safe": True,
        "train_cap": TRAIN_CAP,
        "target_total": target_total,
        "train_count": len(train_ids),
        "locked_count": len(locked_ids),
        "train_ids": train_ids,
        "locked_ids": locked_ids,
        "locked_must_not_be_used_to_train_or_tune": True,
        "locked_pool_complete": pool_complete,
        "native_gold_benchmark": native_gold,
        "not_the_1000_to_2000_native_gold_benchmark": not native_gold,
        "promotion": "not_promoted",
        "when_complete_rule": WHEN_COMPLETE_RULE,
        "note": INCOMPLETE_NOTE if not pool_complete else NOT_NATIVE_GOLD_NOTE,
        "matches_owner_500": (
            pool_complete
            and len(rows) == TARGET_TOTAL
            and len(train_ids) == TRAIN_CAP
            and len(locked_ids) == LOCKED_WHEN_COMPLETE
        ),
    }


def assert_trainable(plan: dict[str, Any], row_id: str) -> None:
    """Raise when a locked id, or any id outside the capped train set, is used to train."""
    if plan.get("train_count", 0) > TRAIN_CAP or len(plan.get("train_ids") or []) > TRAIN_CAP:
        raise SplitPlanError("train cap is 100")
    locked = set(plan.get("locked_ids") or [])
    train = set(plan.get("train_ids") or [])
    if row_id in locked or row_id not in train:
        raise LockedPoolError(
            f"{row_id} is locked or outside the train cap and must not be used to train or tune"
        )


def apply_spoken_split(
    rows: list[BenchmarkRow | dict[str, Any]],
    plan: dict[str, Any],
) -> None:
    """Write split labels. A locked test row cannot move into train."""
    train_ids = set(plan.get("train_ids") or [])
    locked_ids = set(plan.get("locked_ids") or [])
    family_of = {_id(row): _family(row) for row in rows}
    assert_assignment_disjoint(list(train_ids), list(locked_ids), family_of)
    if len(train_ids) > TRAIN_CAP:
        raise SplitPlanError("train cap is 100")
    for row in rows:
        row_id = _id(row)
        if row_id in train_ids:
            target = "train"
        elif row_id in locked_ids:
            target = "test"
        else:
            continue
        if isinstance(row, BenchmarkRow):
            assign_split(row, target)
            if target == "train":
                row.locked = False
        else:
            if row.get("split") == "test" and row.get("locked") and target != "test":
                raise SplitLockError(f"{row_id} is locked in the test split")
            row["split"] = target
            row["locked"] = target == "test"


SCALE_LOCK_COUNT = 1000
SCALE_VERSION = "scale-lock1000-20261023"
HISTORICAL_TRAIN_POOL = 100
SCALE_NOTE = (
    "Once the file has at least 1,000 ids, the last 1,000 ids are the locked "
    "benchmark and earlier ids are the train pool for a later adapter. "
    "Until a 1,000-row lock exists, every id outside the historical train "
    "pool stays locked. This synthetic lock is not the 1,000–2,000 "
    "native-reviewed gold benchmark. 10,000–30,000 reviewed training rows "
    "remain a target. Gemini is the teacher and Jev is the ranker. "
    "Neither one updates weights. 3B, 7B, 8B, and 14B training stays blocked "
    "on this 16 GB machine."
)


def scale_split_spec() -> dict[str, Any]:
    """Policy for the owner scale table. Does not read dialogue rows."""
    return {
        "schema": "spoken-scale-spec-1",
        "version": SCALE_VERSION,
        "lock_count": SCALE_LOCK_COUNT,
        "rule": (
            "last 1000 ids locked when the file has at least 1000 ids; "
            "earlier ids are the train pool"
        ),
        "until_lock_exists": (
            "lock every id outside the historical train pool of the lowest "
            f"{HISTORICAL_TRAIN_POOL} ids"
        ),
        "cut_is_frozen_in_the_version_directory": True,
        "sliding_the_window_later_is_forbidden": True,
        "train_on_locked": False,
        "tune_on_locked": False,
        "native_gold_benchmark": False,
        "not_the_1000_to_2000_native_gold_benchmark": True,
        "promotion": "not_promoted",
        "licence": "unknown",
        "dataset_rows_target": {"min": 10000, "max": 30000, "status": "target_not_current"},
        "native_benchmark_rows_target": {
            "min": 1000,
            "max": 2000,
            "status": "target_not_current",
        },
        "blocked_model_sizes": ["3B", "7B", "8B", "14B"],
        "blocked_reason": "16 GB M4; trainer.start refuses these sizes",
        "gemini_role": "teacher",
        "jev_role": "ranker",
        "weight_update": False,
        "vertex_fine_tune": "not_called",
        "weights_written": False,
        "weights_uploaded": False,
        "prior_plans_deleted": False,
        "note": SCALE_NOTE,
    }


def plan_scale_holdout(row_ids: list[str]) -> dict[str, Any]:
    """Freeze a scale cut for the ids passed in.

    With at least 1,000 ids, lock the 1,000 highest kp numbers and keep every
    earlier id in the train pool. With fewer than 1,000, lock every id outside
    the lowest 100. Callers write the result into a version directory and do
    not slide that cut when later rows are appended.
    """
    numbers: list[tuple[int, str]] = []
    seen: set[int] = set()
    for row_id in row_ids:
        number = _kp_number(row_id)
        if number is None:
            raise SplitPlanError(f"{row_id or '<missing id>'} is not a kp id")
        if number in seen:
            raise SplitPlanError(f"duplicate kp id {row_id}")
        seen.add(number)
        numbers.append((number, row_id))
    ordered = [row_id for _, row_id in sorted(numbers)]
    total = len(ordered)
    if total >= SCALE_LOCK_COUNT:
        locked = ordered[-SCALE_LOCK_COUNT:]
        train = ordered[:-SCALE_LOCK_COUNT]
        rule = "last_1000_ids_locked_earlier_ids_train"
        lock_ready = True
    else:
        train_n = min(HISTORICAL_TRAIN_POOL, total)
        train = ordered[:train_n]
        locked = ordered[train_n:]
        rule = "until_1000_locked_rows_exist_lock_every_id_outside_the_train_pool"
        lock_ready = False
    if set(train) & set(locked):
        raise OverlapError("scale split overlap")
    spec = scale_split_spec()
    return {
        "schema": "spoken-scale-plan-1",
        "version": SCALE_VERSION,
        "rule": rule,
        "row_count": total,
        "train_count": len(train),
        "locked_count": len(locked),
        "train_id_first": train[0] if train else "",
        "train_id_last": train[-1] if train else "",
        "locked_id_first": locked[0] if locked else "",
        "locked_id_last": locked[-1] if locked else "",
        "train_ids": train,
        "locked_ids": locked,
        "lock_count_target": SCALE_LOCK_COUNT,
        "lock_ready": lock_ready,
        "train_on_locked": False,
        "tune_on_locked": False,
        "native_gold_benchmark": False,
        "not_the_1000_to_2000_native_gold_benchmark": True,
        "promotion": "not_promoted",
        "licence": "unknown",
        "weights_written": False,
        "weights_uploaded": False,
        "weight_update": False,
        "blocked_model_sizes": list(spec["blocked_model_sizes"]),
        "gemini_role": "teacher",
        "jev_role": "ranker",
        "dataset_rows_target": dict(spec["dataset_rows_target"]),
        "native_benchmark_rows_target": dict(spec["native_benchmark_rows_target"]),
        "note": SCALE_NOTE,
    }


def assert_scale_not_locked(plan: dict[str, Any], row_id: str) -> None:
    """Raise when a scale-locked id is requested for training or tuning."""
    locked = set(plan.get("locked_ids") or [])
    if row_id in locked:
        raise LockedPoolError(
            f"{row_id} is in the scale holdout and must not be used to train or tune"
        )
