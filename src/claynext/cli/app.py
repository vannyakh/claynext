"""Claynext CLI — headless tools + GUI launcher."""
from __future__ import annotations

import argparse
import sys

from claynext import APP_NAME, APP_VERSION
from claynext.cli import (
    cmd_asr,
    cmd_dataset,
    cmd_dub,
    cmd_features,
    cmd_gui,
    cmd_plan,
    cmd_translate,
    cmd_tts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claynext",
        description=f"{APP_NAME} - AI movie dubbing tools (GUI + CLI)",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"{APP_NAME} {APP_VERSION}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cmd_gui.add_parser(sub)
    cmd_dub.add_parser(sub)
    cmd_asr.add_parser(sub)
    cmd_tts.add_parser(sub)
    cmd_translate.add_parser(sub)
    cmd_plan.add_parser(sub)
    cmd_features.add_parser(sub)
    cmd_dataset.add_parser(sub)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    try:
        return int(func(args) or 0)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
