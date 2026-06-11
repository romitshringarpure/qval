"""`qval map` — stamp governance controls onto a canonical run (F-07).

Loads a canonical run, maps each finding's category to its governance controls
(OWASP-LLM / NIST AI RMF) via the catalog, prints a coverage matrix, and
optionally writes the enriched run. The enriched run feeds the gate, report,
and evidence pack — control_ids and the controls list are populated for them.
Exits 0 on success; input/catalog errors exit 2.
"""
from __future__ import annotations

import argparse

from qval.canonical.io import load_canonical, save_canonical
from qval.controls import (
    load_catalog, map_controls, coverage, ControlCatalogError,
    COVERAGE_FAILED, COVERAGE_NEEDS_REVIEW, COVERAGE_NOT_EXERCISED,
)

_MARK = {
    COVERAGE_FAILED: "FAIL",
    COVERAGE_NEEDS_REVIEW: "REVIEW",
    COVERAGE_NOT_EXERCISED: "GAP",
}


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser(
        "map",
        help="Map a run's findings to governance controls and show coverage.",
        description="Stamp OWASP-LLM / NIST AI RMF control ids onto a canonical "
                    "run's findings and report per-control coverage.",
    )
    sub.add_argument("run", help="Path to the canonical run.json to map.")
    sub.add_argument("--out", default=None,
                     help="Write the run with controls attached here.")
    sub.add_argument("--catalog", default=None,
                     help="Path to a control catalog JSON. Default: built-in "
                          "config/controls.json.")
    sub.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    try:
        catalog = load_catalog(args.catalog)
    except ControlCatalogError as e:
        print(f"qval map: {e}")
        return 2

    try:
        run_obj = load_canonical(args.run)
    except ValueError as e:
        print(f"qval map: {e}")
        return 2

    map_controls(run_obj, catalog)
    _print_coverage(coverage(run_obj))

    if args.out:
        save_canonical(run_obj, args.out)
        print(f"\nMapped run written to {args.out}")
    return 0


def _print_coverage(rows) -> None:
    if not rows:
        print("No controls exercised (no findings mapped to a catalog category).")
        return
    print("Control coverage:")
    for c in rows:
        mark = _MARK.get(c.status, "PASS")
        print(f"  [{mark:>6}] {c.control_id} ({c.framework}) — {c.title}: "
              f"{c.passed}/{c.total} passed")
