"""Benchmark package. Reports default to not promoted and not a gold score."""
from claynext.models.benchmarks.comparison import comparison_report
from claynext.models.benchmarks.leaderboard import leaderboard
from claynext.models.benchmarks.promotion import PROPOSED_GATES, evaluate_promotion
from claynext.models.benchmarks.runner import run_benchmark
from claynext.models.benchmarks.schema import BenchmarkRow
from claynext.models.benchmarks.spoken_split import (
    incomplete_split_spec,
    plan_scale_holdout,
    plan_spoken_split,
)

__all__ = [
    "BenchmarkRow",
    "PROPOSED_GATES",
    "comparison_report",
    "evaluate_promotion",
    "incomplete_split_spec",
    "leaderboard",
    "plan_scale_holdout",
    "plan_spoken_split",
    "run_benchmark",
]
