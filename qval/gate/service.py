"""Shared gate evaluation helpers for CLI and local UI."""

from __future__ import annotations

import dataclasses
from dataclasses import asdict
from pathlib import Path
from typing import Any

from qval.canonical import ALL_SEVERITIES, STATUS_NEEDS_REVIEW
from qval.engine.run_service import list_run_history, load_run
from qval.gate.decision import GateThresholds, POLICY_VERSION, evaluate
from qval.gate.diff import diff_runs
from qval.gate.policy import PolicyError, discover_policy, load_policy


def resolve_policy(*, policy: str | None = None, no_policy: bool = False,
                   min_pass_rate: float | None = None,
                   block_severity: str | None = None) -> tuple[GateThresholds, str, Path | None]:
    """Build thresholds + provenance using the same precedence as `qval gate`."""

    thresholds = GateThresholds()
    policy_version = POLICY_VERSION
    policy_path = None

    if not no_policy:
        policy_path = Path(policy) if policy else discover_policy()
        if policy_path is not None:
            loaded = load_policy(policy_path)
            thresholds, policy_version = loaded.thresholds, loaded.version

    overrides: dict[str, Any] = {}
    if block_severity is not None:
        sevs = frozenset(s.strip() for s in block_severity.split(",") if s.strip())
        bad = sevs - set(ALL_SEVERITIES)
        if bad:
            raise ValueError(f"invalid --block-severity {sorted(bad)}; "
                             f"choose from {ALL_SEVERITIES}")
        overrides["block_new_severities"] = sevs
    if min_pass_rate is not None:
        overrides["min_pass_rate"] = min_pass_rate

    if overrides:
        thresholds = dataclasses.replace(thresholds, **overrides)
    return thresholds, policy_version, policy_path


def gate_payload(run_id: str, baseline_id: str | None = None) -> dict[str, Any]:
    current = load_run(run_id)
    actual_baseline_id = baseline_id or default_baseline_for(current)
    baseline = load_run(actual_baseline_id) if actual_baseline_id else None
    thresholds, policy_version, policy_path = resolve_policy()
    diff = diff_runs(baseline, current)
    decision = evaluate(diff, thresholds, policy_version=policy_version)
    unresolved = sum(1 for finding in current.findings
                     if finding.status == STATUS_NEEDS_REVIEW)

    return {
        "run_id": run_id,
        "baseline_run_id": actual_baseline_id,
        "decision": asdict(decision),
        "triggering_policy_rules": list(decision.rationale),
        "policy_rules": _policy_rule_lines(policy_path),
        "policy_version": policy_version,
        "regressions": _regressions(diff, current),
        "category_regressions": [asdict(item) for item in diff.category_regressions],
        "unresolved_review_count": unresolved,
        "blocked_by_reviews": unresolved > 0,
        "pass_rate": {
            "baseline": diff.pass_rate_baseline,
            "current": diff.pass_rate_current,
            "delta": diff.pass_rate_delta,
        },
    }


def default_baseline_for(current) -> str | None:
    """Pick the previous run with the same suite from run history."""

    history = list_run_history()
    current_seen = False
    for item in history:
        if item["run_id"] == current.run_id:
            current_seen = True
            continue
        if item.get("suite") != current.suite:
            continue
        if current_seen:
            return item["run_id"]
    for item in history:
        if item["run_id"] != current.run_id and item.get("suite") == current.suite:
            return item["run_id"]
    return None


def _regressions(diff, current) -> list[dict[str, Any]]:
    names = {case.case_id: case.name for case in current.cases}
    rows = []
    for finding in diff.new_failures:
        rows.append({
            "type": "new_failure",
            "case_id": finding.case_id,
            "name": names.get(finding.case_id, finding.case_id),
            "status": finding.status,
            "severity": finding.severity,
            "reason": finding.reason,
        })
    for regression in diff.severity_regressions:
        row = asdict(regression)
        row["type"] = "severity_regression"
        rows.append(row)
    return rows


def _policy_rule_lines(policy_path: Path | None) -> list[str]:
    if policy_path is None:
        return ["builtin-v1"]
    try:
        lines = policy_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    in_release_policy = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "release_policy:":
            in_release_policy = True
            out.append(stripped)
            continue
        if in_release_policy:
            if line and not line.startswith((" ", "\t", "-")):
                break
            out.append(line.rstrip())
    return out
