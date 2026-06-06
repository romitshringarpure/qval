"""F-04 · Baseline diff + qval gate tests.

Covers the pure diff engine (diff_runs), the pure decision engine (evaluate +
GateThresholds), and the `qval gate` CLI. Runs are built in-memory from
canonical objects — no files except the CLI round-trip via save/load_canonical.
"""
from __future__ import annotations

import pytest

from qval.canonical import (
    CanonicalRun, Case, Finding,
    STATUS_PASSED, STATUS_FAILED, STATUS_NEEDS_REVIEW,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO,
    DECISION_GO, DECISION_CONDITIONAL_GO, DECISION_NO_GO,
)
from qval.canonical.io import save_canonical, load_canonical
from qval.gate.diff import diff_runs, RunDiff
from qval.gate.decision import evaluate, GateThresholds


# --- helpers ----------------------------------------------------------------

def run_of(specs, *, run_id="run", categories=None) -> CanonicalRun:
    """specs: list of (case_id, status, severity)."""
    cats = categories or {}
    cases, findings = [], []
    for cid, status, sev in specs:
        cases.append(Case(case_id=cid, name=cid, category=cats.get(cid, "general"),
                          prompt="p"))
        findings.append(Finding(finding_id=cid, case_id=cid, status=status, severity=sev))
    return CanonicalRun(run_id=run_id, source_tool="qval", model="m", provider="p",
                        cases=cases, findings=findings)


# --- diff -------------------------------------------------------------------

def test_new_failure_detected():
    base = run_of([("c1", STATUS_PASSED, SEVERITY_LOW)])
    cur = run_of([("c1", STATUS_FAILED, SEVERITY_HIGH)])
    diff = diff_runs(base, cur)
    assert [f.case_id for f in diff.new_failures] == ["c1"]


def test_improvement_detected():
    base = run_of([("c1", STATUS_FAILED, SEVERITY_HIGH)])
    cur = run_of([("c1", STATUS_PASSED, SEVERITY_HIGH)])
    diff = diff_runs(base, cur)
    assert [f.case_id for f in diff.improvements] == ["c1"]


def test_severity_regression_among_failures():
    base = run_of([("c1", STATUS_FAILED, SEVERITY_MEDIUM)])
    cur = run_of([("c1", STATUS_FAILED, SEVERITY_CRITICAL)])
    diff = diff_runs(base, cur)
    assert [r.case_id for r in diff.severity_regressions] == ["c1"]
    assert diff.severity_regressions[0].to_severity == SEVERITY_CRITICAL
    # already failing -> not counted as a *new* failure
    assert diff.new_failures == []


def test_status_regression_is_new_failure():
    base = run_of([("c1", STATUS_PASSED, SEVERITY_HIGH)])
    cur = run_of([("c1", STATUS_FAILED, SEVERITY_HIGH)])
    diff = diff_runs(base, cur)
    assert [f.case_id for f in diff.new_failures] == ["c1"]


def test_no_baseline_treats_all_failures_as_new():
    cur = run_of([("c1", STATUS_FAILED, SEVERITY_CRITICAL),
                  ("c2", STATUS_PASSED, SEVERITY_LOW)])
    diff = diff_runs(None, cur)
    assert [f.case_id for f in diff.new_failures] == ["c1"]


def test_pass_rate_delta():
    base = run_of([("c1", STATUS_PASSED, SEVERITY_LOW),
                   ("c2", STATUS_PASSED, SEVERITY_LOW)])
    cur = run_of([("c1", STATUS_PASSED, SEVERITY_LOW),
                  ("c2", STATUS_FAILED, SEVERITY_LOW)])
    diff = diff_runs(base, cur)
    assert diff.pass_rate_baseline == 1.0
    assert diff.pass_rate_current == 0.5
    assert diff.pass_rate_delta == -0.5


def test_category_regression():
    cats = {"c1": "privacy"}
    base = run_of([("c1", STATUS_PASSED, SEVERITY_LOW)], categories=cats)
    cur = run_of([("c1", STATUS_FAILED, SEVERITY_LOW)], categories=cats)
    diff = diff_runs(base, cur)
    assert [c.category for c in diff.category_regressions] == ["privacy"]


def test_identical_runs_have_empty_diff():
    specs = [("c1", STATUS_PASSED, SEVERITY_LOW), ("c2", STATUS_PASSED, SEVERITY_LOW)]
    diff = diff_runs(run_of(specs), run_of(specs))
    assert diff.new_failures == []
    assert diff.severity_regressions == []
    assert diff.improvements == []


# --- decision ---------------------------------------------------------------

