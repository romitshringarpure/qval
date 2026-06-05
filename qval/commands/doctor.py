from __future__ import annotations

import argparse


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser("doctor")
    sub.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    return 0
