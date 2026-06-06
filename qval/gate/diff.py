"""Baseline diff engine (F-04).

Pure functions that compare a *current* canonical run against a *baseline* and
produce a ``RunDiff`` — the structured "what changed" that the decision engine
turns into a verdict and the F-05 report renders. Findings are paired by
``case_id``. With no baseline, every current failure is treated as new.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from qval.canonical import (
    CanonicalRun, Finding,
    STATUS_PASSED, STATUS_FAILED, STATUS_NEEDS_REVIEW,
    STATUS_WAIVED, STATUS_APPROVED, STATUS_BLOCKED,
)
from qval.canonical.schema import SEVERITY_RANK

# A finding blocks the gate if it failed or a reviewer explicitly blocked it
# (F-10 reject). A reviewer can resolve a failure by approving or waiving it —
# those count as cleared, not failing.
FAILING_STATUSES = frozenset({STATUS_FAILED, STATUS_BLOCKED})
RESOLVED_STATUSES = frozenset({STATUS_PASSED, STATUS_APPROVED, STATUS_WAIVED})


def is_failing(status: str) -> bool:
    return status in FAILING_STATUSES


@dataclass
class Regression:
    """A case that was already failing and got worse (status or severity)."""

    case_id: str
    name: str
    from_status: str
    to_status: str
    from_severity: str
    to_severity: str


@dataclass
class CategoryDelta:
    """A category whose pass rate dropped between baseline and current."""

    category: str
    baseline_pass_rate: float
    current_pass_rate: float
    delta: float                 # current - baseline (negative = worse)


@dataclass
class RunDiff:
    """Structured comparison of a current run against a baseline."""

    new_failures: list[Finding] = field(default_factory=list)
    current_failures: list[Finding] = field(default_factory=list)
    improvements: list[Finding] = field(default_factory=list)
    severity_regressions: list[Regression] = field(default_factory=list)
    category_regressions: list[CategoryDelta] = field(default_factory=list)
    needs_review: list[Finding] = field(default_factory=list)
    pass_rate_baseline: float = 1.0
    pass_rate_current: float = 1.0
    pass_rate_delta: float = 0.0


def diff_runs(baseline: CanonicalRun | None, current: CanonicalRun) -> RunDiff:
    """Compare ``current`` against ``baseline`` (or nothing) into a RunDiff."""
    base_by_case = (
        {f.case_id: f for f in baseline.findings} if baseline else {}
    )

    diff = RunDiff()

    for f in current.findings:
        prior = base_by_case.get(f.case_id)

        if is_failing(f.status):
            diff.current_failures.append(f)
            if prior is None or not is_failing(prior.status):
                # newly failing (absent before, or was passing / needs_review)
                diff.new_failures.append(f)
            elif SEVERITY_RANK[f.severity] > SEVERITY_RANK[prior.severity]:
                # already failing, but worse severity now
                diff.severity_regressions.append(
                    Regression(f.case_id, _name(current, f.case_id),
                               prior.status, f.status,
                               prior.severity, f.severity)
                )

        if f.status == STATUS_NEEDS_REVIEW:
            diff.needs_review.append(f)

        if (f.status == STATUS_PASSED and prior is not None
                and is_failing(prior.status)):
            diff.improvements.append(f)

    diff.pass_rate_current = _pass_rate(current)
    diff.pass_rate_baseline = _pass_rate(baseline) if baseline else diff.pass_rate_current
    diff.pass_rate_delta = diff.pass_rate_current - diff.pass_rate_baseline

    if baseline is not None:
        diff.category_regressions = _category_regressions(baseline, current)

    return diff


# --- internals --------------------------------------------------------------

def _name(run: CanonicalRun, case_id: str) -> str:
    for c in run.cases:
        if c.case_id == case_id:
            return c.name
    return case_id


def _pass_rate(run: CanonicalRun) -> float:
    total = len(run.findings)
    if total == 0:
        return 1.0                      # vacuously: nothing failing
    # Approved/waived findings are resolved-acceptable: they count toward the
    # rate, not against it (a reviewer signed off).
    passed = sum(1 for f in run.findings if f.status in RESOLVED_STATUSES)
    return passed / total


def _category_rates(run: CanonicalRun) -> dict[str, float]:
    cat_by_case = {c.case_id: c.category for c in run.cases}
    totals: dict[str, int] = {}
    passes: dict[str, int] = {}
    for f in run.findings:
        cat = cat_by_case.get(f.case_id, "")
        totals[cat] = totals.get(cat, 0) + 1
        if f.status in RESOLVED_STATUSES:
            passes[cat] = passes.get(cat, 0) + 1
    return {cat: passes.get(cat, 0) / n for cat, n in totals.items() if n}


def _category_regressions(baseline: CanonicalRun,
                          current: CanonicalRun) -> list[CategoryDelta]:
    base_rates = _category_rates(baseline)
    cur_rates = _category_rates(current)
    out: list[CategoryDelta] = []
    for cat, cur_rate in cur_rates.items():
        base_rate = base_rates.get(cat)
        if base_rate is not None and cur_rate < base_rate:
            out.append(CategoryDelta(cat, base_rate, cur_rate, cur_rate - base_rate))
    return out
