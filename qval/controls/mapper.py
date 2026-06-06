"""Map findings to governance controls and compute coverage (F-07).

``map_controls`` enriches a ``CanonicalRun`` in place: each finding gains the
``control_ids`` for its case category, and the run's ``controls`` list is
populated with exactly the ``Control`` objects referenced (deduped, stable
order). ``coverage`` then rolls findings up per control into a pass/fail matrix
— the "which OWASP-LLM / NIST risks did we exercise, and did they pass?" view a
compliance reviewer reads.
"""
from __future__ import annotations

from dataclasses import dataclass

from qval.canonical import (
    CanonicalRun,
    STATUS_PASSED, STATUS_FAILED, STATUS_NEEDS_REVIEW,
)
from .catalog import Catalog

# Coverage status for a single control, derived from its findings.
COVERAGE_PASSED = "passed"
COVERAGE_FAILED = "failed"
COVERAGE_NEEDS_REVIEW = "needs_review"
COVERAGE_NOT_EXERCISED = "not_exercised"


@dataclass
class ControlCoverage:
    """Per-control rollup: how many findings touched it and how they fared."""

    control_id: str
    framework: str
    title: str
    total: int
    passed: int
    failed: int
    needs_review: int
    status: str


def map_controls(run: CanonicalRun, catalog: Catalog) -> CanonicalRun:
    """Stamp ``control_ids`` on findings and populate ``run.controls``.

    Findings whose case category is not in the catalog get no control ids (and
    surface as an explicit gap in coverage, not a silent pass). Returns the same
    run for chaining.
    """
    cat_by_case = {c.case_id: c.category for c in run.cases}

    referenced: list[str] = []
    seen: set[str] = set()
    for f in run.findings:
        category = cat_by_case.get(f.case_id, "")
        ids = catalog.control_ids_for(category)
        f.control_ids = list(ids)
        for cid in ids:
            if cid not in seen:
                seen.add(cid)
                referenced.append(cid)

    run.controls = [catalog.control(cid) for cid in referenced]
    return run


def coverage(run: CanonicalRun) -> list[ControlCoverage]:
    """Roll findings up per control into a coverage matrix.

    Reads ``Finding.control_ids`` (set by :func:`map_controls`) and the run's
    ``controls`` for framework/title. A control with a failing finding is
    ``failed``; else with a needs-review finding ``needs_review``; else if
    exercised ``passed``; else ``not_exercised``.
    """
    meta = {c.control_id: c for c in run.controls}
    # Preserve run.controls order; include any stray ids on findings too.
    order: list[str] = [c.control_id for c in run.controls]
    seen = set(order)
    for f in run.findings:
        for cid in f.control_ids:
            if cid not in seen:
                seen.add(cid)
                order.append(cid)

    out: list[ControlCoverage] = []
    for cid in order:
        hits = [f for f in run.findings if cid in f.control_ids]
        passed = sum(1 for f in hits if f.status == STATUS_PASSED)
        failed = sum(1 for f in hits if f.status == STATUS_FAILED)
        review = sum(1 for f in hits if f.status == STATUS_NEEDS_REVIEW)
        if failed:
            status = COVERAGE_FAILED
        elif review:
            status = COVERAGE_NEEDS_REVIEW
        elif hits:
            status = COVERAGE_PASSED
        else:
            status = COVERAGE_NOT_EXERCISED
        ctrl = meta.get(cid)
        out.append(ControlCoverage(
            control_id=cid,
            framework=ctrl.framework if ctrl else "",
            title=ctrl.title if ctrl else "",
            total=len(hits), passed=passed, failed=failed,
            needs_review=review, status=status,
        ))
    return out
