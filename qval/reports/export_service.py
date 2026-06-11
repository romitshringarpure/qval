"""Export helpers for the local UI sign-off screen."""

from __future__ import annotations

from pathlib import Path

from qval.engine.run_service import load_run
from qval.evidence import build_pack
from qval.gate import diff_runs, evaluate
from qval.reports.canonical_report import render_html, render_markdown
from qval.utils.file_loader import outputs_dir


def export_run(run_id: str, fmt: str) -> Path:
    """Write a report or evidence pack using existing report/pack primitives."""

    run = load_run(run_id)
    decision = run.decision or evaluate(diff_runs(None, run))
    run.decision = decision

    if fmt == "markdown":
        path = outputs_dir() / "reports" / f"{run_id}.signoff.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(run, None, decision), encoding="utf-8")
        return path
    if fmt == "html":
        path = outputs_dir() / "reports" / f"{run_id}.signoff.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_html(run, None, decision), encoding="utf-8")
        return path
    if fmt == "evidence-pack":
        _pack, out_dir = build_pack(run, outputs_dir() / "evidence" / run_id)
        return out_dir
    raise ValueError("format must be one of: html, markdown, evidence-pack")
