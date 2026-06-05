"""Native -> canonical adapter (F-01).

Converts the existing native run schema (``src/engine/schemas.py``:
``RunSummary`` + ``TestResult``) into a ``CanonicalRun``. This keeps the
working native pipeline untouched: the runner still produces TestResults, and
this adapter translates them into the governance-layer shape that the gate,
reports, and evidence packs consume.

Importers (Promptfoo F-03, DeepEval F-09) construct ``CanonicalRun`` directly
rather than going through this adapter, since they never produce TestResults.
"""

from __future__ import annotations

from qval.engine.schemas import RunSummary, TestResult
from .schema import (
    CanonicalRun, Case, Finding,
    map_native_status, map_native_severity,
)


def test_result_to_case(tr: TestResult) -> Case:
    """Extract the input side of a native TestResult into a canonical Case."""
    return Case(
        case_id=tr.test_id,
        name=tr.test_name,
        category=tr.category,
        prompt=tr.prompt,
        expected_behavior=tr.expected_behavior,
        source_tool="qval",
        tags=[],
        extra=_case_extra(tr),
    )


def test_result_to_finding(tr: TestResult) -> Finding:
    """Extract the result side of a native TestResult into a canonical Finding."""
    return Finding(
        finding_id=f"{tr.test_id}",
        case_id=tr.test_id,
        status=map_native_status(tr.status),
        severity=map_native_severity(tr.risk_level),
        score=float(tr.score) if tr.score is not None else None,
        reason=tr.scoring_reason,
        response=tr.response,
        control_ids=[],          # filled by F-07 control mapping
        manual_review_required=tr.manual_review_required,
        reviewers=[],
        waiver=None,
        extra=_finding_extra(tr),
    )


def run_summary_to_canonical(
    summary: RunSummary,
    results: list[TestResult],
) -> CanonicalRun:
    """Build a CanonicalRun from a native RunSummary plus its TestResults.

    Args:
        summary: native aggregate metrics for the run.
        results: the per-test results produced by the runner.

    Returns:
        A CanonicalRun with cases + findings populated. Decision, controls, and
        evidence_pack are left empty for later features to fill.
    """
    cases = [test_result_to_case(tr) for tr in results]
    findings = [test_result_to_finding(tr) for tr in results]

    return CanonicalRun(
        run_id=summary.run_id,
        source_tool="qval",
        model=summary.model,
        provider=summary.provider,
        started_at=summary.started_at,
        completed_at=summary.completed_at,
        suite=summary.suite,
        environment="",
        prompt_version="",
        cases=cases,
        findings=findings,
        controls=[],
        decision=None,
        evidence_pack=None,
        metadata=_run_metadata(summary),
    )


# --- internal helpers -------------------------------------------------------


def _case_extra(tr: TestResult) -> dict:
    extra = {}
    if tr.paired_prompt is not None:
        extra["paired_prompt"] = tr.paired_prompt
    return extra


def _finding_extra(tr: TestResult) -> dict:
    extra = {
        "latency_ms": tr.latency_ms,
        "temperature": tr.temperature,
        "timestamp": tr.timestamp,
    }
    if tr.paired_response is not None:
        extra["paired_response"] = tr.paired_response
    if tr.error is not None:
        extra["error"] = tr.error
    if tr.detector_results:
        extra["detectors"] = [
            {"name": d.name, "triggered": d.triggered,
             "matches": d.matches, "notes": d.notes}
            for d in tr.detector_results
        ]
    # token / cost telemetry when present
    for fld in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_usd"):
        val = getattr(tr, fld, None)
        if val is not None:
            extra[fld] = val
    return extra


def _run_metadata(summary: RunSummary) -> dict:
    """Carry native aggregate metrics that have no canonical home (yet) into
    metadata, so nothing is lost in translation."""
    return {
        "temperature": summary.temperature,
        "total_tests": summary.total_tests,
        "pass_count": summary.pass_count,
        "fail_count": summary.fail_count,
        "needs_review_count": summary.needs_review_count,
        "error_count": summary.error_count,
        "pass_rate": summary.pass_rate,
        "weighted_pass_rate": summary.weighted_pass_rate,
        "average_score": summary.average_score,
        "by_category": summary.by_category,
        "total_cost_usd": summary.total_cost_usd,
        "p50_latency_ms": summary.p50_latency_ms,
        "p95_latency_ms": summary.p95_latency_ms,
        "p99_latency_ms": summary.p99_latency_ms,
    }
