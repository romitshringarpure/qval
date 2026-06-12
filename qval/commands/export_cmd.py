"""`qval export <tool> --suite <name> --out <path>` — F-17.

The reverse of `qval import`: take a qval native suite and render it into a
runnable config for another eval tool (Promptfoo, DeepEval), writing the config
plus a `<out>.fidelity.md` report of what translated cleanly vs degraded.

Tool-agnostic: the exporter is looked up from the registry, so adding an
exporter makes it usable here with no edits to this file. Tool and suite are
validated at runtime (not via argparse ``choices``) so an unknown value exits 1
with a helpful list rather than argparse's terse exit 2.
"""
from __future__ import annotations

import argparse

from qval.engine.schemas import TestCase
from qval.exporters import available_tools, get_exporter
from qval.project import require_project, set_active_project, ProjectNotFoundError
from qval.utils.file_loader import ALL_SUITES, load_all_suites, load_test_suite


def add_parser(subparsers) -> None:
    tools = ", ".join(available_tools()) or "(none)"
    sub = subparsers.add_parser(
        "export",
        help="Export a qval suite into a runnable Promptfoo/DeepEval config.",
        description="Render a qval native test suite into another eval tool's "
                    "config, with a fidelity report on what translated cleanly.",
    )
    sub.add_argument("tool", help=f"Target eval tool. One of: {tools}.")
    sub.add_argument(
        "--suite", required=True,
        help=f"Suite to export: 'all' or one of {', '.join(ALL_SUITES)}.",
    )
    sub.add_argument(
        "--out", required=True,
        help="Where to write the config. A '<out>.fidelity.md' report is "
             "written alongside it.",
    )
    sub.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    # Validate the tool first so an unknown tool fails fast (exit 1) without
    # needing a project on disk.
    try:
        exporter = get_exporter(args.tool)
    except ValueError as e:
        print(f"qval export: {e}")
        return 1

    # Anchor suite-path resolution at the discovered project root (U-00).
    try:
        project = require_project()
    except ProjectNotFoundError as exc:
        print(exc)
        return 2
    set_active_project(project)

    try:
        cases = _load_cases(args.suite)
    except ValueError as e:
        print(f"qval export: {e}")
        return 1

    written = exporter.export_to_path(cases, args.suite, args.out)
    print(written.result.fidelity.render_table())
    print("")
    print(f"Config written to   {written.output_path}")
    print(f"Fidelity report at  {written.fidelity_path}")
    return 0


def _load_cases(suite: str) -> list[TestCase]:
    """Load a suite by name into validated TestCase objects.

    ``all`` loads the core suites (same set as ``qval run --suite all``); any
    other value resolves to a single named suite. ``load_test_suite`` raises
    ValueError on an unknown name — surfaced by the caller as exit 1.
    """
    raws = load_all_suites() if suite == "all" else load_test_suite(suite)
    return [TestCase.from_dict(raw, source=suite) for raw in raws]
