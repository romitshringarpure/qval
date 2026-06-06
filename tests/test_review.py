"""F-10 · Manual review workflow tests.

Covers the queue, decisions (approve/reject/waive + audit trail), owner
assignment, gate integration for the new statuses, decision-packet export, and
the `qval review` CLI (queue / assign / decide / export).
"""
from __future__ import annotations

import json

import pytest

from qval.canonical import (
    CanonicalRun, Case, Finding,
    STATUS_PASSED, STATUS_FAILED, STATUS_NEEDS_REVIEW,
    STATUS_WAIVED, STATUS_APPROVED, STATUS_BLOCKED,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW,
    DECISION_GO, DECISION_NO_GO,
)
from qval.canonical.io import save_canonical, load_canonical
from qval.gate import diff_runs, evaluate, GateThresholds
from qval.review import (
    review_queue, apply_decision, assign_owner, get_finding, owner_of,
    ReviewError, to_csv, to_json,
)


# --- helpers ----------------------------------------------------------------

def run_of(specs):
    """specs: list of (fid, category, status, severity)."""
    cases, findings = [], []
    for fid, cat, status, sev in specs:
        cases.append(Case(case_id=fid, name=f"name-{fid}", category=cat, prompt="p"))
        findings.append(Finding(finding_id=fid, case_id=fid, status=status,
                                severity=sev, response=f"resp-{fid}"))
    return CanonicalRun(run_id="r", source_tool="qval", model="m", provider="p",
                        cases=cases, findings=findings)


# --- queue ------------------------------------------------------------------

def test_queue_sorted_worst_severity_first():
    run = run_of([("a", "x", STATUS_FAILED, SEVERITY_LOW),
                  ("b", "x", STATUS_FAILED, SEVERITY_CRITICAL),
                  ("c", "x", STATUS_NEEDS_REVIEW, SEVERITY_MEDIUM)])
    q = review_queue(run)
    assert [it.finding_id for it in q] == ["b", "c", "a"]


def test_queue_excludes_passed():
    run = run_of([("a", "x", STATUS_PASSED, SEVERITY_LOW),
                  ("b", "x", STATUS_FAILED, SEVERITY_HIGH)])
    assert [it.finding_id for it in review_queue(run)] == ["b"]


def test_queue_include_resolved():
    run = run_of([("a", "x", STATUS_PASSED, SEVERITY_LOW)])
    apply_decision(run, "a", reviewer_id="r1", decision="approve")
    assert review_queue(run) == []
    assert [it.finding_id for it in review_queue(run, include_resolved=True)] == ["a"]


def test_queue_baseline_side_by_side():
    base = run_of([("a", "x", STATUS_PASSED, SEVERITY_HIGH)])
    cur = run_of([("a", "x", STATUS_FAILED, SEVERITY_HIGH)])
    q = review_queue(cur, base)
    assert q[0].baseline_status == STATUS_PASSED
    assert q[0].current_response == "resp-a"


# --- decisions --------------------------------------------------------------

def test_approve_sets_status_and_audit():
    run = run_of([("a", "x", STATUS_FAILED, SEVERITY_HIGH)])
    f = apply_decision(run, "a", reviewer_id="alice", decision="approve",
                       notes="looks fine")
    assert f.status == STATUS_APPROVED
    assert f.reviewers[-1].reviewer_id == "alice"
    assert f.reviewers[-1].decision == "approve"
    assert f.reviewers[-1].decided_at            # timestamp recorded


def test_reject_blocks():
    run = run_of([("a", "x", STATUS_FAILED, SEVERITY_HIGH)])
    f = apply_decision(run, "a", reviewer_id="bob", decision="reject")
    assert f.status == STATUS_BLOCKED


def test_waive_sets_waiver():
    run = run_of([("a", "x", STATUS_FAILED, SEVERITY_HIGH)])
    f = apply_decision(run, "a", reviewer_id="carol", decision="waive",
                       reason="accepted risk", expires_at="2026-12-31T00:00:00+00:00")
    assert f.status == STATUS_WAIVED
    assert f.waiver and f.waiver.reason == "accepted risk"
    assert f.waiver.approver == "carol"
    assert f.waiver.expires_at == "2026-12-31T00:00:00+00:00"


def test_waive_requires_reason():
    run = run_of([("a", "x", STATUS_FAILED, SEVERITY_HIGH)])
    with pytest.raises(ReviewError):
        apply_decision(run, "a", reviewer_id="carol", decision="waive")


def test_unknown_finding_raises():
    run = run_of([("a", "x", STATUS_FAILED, SEVERITY_HIGH)])
    with pytest.raises(ReviewError):
        apply_decision(run, "zzz", reviewer_id="r", decision="approve")


def test_unknown_decision_raises():
    run = run_of([("a", "x", STATUS_FAILED, SEVERITY_HIGH)])
    with pytest.raises(ReviewError):
        apply_decision(run, "a", reviewer_id="r", decision="maybe")