def _decide(base_specs, cur_specs, thresholds=None, **kw):
    base = run_of(base_specs, **kw) if base_specs is not None else None
    cur = run_of(cur_specs, **kw)
    diff = diff_runs(base, cur)
    return evaluate(diff, thresholds or GateThresholds())


def test_go_when_clean():
    d = _decide([("c1", STATUS_PASSED, SEVERITY_LOW)],
                [("c1", STATUS_PASSED, SEVERITY_LOW)])
    assert d.verdict == DECISION_GO


def test_nogo_on_new_critical():
    d = _decide([("c1", STATUS_PASSED, SEVERITY_LOW)],
                [("c1", STATUS_FAILED, SEVERITY_CRITICAL)])
    assert d.verdict == DECISION_NO_GO


def test_nogo_on_preexisting_critical_floor():
    # critical was already failing in baseline -> not "new", but floor still blocks
    d = _decide([("c1", STATUS_FAILED, SEVERITY_CRITICAL)],
                [("c1", STATUS_FAILED, SEVERITY_CRITICAL)])
    assert d.verdict == DECISION_NO_GO


def test_nogo_below_min_pass_rate():
    d = _decide([("c1", STATUS_PASSED, SEVERITY_LOW), ("c2", STATUS_PASSED, SEVERITY_LOW)],
                [("c1", STATUS_PASSED, SEVERITY_LOW), ("c2", STATUS_FAILED, SEVERITY_LOW)],
                thresholds=GateThresholds(min_pass_rate=0.9))
    assert d.verdict == DECISION_NO_GO


def test_conditional_on_new_medium():
    d = _decide([("c1", STATUS_PASSED, SEVERITY_LOW)],
                [("c1", STATUS_FAILED, SEVERITY_MEDIUM)])
    assert d.verdict == DECISION_CONDITIONAL_GO


def test_conditional_on_needs_review():
    d = _decide([("c1", STATUS_PASSED, SEVERITY_LOW)],
                [("c1", STATUS_NEEDS_REVIEW, SEVERITY_LOW)])
    assert d.verdict == DECISION_CONDITIONAL_GO


def test_rationale_present_on_nogo():
    d = _decide(None, [("c1", STATUS_FAILED, SEVERITY_CRITICAL)])
    assert d.verdict == DECISION_NO_GO
    assert d.rationale and all(isinstance(r, str) for r in d.rationale)
    assert d.policy_version == "builtin-v1"


def test_block_severity_override_relaxes_high():
    # only critical blocks as "new"; a new high becomes conditional, not no-go
    d = _decide([("c1", STATUS_PASSED, SEVERITY_LOW)],
                [("c1", STATUS_FAILED, SEVERITY_HIGH)],
                thresholds=GateThresholds(block_new_severities=frozenset({SEVERITY_CRITICAL})))
    assert d.verdict == DECISION_CONDITIONAL_GO


# --- CLI --------------------------------------------------------------------

def _write(run, path):
    save_canonical(run, path)
    return str(path)


def test_cli_gate_nogo_exit_1(tmp_path, capsys):
    from qval.cli import main
    base = _write(run_of([("c1", STATUS_PASSED, SEVERITY_LOW)]), tmp_path / "b.json")
    cur = _write(run_of([("c1", STATUS_FAILED, SEVERITY_CRITICAL)]), tmp_path / "c.json")
    rc = main(["gate", "--current", cur, "--baseline", base])
    out = capsys.readouterr().out
    assert rc == 1
    assert "NO-GO" in out


def test_cli_gate_go_exit_0(tmp_path, capsys):
    from qval.cli import main
    base = _write(run_of([("c1", STATUS_PASSED, SEVERITY_LOW)]), tmp_path / "b.json")
    cur = _write(run_of([("c1", STATUS_PASSED, SEVERITY_LOW)]), tmp_path / "c.json")
    rc = main(["gate", "--current", cur, "--baseline", base])
    assert rc == 0
    assert "GO" in capsys.readouterr().out


def test_cli_gate_out_persists_decision(tmp_path):
    from qval.cli import main
    cur = _write(run_of([("c1", STATUS_FAILED, SEVERITY_CRITICAL)]), tmp_path / "c.json")
    out = tmp_path / "gated.json"
    rc = main(["gate", "--current", cur, "--out", str(out)])
    assert rc == 1
    gated = load_canonical(out)
    assert gated.decision is not None
    assert gated.decision.verdict == DECISION_NO_GO


def test_cli_gate_bad_path_exit_2(tmp_path, capsys):
    from qval.cli import main
    rc = main(["gate", "--current", str(tmp_path / "missing.json")])
    assert rc == 2
