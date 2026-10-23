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

    inst = sp.add_parser("install", help="Install one extra, or all optional extras")
    inst.add_argument(
        "extra",
        help="Extra id, feature id, or 'all' (demucs, demucs-mlx, voxcpm, omnivoice, whisperx, gender)",
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
        line = f"{r['label']:<{width}}  {r['status']:<14}  extra={r.get('extra') or '-'}"
        if r["status"] == "Unsupported" and r.get("hint"):
            line += f"  · {r['hint']}"
        print(line)
    return 0


def run_install(args: argparse.Namespace) -> int:
    from claynext.models.features import FEATURE_REGISTRY, install_dev_environment, install_uv_extra

    key = str(args.extra or "").strip()
    progress = make_progress(args.quiet)
    if key == "all":
        try:
            result = install_dev_environment(progress_callback=progress, apply_preferences=True)
        except Exception as exc:
            die(str(exc))
        failed = list(result.get("failed") or [])
        if failed:
            detail = "; ".join(
                f"{item.get('extra')}: {item.get('error')}" for item in failed
            )
            die(detail or "Some extras could not be installed.")
        print(f"installed · {result.get('command') or 'development environment'}")
        return 0
    extra = key
    for item in FEATURE_REGISTRY:
        if key in {item["id"], item["extra"]}:
            extra = item["extra"]
            break
    try:
        result = install_uv_extra(extra, progress_callback=progress)
    except Exception as exc:
        die(str(exc))
    print(f"installed · {result.get('command') or extra}")
    return 0
