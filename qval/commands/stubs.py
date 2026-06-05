"""Stub subcommands for features not yet implemented (gate/report/import).

Registered so the command surface is complete and discoverable now; each owning
feature (F-04 gate, F-05 report, F-03 import) replaces its stub.
"""
from __future__ import annotations

import argparse

NOT_IMPLEMENTED_EXIT = 3

_STUBS = {
    "gate": "F-04",
    "report": "F-05",
    "import": "F-03",
}


def _make_run(name: str, feature: str):
    def run(args: argparse.Namespace) -> int:
        print(f"qval {name}: not implemented yet — ships in {feature}.")
        return NOT_IMPLEMENTED_EXIT
    return run


def add_parsers(subparsers) -> None:
    for name, feature in _STUBS.items():
        sub = subparsers.add_parser(name, help=f"(not implemented — {feature})")
        sub.set_defaults(func=_make_run(name, feature))
