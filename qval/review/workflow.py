"""Manual review workflow (F-10).

Some findings — safety violations, fairness edge cases, sensitive outputs —
cannot be auto-decided by pass/fail scoring. They need human judgment. Without a
structured workflow that judgment happens in spreadsheets and Slack threads: no
audit trail, no consistency, no accountability. This module turns it into
first-class canonical data.

A reviewer **approves** (resolved-acceptable), **rejects** (blocked — do not
ship), or **waives** (a known failure shipped with documented acceptance). Each
decision appends a ``Reviewer`` to the finding (the audit trail: who, what,
when) and moves the finding's status into the F-01 governance vocabulary
(``approved`` / ``blocked`` / ``waived``). The gate already understands those:
approved/waived clear a failure, blocked keeps blocking.
"""
from __future__ import annotations

from dataclasses import dataclass

from qval.canonical import (
    CanonicalRun, Finding, Reviewer, Waiver,
    STATUS_FAILED, STATUS_NEEDS_REVIEW, STATUS_BLOCKED,
    STATUS_WAIVED, STATUS_APPROVED,
)
from qval.canonical.schema import SEVERITY_RANK
from qval.utils.time_utils import now_utc_iso

# Reviewer decisions and the finding status each produces.
DECISION_APPROVE = "approve"
DECISION_REJECT = "reject"
DECISION_WAIVE = "waive"
ALL_DECISIONS = (DECISION_APPROVE, DECISION_REJECT, DECISION_WAIVE)

_DECISION_STATUS = {
    DECISION_APPROVE: STATUS_APPROVED,
    DECISION_REJECT: STATUS_BLOCKED,
    DECISION_WAIVE: STATUS_WAIVED,
}

# Findings that still need a human look (the review queue).
OPEN_STATUSES = frozenset({STATUS_FAILED, STATUS_NEEDS_REVIEW, STATUS_BLOCKED})
# Queue ordering within a severity: most urgent posture first.
_STATUS_PRIORITY = {STATUS_FAILED: 0, STATUS_NEEDS_REVIEW: 1, STATUS_BLOCKED: 2}


class ReviewError(Exception):
    """Raised on an invalid review action (unknown finding/decision, etc.)."""


@dataclass
class QueueItem:
    """One finding awaiting (or carrying) a human decision."""

    finding_id: str
    case_id: str
    name: str
    category: str
    severity: str
    status: str
    owner: str
    current_response: str
    baseline_status: str = ""
    baseline_response: str = ""
    last_decision: str = ""


def get_finding(run: CanonicalRun, finding_id: str) -> Finding:
    for f in run.findings:
        if f.finding_id == finding_id:
            return f
    raise ReviewError(f"no finding with id {finding_id!r} in run {run.run_id!r}")


def owner_of(finding: Finding) -> str:
    return str(finding.extra.get("owner", ""))


def assign_owner(run: CanonicalRun, finding_id: str, owner: str) -> Finding:
    """Assign a review owner to a finding (stored on the finding)."""
    finding = get_finding(run, finding_id)
    finding.extra["owner"] = owner
    return finding


def apply_decision(run: CanonicalRun, finding_id: str, *, reviewer_id: str,
                   decision: str, notes: str = "", reason: str = "",
                   expires_at: str = "") -> Finding:
    """Record a reviewer decision: append the audit entry and move the status.

    ``waive`` requires a ``reason`` (the documented acceptance). Returns the
    updated finding.
    """
    if decision not in ALL_DECISIONS:
        raise ReviewError(
            f"unknown decision {decision!r}; choose from {ALL_DECISIONS}")
    if not reviewer_id:
        raise ReviewError("a reviewer id is required")
    if decision == DECISION_WAIVE and not reason:
        raise ReviewError("a waiver requires a reason (documented acceptance)")

    finding = get_finding(run, finding_id)
    decided_at = now_utc_iso()
    finding.reviewers.append(Reviewer(
        reviewer_id=reviewer_id, decision=decision, notes=notes,
        decided_at=decided_at))
    finding.status = _DECISION_STATUS[decision]

    if decision == DECISION_WAIVE:
        finding.waiver = Waiver(
            waiver_id=f"wv-{finding_id}", reason=reason, approver=reviewer_id,
            approved_at=decided_at, expires_at=expires_at)
    return finding


def review_queue(run: CanonicalRun, baseline: CanonicalRun | None = None, *,
                 include_resolved: bool = False) -> list[QueueItem]:
    """Build the review queue, sorted worst-severity-first.

    Open items (failed / needs_review / blocked) by default; pass
    ``include_resolved`` to also list approved/waived findings (for audit). When
    a baseline is given, each item carries the baseline status/response for a
    side-by-side comparison.
    """
    base_by_case = {f.case_id: f for f in baseline.findings} if baseline else {}
    name_by_case = {c.case_id: c.name for c in run.cases}
    cat_by_case = {c.case_id: c.category for c in run.cases}

    items: list[QueueItem] = []
    for f in run.findings:
        if not include_resolved and f.status not in OPEN_STATUSES:
            continue
        prior = base_by_case.get(f.case_id)
        items.append(QueueItem(
            finding_id=f.finding_id,
            case_id=f.case_id,
            name=name_by_case.get(f.case_id, f.case_id),
            category=cat_by_case.get(f.case_id, ""),
            severity=f.severity,
            status=f.status,
            owner=owner_of(f),
            current_response=f.response,
            baseline_status=prior.status if prior else "",
            baseline_response=prior.response if prior else "",
            last_decision=f.reviewers[-1].decision if f.reviewers else "",
        ))

    items.sort(key=lambda it: (
        -SEVERITY_RANK.get(it.severity, 0),
        _STATUS_PRIORITY.get(it.status, 9),
        it.finding_id,
    ))
    return items