def test_audit_trail_accumulates():
    run = run_of([("a", "x", STATUS_FAILED, SEVERITY_HIGH)])
    apply_decision(run, "a", reviewer_id="r1", decision="reject")
    apply_decision(run, "a", reviewer_id="r2", decision="approve")
    f = get_finding(run, "a")
    assert [r.reviewer_id for r in f.reviewers] == ["r1", "r2"]
    assert f.status == STATUS_APPROVED       # latest decision wins


# --- owner ------------------------------------------------------------------

def test_assign_owner():
    run = run_of([("a", "x", STATUS_FAILED, SEVERITY_HIGH)])
    assign_owner(run, "a", "team-safety")
    assert owner_of(get_finding(run, "a")) == "team-safety"


# --- gate integration -------------------------------------------------------

def test_waive_clears_gate_block():
    cur = run_of([("a", "x", STATUS_FAILED, SEVERITY_CRITICAL)])
    assert evaluate(diff_runs(None, cur)).verdict == DECISION_NO_GO
    apply_decision(cur, "a", reviewer_id="r", decision="waive", reason="ok")
    assert evaluate(diff_runs(None, cur)).verdict == DECISION_GO


def test_reject_keeps_gate_block():
    cur = run_of([("a", "x", STATUS_FAILED, SEVERITY_CRITICAL)])
    apply_decision(cur, "a", reviewer_id="r", decision="reject")
    # blocked is still a failure for the gate
    assert evaluate(diff_runs(None, cur)).verdict == DECISION_NO_GO


def test_approved_counts_toward_pass_rate():
    cur = run_of([("a", "x", STATUS_FAILED, SEVERITY_LOW),
                  ("b", "x", STATUS_PASSED, SEVERITY_LOW)])
    assert diff_runs(None, cur).pass_rate_current == 0.5
    apply_decision(cur, "a", reviewer_id="r", decision="approve")
    assert diff_runs(None, cur).pass_rate_current == 1.0


# --- packet -----------------------------------------------------------------

def test_csv_export_has_header_and_rows():
    run = run_of([("a", "privacy", STATUS_FAILED, SEVERITY_HIGH)])
    apply_decision(run, "a", reviewer_id="alice", decision="waive", reason="ok")
    csv_text = to_csv(run)
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("finding_id,case_id,category")
    assert "alice" in csv_text and "waive" in csv_text and "ok" in csv_text


def test_json_export_has_audit_trail():
    run = run_of([("a", "privacy", STATUS_FAILED, SEVERITY_HIGH)])
    apply_decision(run, "a", reviewer_id="alice", decision="waive", reason="ok")
    packet = json.loads(to_json(run))
    f = packet["findings"][0]
    assert f["reviewers"][0]["reviewer_id"] == "alice"
    assert f["waiver"]["reason"] == "ok"


# --- CLI --------------------------------------------------------------------

def _write(run, path):
    save_canonical(run, path)
    return str(path)


def test_cli_queue(tmp_path, capsys):
    from qval.cli import main
    src = _write(run_of([("a", "x", STATUS_FAILED, SEVERITY_CRITICAL)]), tmp_path / "r.json")
    rc = main(["review", "queue", src])
    assert rc == 0
    assert "critical" in capsys.readouterr().out


def test_cli_decide_persists_in_place(tmp_path):
    from qval.cli import main
    src = _write(run_of([("a", "x", STATUS_FAILED, SEVERITY_CRITICAL)]), tmp_path / "r.json")
    rc = main(["review", "decide", src, "--finding", "a",
               "--decision", "waive", "--reviewer", "alice", "--reason", "ok"])
    assert rc == 0
    reloaded = load_canonical(src)
    assert reloaded.findings[0].status == STATUS_WAIVED
    assert reloaded.findings[0].waiver.reason == "ok"


def test_cli_decide_waive_without_reason_exit_2(tmp_path):
    from qval.cli import main
    src = _write(run_of([("a", "x", STATUS_FAILED, SEVERITY_HIGH)]), tmp_path / "r.json")
    rc = main(["review", "decide", src, "--finding", "a",
               "--decision", "waive", "--reviewer", "alice"])
    assert rc == 2


def test_cli_assign_persists(tmp_path):
    from qval.cli import main
    src = _write(run_of([("a", "x", STATUS_FAILED, SEVERITY_HIGH)]), tmp_path / "r.json")
    rc = main(["review", "assign", src, "--finding", "a", "--owner", "team-x"])
    assert rc == 0
    assert owner_of(load_canonical(src).findings[0]) == "team-x"


def test_cli_export_csv_to_file(tmp_path):
    from qval.cli import main
    src = _write(run_of([("a", "x", STATUS_FAILED, SEVERITY_HIGH)]), tmp_path / "r.json")
    out = tmp_path / "packet.csv"
    rc = main(["review", "export", src, "--format", "csv", "--out", str(out)])
    assert rc == 0
    assert out.read_text(encoding="utf-8").startswith("finding_id,")


def test_cli_review_bad_path_exit_2(tmp_path):
    from qval.cli import main
    rc = main(["review", "queue", str(tmp_path / "missing.json")])
    assert rc == 2
