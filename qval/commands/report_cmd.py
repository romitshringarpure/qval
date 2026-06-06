"""`qval report` — render a canonical run into HTML/Markdown (F-05).

Loads a canonical run, derives the gate decision (persisted if the run was
gated, else computed via the F-04 engine) and an optional baseline diff, and
writes a shareable report. A report never gates the exit code — that is
`qval gate`'s job; this always exits 0 on success.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from qval.canonical.io import load_canonical
from qval.gate import diff_runs, evaluate
from qval.reports.canonical_report import render_markdown, render_html


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser(
        "report",
        help="Render a canonical run (with its gate decision) into HTML/Markdown.",
        description="Produce a shareable HTML or Markdown release report from a "
                    "canonical run.json.",
    )
    sub.add_argument("run", help="Path to the canonical run.json to render.")
    sub.add_argument("--baseline", default=None,
                     help="Baseline run.json to include a diff section.")
    sub.add_argument("--format", default="html",
                     choices=["html", "markdown", "both"],
                     help="Output format. Default: html.")
    sub.add_argument("--out", default=None,
                     help="Output path. Default: report.<ext>. For --format both, "
                          "the stem is used for both files.")
    sub.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    try:
        run_obj = load_canonical(args.run)
        baseline = load_canonical(args.baseline) if args.baseline else None
    except ValueError as e:
        print(f"qval report: {e}")
        return 2

    diff = diff_runs(baseline, run_obj) if baseline is not None else None

    decision = run_obj.decision
    if decision is None:
        decision = evaluate(diff if diff is not None else diff_runs(None, run_obj))

    written: list[Path] = []
    if args.format in ("markdown", "both"):
        path = _target(args.out, "md", args.format)
        path.write_text(render_markdown(run_obj, diff, decision), encoding="utf-8")
        written.append(path)
    if args.format in ("html", "both"):
        path = _target(args.out, "html", args.format)
        path.write_text(render_html(run_obj, diff, decision), encoding="utf-8")
        written.append(path)

    for p in written:
        print(f"Report written to {p}")
    return 0


def _target(out: str | None, ext: str, fmt: str) -> Path:
    if not out:
        return Path(f"report.{ext}")
    p = Path(out)
    if fmt == "both":
        return p.with_suffix(f".{ext}")
    return p if p.suffix else p.with_suffix(f".{ext}")
