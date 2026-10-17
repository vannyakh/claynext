"""CLI: list / install optional tool backends (uv extras)."""
from __future__ import annotations

import argparse
import json

from claynext.cli.common import die, make_progress


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("features", help="List or install optional tool backends")
    sp = p.add_subparsers(dest="features_cmd", required=True)

    list_p = sp.add_parser("list", help="Show backend status")
    list_p.add_argument("--json", action="store_true", help="Machine-readable output")
    list_p.set_defaults(func=run_list)

    inst = sp.add_parser("install", help="Run uv sync --extra <name>")
    inst.add_argument(
        "extra",
        help="Extra id or feature id (demucs, demucs-mlx, voxcpm, whisperx, gender)",
    )
    inst.add_argument("-q", "--quiet", action="store_true")
    inst.set_defaults(func=run_install)


def run_list(args: argparse.Namespace) -> int:
    from claynext.models.features import list_features

    rows = list_features()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("No optional features registered.")
        return 0
    width = max(len(r["label"]) for r in rows)
    for r in rows:
        print(f"{r['label']:<{width}}  {r['status']:<14}  extra={r.get('extra') or '-'}")
    return 0


def run_install(args: argparse.Namespace) -> int:
    from claynext.models.features import FEATURE_REGISTRY, install_uv_extra

    key = str(args.extra or "").strip()
    extra = key
    for item in FEATURE_REGISTRY:
        if key in {item["id"], item["extra"]}:
            extra = item["extra"]
            break
    progress = make_progress(args.quiet)
    try:
        install_uv_extra(extra, progress_callback=progress)
    except Exception as exc:
        die(str(exc))
    print(f"installed · uv sync --extra {extra}")
    return 0
