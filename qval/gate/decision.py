"""Release decision engine (F-04).

Turns a ``RunDiff`` into a ``Decision`` (GO / CONDITIONAL-GO / NO-GO) using a
``GateThresholds`` ruleset. Today ``GateThresholds`` holds built-in defaults;
**F-06 policy-as-code** will construct it from ``policy.yaml`` — this engine is
the stable seam, so F-06 swaps the input, not the logic. The verdict is stamped
``policy_version="builtin-v1"`` to mark it as built-in-rule-derived.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from qval.canonical import (
    Decision,
    SEVERITY_CRITICAL, SEVERITY_HIGH,
    DECISION_GO, DECISION_CONDITIONAL_GO, DECISION_NO_GO,
)
from qval.utils.time_utils import now_utc_iso
from .diff import RunDiff

POLICY_VERSION = "builtin-v1"


@dataclass
class GateThresholds:
    """Gate rules. Built-in defaults today; F-06 constructs these from a
    ``policy.yaml`` (see ``qval/gate/policy.py``) without changing the engine."""

    block_new_severities: frozenset[str] = field(
        default_factory=lambda: frozenset({SEVERITY_CRITICAL, SEVERITY_HIGH})
    )
    critical_floor: bool = True          # block on any current critical failure
    min_pass_rate: float | None = None   # opt-in pass-rate floor
    # Failures at these severities never block, but force CONDITIONAL-GO so a
    # human signs off (policy `require_review`). Empty = no review gate.
    require_review_severities: frozenset[str] = field(default_factory=frozenset)


def evaluate(diff: RunDiff, thresholds: GateThresholds | None = None,
             policy_version: str = POLICY_VERSION) -> Decision:
    """Apply the ruleset to a diff and return a release Decision.

    ``policy_version`` stamps the verdict's provenance: ``"builtin-v1"`` for the
    default rules, or a policy-file identifier when F-06 supplies one.
    """
    t = thresholds or GateThresholds()
    block: list[str] = []

    # New failures at a blocking severity (regression vs baseline).
    new_blocking = _by_severity(diff.new_failures, t.block_new_severities)
    for sev, n in new_blocking.items():
        block.append(f"{n} new {sev} finding(s) vs baseline")

    # Severity regressions that worsened *into* a blocking severity.
    worse = [r for r in diff.severity_regressions
             if r.to_severity in t.block_new_severities]
    if worse:
        block.append(f"{len(worse)} finding(s) regressed to "
                     f"{', '.join(sorted({r.to_severity for r in worse}))}")

    # Critical floor: any critical failure in the current run, new or not.
    if t.critical_floor:
        crit = [f for f in diff.current_failures if f.severity == SEVERITY_CRITICAL]
        # avoid double-counting ones already named as new critical
        new_crit = {f.case_id for f in diff.new_failures
                    if f.severity == SEVERITY_CRITICAL}
        preexisting = [f for f in crit if f.case_id not in new_crit]
        if preexisting:
            block.append(f"{len(preexisting)} unresolved critical failure(s)")

    # Pass-rate floor (opt-in).
    if t.min_pass_rate is not None and diff.pass_rate_current < t.min_pass_rate:
        block.append(f"pass-rate {diff.pass_rate_current:.0%} below floor "
                     f"{t.min_pass_rate:.0%}")

    if block:
        return _decision(DECISION_NO_GO, block, policy_version)

    # Not blocked — anything that warrants caution?
    conditional: list[str] = []
    minor = _by_severity(
        [f for f in diff.new_failures if f.severity not in t.block_new_severities],
        None,
    )
    for sev, n in minor.items():
        conditional.append(f"{n} new {sev} finding(s) vs baseline")

    # Policy require_review: current failures at a review severity that are not
    # already named above (new failures get named there) push to CONDITIONAL.
    if t.require_review_severities:
        named = {f.case_id for f in diff.new_failures}
        review = _by_severity(
            [f for f in diff.current_failures
             if f.severity in t.require_review_severities and f.case_id not in named],
            t.require_review_severities,
        )
        for sev, n in review.items():
            conditional.append(f"{n} {sev} finding(s) require review per policy")

    if diff.needs_review:
        conditional.append(f"{len(diff.needs_review)} finding(s) require human review")

    if conditional:
        return _decision(DECISION_CONDITIONAL_GO, conditional, policy_version)

    return _decision(DECISION_GO, ["no new failures or regressions vs baseline"],
                     policy_version)


def _by_severity(findings, allowed) -> dict[str, int]:
    """Count findings per severity, optionally filtered to an allowed set,
    returned worst-first for stable rationale ordering."""
    from qval.canonical.schema import SEVERITY_RANK
    counts: dict[str, int] = {}
    for f in findings:
        if allowed is not None and f.severity not in allowed:
            continue
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -SEVERITY_RANK[kv[0]]))


def _decision(verdict: str, rationale: list[str],
              policy_version: str = POLICY_VERSION) -> Decision:
    return Decision(verdict=verdict, rationale=rationale,
                    decided_at=now_utc_iso(), policy_version=policy_version)
