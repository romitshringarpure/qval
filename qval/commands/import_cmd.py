"""`qval import <tool> <path>` — normalize external eval results (F-03).

Tool-agnostic: the ``tool`` choices come from the importer registry, so adding
an importer makes it selectable here with no edits to this file. Reads a tool's
results, maps them to a ``CanonicalRun``, and writes a canonical ``run.json``.
"""
from __future__ import annotations

import argparse

from qval.canonical.io import save_canonical
from qval.canonical.schema import ALL_SEVERITIES, SEVERITY_INFO, STATUS_PASSED
from qval.importers import available_tools, get_importer


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser(
        "import",
        help="Import external eval results (e.g. Promptfoo) into a canonical run.json.",
        description="Normalize an external eval tool's results into Qval's "
                    "canonical run.json.",
    )
    sub.add_argument(
        "tool", choices=available_tools(),
        help="Which eval tool produced the results.",
    )
    sub.add_argument(
        "path",
        help="Path to the tool's results file, or a directory containing it.",
    )
    sub.add_argument(
        "--out", default="run.json",
        help="Where to write the canonical run.json. Default: ./run.json",
    )
    sub.add_argument(
        "--default-severity", default=SEVERITY_INFO, choices=list(ALL_SEVERITIES),
        help="Severity for findings whose results carry no explicit severity. "
             "Default: info.",
    )
    sub.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    importer = get_importer(args.tool)
    try:
        canonical = importer.import_path(
            args.path, default_severity=args.default_severity
        )
    except ValueError as e:
        print(f"qval import: {e}")
        return 1

    out_path = save_canonical(canonical, args.out)

    passed = sum(1 for f in canonical.findings if f.status == STATUS_PASSED)
    failed = len(canonical.findings) - passed
    print(f"Imported {len(canonical.findings)} findings from {args.tool} "
          f"({passed} passed, {failed} failed).")
    print(f"Canonical run written to {out_path}")
    return 0
