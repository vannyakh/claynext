"""Launch Claynext Studio GUI from the CLI."""
from __future__ import annotations

import argparse


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("gui", help="Open Claynext Studio (desktop UI)")
    p.add_argument("--project", metavar="PATH", help="Open a .claynext.json project")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    argv: list[str] = []
    if args.project:
        argv.extend(["--project", args.project])
    from claynext.app import main as gui_main

    gui_main(argv)
    return 0
