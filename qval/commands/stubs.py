"""Stub subcommands for features not yet implemented.

The registry is empty today — init/doctor/run/import/gate/report are all real.
Kept as the seam where a future not-yet-built command (F-06+) is registered so
the command surface stays discoverable before its feature lands.
"""
from __future__ import annotations

import argparse

NOT_IMPLEMENTED_EXIT = 3

# name -> owning feature. Empty until the next unbuilt command is scaffolded.
_STUBS: dict[str, str] = {}


def _make_run(name: str, feature: str):
    def run(args: argparse.Namespace) -> int:
        print(f"qval {name}: not implemented yet — ships in {feature}.")
        return NOT_IMPLEMENTED_EXIT
    return run


def add_parsers(subparsers) -> None:
    for name, feature in _STUBS.items():
        sub = subparsers.add_parser(name, help=f"(not implemented — {feature})")
        sub.set_defaults(func=_make_run(name, feature))
