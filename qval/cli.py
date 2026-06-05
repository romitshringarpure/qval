"""Qval command-line entry point.

Usage:
    qval init | doctor | run | gate | report | import
"""
from __future__ import annotations

import argparse

from qval.commands import init as init_cmd
from qval.commands import doctor as doctor_cmd
from qval.commands import run as run_cmd
from qval.commands import stubs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qval",
        description="AI release-governance and QA sign-off layer above eval tools.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    init_cmd.add_parser(subparsers)
    doctor_cmd.add_parser(subparsers)
    run_cmd.add_parser(subparsers)
    stubs.add_parsers(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
