"""F-06 · Policy-as-code tests.

Covers the policy loader (policy.yaml -> GateThresholds + version stamp), the
require_review verdict path in the decision engine, and the `qval gate --policy`
wiring (load, override precedence, provenance stamp, error handling).
"""
from __future__ import annotations

import pytest

from qval.canonical import (
    CanonicalRun, Case, Finding,
    STATUS_PASSED, STATUS_FAILED,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW,
    DECISION_GO, DECISION_CONDITIONAL_GO, DECISION_NO_GO,
)
from qval.canonical.io import save_canonical, load_canonical
from qval.gate import diff_runs, evaluate, GateThresholds
from qval.gate.policy import load_policy, discover_policy, PolicyError


# --- helpers ----------------------------------------------------------------

def run_of(specs, *, run_id="run") -> CanonicalRun:
    cases, findings = [], []
    for cid, status, sev in specs:
        cases.append(Case(case_id=cid, name=cid, category="general", prompt="p"))
        findings.append(Finding(finding_id=cid, case_id=cid, status=status, severity=sev))
    return CanonicalRun(run_id=run_id, source_tool="qval", model="m", provider="p",
                        cases=cases, findings=findings)


def write_policy(tmp_path, text, name="policy.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# --- loader -----------------------------------------------------------------

def test_load_full_policy_maps_all_fields(tmp_path):
    p = write_policy(tmp_path, """
version: "2.1"
release_policy:
  block_on:
    - severity: critical
    - severity: high
  critical_floor: false
  pass_rate_floor: 0.85
  require_review:
    - severity: medium
""")
    loaded = load_policy(p)
    t = loaded.thresholds
    assert t.block_new_severities == frozenset({SEVERITY_CRITICAL, SEVERITY_HIGH})
    assert t.critical_floor is False
    assert t.min_pass_rate == 0.85
    assert t.require_review_severities == frozenset({SEVERITY_MEDIUM})
    assert loaded.version == "policy:2.1"


def test_partial_policy_keeps_defaults(tmp_path):
    # only a pass-rate floor; block severities fall back to the built-in default
    p = write_policy(tmp_path, "release_policy:\n  pass_rate_floor: 0.9\n")
    t = load_policy(p).thresholds
    assert t.min_pass_rate == 0.9
    assert t.block_new_severities == GateThresholds().block_new_severities


def test_empty_policy_is_builtin_defaults(tmp_path):
    p = write_policy(tmp_path, "")
    loaded = load_policy(p)
    assert loaded.thresholds.block_new_severities == GateThresholds().block_new_severities
    # no version field -> content-hash stamp
    assert loaded.version.startswith("policy:sha256:")


def test_version_absent_uses_content_hash(tmp_path):
    p = write_policy(tmp_path, "release_policy:\n  pass_rate_floor: 0.5\n")
    assert load_policy(p).version.startswith("policy:sha256:")


def test_unknown_severity_rejected(tmp_path):
    p = write_policy(tmp_path, "release_policy:\n  block_on:\n    - severity: spicy\n")
    with pytest.raises(PolicyError):
        load_policy(p)


def test_non_mapping_policy_rejected(tmp_path):
    p = write_policy(tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(PolicyError):
        load_policy(p)


def test_bad_pass_rate_floor_rejected(tmp_path):
    p = write_policy(tmp_path, "release_policy:\n  pass_rate_floor: 1.5\n")
    with pytest.raises(PolicyError):
        load_policy(p)


def test_missing_policy_file_raises(tmp_path):
    with pytest.raises(PolicyError):
        load_policy(tmp_path / "nope.yaml")


def test_empty_block_on_disables_blocking(tmp_path):
    # an explicit empty list is meaningful: nothing blocks as "new"
    p = write_policy(tmp_path, "release_policy:\n  block_on: []\n")
    t = load_policy(p).thresholds
    assert t.block_new_severities == frozenset()


# --- discovery --------------------------------------------------------------

def test_discover_finds_policy_upward(tmp_path):
    write_policy(tmp_path, "release_policy: {}\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert discover_policy(nested) == tmp_path / "policy.yaml"


def test_discover_returns_none_when_absent(tmp_path):
    assert discover_policy(tmp_path) is None


# --- require_review verdict -------------------------------------------------

def test_require_review_forces_conditional():
    # a medium failure does not block, but require_review pushes it to CONDITIONAL
    cur = run_of([("c1", STATUS_FAILED, SEVERITY_MEDIUM)])
    diff = diff_runs(cur, cur)  # same run as baseline -> not a "new" failure
    t = GateThresholds(require_review_severities=frozenset({SEVERITY_MEDIUM}))
    d = evaluate(diff, t)
    assert d.verdict == DECISION_CONDITIONAL_GO
    assert any("require review per policy" in r for r in d.rationale)


def test_policy_version_stamped_on_decision():
    cur = run_of([("c1", STATUS_PASSED, SEVERITY_LOW)])
    d = evaluate(diff_runs(None, cur), GateThresholds(), policy_version="policy:9.9")
    assert d.policy_version == "policy:9.9"


# --- CLI --------------------------------------------------------------------

def test_cli_gate_with_policy_blocks_and_stamps(tmp_path, capsys):
    from qval.cli import main
    write_policy(tmp_path, """
version: "1.0"
release_policy:
  block_on:
    - severity: high
""", name="pol.yaml")
    cur = tmp_path / "c.json"
    save_canonical(run_of([("c1", STATUS_FAILED, SEVERITY_HIGH)]), cur)
    out = tmp_path / "gated.json"
    rc = main(["gate", "--current", str(cur), "--policy", str(tmp_path / "pol.yaml"),
               "--out", str(out)])
    assert rc == 1
    assert "NO-GO" in capsys.readouterr().out
    assert load_canonical(out).decision.policy_version == "policy:1.0"


def test_cli_flag_overrides_policy(tmp_path, capsys):
    from qval.cli import main
    # policy blocks high; CLI narrows blocking to critical only -> high becomes conditional
    write_policy(tmp_path, "release_policy:\n  block_on:\n    - severity: high\n",
                 name="pol.yaml")
    cur = tmp_path / "c.json"
    save_canonical(run_of([("c1", STATUS_FAILED, SEVERITY_HIGH)]), cur)
    rc = main(["gate", "--current", str(cur),
               "--policy", str(tmp_path / "pol.yaml"),
               "--block-severity", "critical"])
    assert rc == 0
    assert "CONDITIONAL-GO" in capsys.readouterr().out


def test_cli_no_policy_uses_builtin(tmp_path, capsys):
    from qval.cli import main
    write_policy(tmp_path, "release_policy:\n  block_on: []\n", name="policy.yaml")
    cur = tmp_path / "c.json"
    save_canonical(run_of([("c1", STATUS_FAILED, SEVERITY_HIGH)]), cur)
    # --no-policy ignores the empty-block policy; built-in blocks new high
    rc = main(["gate", "--current", str(cur), "--no-policy",
               "--policy", str(tmp_path / "policy.yaml")])
    assert rc == 1


def test_cli_bad_policy_exit_2(tmp_path, capsys):
    from qval.cli import main
    write_policy(tmp_path, "release_policy:\n  block_on:\n    - severity: nope\n",
                 name="pol.yaml")
    cur = tmp_path / "c.json"
    save_canonical(run_of([("c1", STATUS_PASSED, SEVERITY_LOW)]), cur)
    rc = main(["gate", "--current", str(cur), "--policy", str(tmp_path / "pol.yaml")])
    assert rc == 2
