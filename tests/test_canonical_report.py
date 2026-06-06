"""F-05 · Canonical release report tests.

Covers the pure renderers (render_markdown / render_html over CanonicalRun +
RunDiff + Decision) and the `qval report` CLI.
"""
from __future__ import annotations

from pathlib import Path

from qval.canonical import (
    CanonicalRun, Case, Finding, Decision,
    STATUS_PASSED, STATUS_FAILED,
    SEVERITY_CRITICAL, SEVERITY_LOW,
    DECISION_NO_GO,
)
from qval.canonical.io import save_canonical
from qval.gate import diff_runs
from qval.reports.canonical_report import render_markdown, render_html


def run_of(specs, *, decision=None) -> CanonicalRun:
    """specs: list of (case_id, status, severity)."""
    cases, findings = [], []
    for cid, status, sev in specs:
        cases.append(Case(case_id=cid, name=f"Case {cid}", category="privacy", prompt="p"))
        findings.append(Finding(finding_id=cid, case_id=cid, status=status,
                                severity=sev, score=0.5, reason=f"reason-{cid}"))
    return CanonicalRun(run_id="run-1", source_tool="promptfoo", model="gpt-4o",
                        provider="openai", suite="demo", cases=cases,
                        findings=findings, decision=decision)


def _nogo() -> Decision:
    return Decision(verdict=DECISION_NO_GO,
                    rationale=["1 new critical finding(s) vs baseline"],
                    policy_version="builtin-v1")


# --- markdown ---------------------------------------------------------------

def test_markdown_has_model_and_findings():
    md = render_markdown(run_of([("c1", STATUS_PASSED, SEVERITY_LOW)]), None, None)
    assert "gpt-4o" in md
    assert "Case c1" in md
    assert "reason-c1" in md


def test_markdown_has_decision_and_verdict():
    md = render_markdown(run_of([("c1", STATUS_FAILED, SEVERITY_CRITICAL)]), None, _nogo())
    assert "DECISION" in md
    assert "NO-GO" in md
    assert "1 new critical finding(s) vs baseline" in md


def test_markdown_has_baseline_diff_section():
    base = run_of([("c1", STATUS_PASSED, SEVERITY_LOW)])
    cur = run_of([("c1", STATUS_FAILED, SEVERITY_CRITICAL)])
    diff = diff_runs(base, cur)
    md = render_markdown(cur, diff, _nogo())
    assert "Baseline" in md
    assert "Case c1" in md


def test_markdown_ungated_notes_not_gated():
    md = render_markdown(run_of([("c1", STATUS_PASSED, SEVERITY_LOW)]), None, None)
    assert "not been gated" in md.lower()


# --- html -------------------------------------------------------------------

def test_html_is_a_full_document():
    html = render_html(run_of([("c1", STATUS_PASSED, SEVERITY_LOW)]), None, _nogo())
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert "NO-GO" in html


def test_html_has_severity_pill():
    html = render_html(run_of([("c1", STATUS_FAILED, SEVERITY_CRITICAL)]), None, _nogo())
    assert "pill-critical" in html


# --- CLI --------------------------------------------------------------------

def _write_run(run, path):
    save_canonical(run, path)
    return str(path)


def test_cli_report_markdown_writes_file(tmp_path):
    from qval.cli import main
    src = _write_run(run_of([("c1", STATUS_FAILED, SEVERITY_CRITICAL)]), tmp_path / "run.json")
    out = tmp_path / "report.md"
    rc = main(["report", src, "--format", "markdown", "--out", str(out)])
    assert rc == 0
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "DECISION" in text and "gpt-4o" in text


def test_cli_report_html_writes_file(tmp_path):
    from qval.cli import main
    src = _write_run(run_of([("c1", STATUS_PASSED, SEVERITY_LOW)]), tmp_path / "run.json")
    out = tmp_path / "report.html"
    rc = main(["report", src, "--format", "html", "--out", str(out)])
    assert rc == 0
    assert out.is_file()
    assert "<!DOCTYPE html>" in out.read_text(encoding="utf-8")


def test_cli_report_both_writes_both(tmp_path):
    from qval.cli import main
    src = _write_run(run_of([("c1", STATUS_PASSED, SEVERITY_LOW)]), tmp_path / "run.json")
    base = tmp_path / "rep"
    rc = main(["report", src, "--format", "both", "--out", str(base)])
    assert rc == 0
    assert (tmp_path / "rep.md").is_file()
    assert (tmp_path / "rep.html").is_file()


def test_cli_report_with_baseline_adds_diff(tmp_path):
    from qval.cli import main
    base = _write_run(run_of([("c1", STATUS_PASSED, SEVERITY_LOW)]), tmp_path / "base.json")
    cur = _write_run(run_of([("c1", STATUS_FAILED, SEVERITY_CRITICAL)]), tmp_path / "cur.json")
    out = tmp_path / "report.md"
    rc = main(["report", cur, "--baseline", base, "--format", "markdown", "--out", str(out)])
    assert rc == 0
    assert "Baseline" in out.read_text(encoding="utf-8")


def test_cli_report_bad_path_exit_2(tmp_path):
    from qval.cli import main
    rc = main(["report", str(tmp_path / "missing.json"), "--out", str(tmp_path / "r.html")])
    assert rc == 2


def test_cli_report_uses_persisted_decision(tmp_path):
    from qval.cli import main
    run = run_of([("c1", STATUS_FAILED, SEVERITY_CRITICAL)], decision=_nogo())
    src = _write_run(run, tmp_path / "run.json")
    out = tmp_path / "report.md"
    rc = main(["report", src, "--format", "markdown", "--out", str(out)])
    assert rc == 0
    assert "NO-GO" in out.read_text(encoding="utf-8")
