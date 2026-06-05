"""Orchestrates a single evaluation run.

The runner's job is small and explicit:
  1. Take a list of TestCase objects and a ModelClient.
  2. For each test, call the model (twice if `paired_prompt` is set).
  3. Hand the prompt(s) and response(s) to the right scorer.
  4. Return a list of TestResult objects plus a RunSummary.

The runner does not know how scoring works, and the scorers do not know
how the model is called — keeping that separation makes the system easy to
test and easy to extend.
"""

from __future__ import annotations

import statistics
from typing import Callable, Optional

from src.engine.model_client import ModelClient
from src.engine.schemas import (
    TestCase, TestResult, RunSummary,
    STATUS_PASS, STATUS_FAIL, STATUS_NEEDS_REVIEW,
)
from src.utils.time_utils import now_utc_iso


# A scorer is a callable: (test_case, response_text, paired_response_text|None) -> dict
ScorerFn = Callable[[TestCase, str, Optional[str]], dict]


class TestRunner:
    def __init__(self, run_id: str, client: ModelClient,
                 scorer_for: Callable[[str], ScorerFn],
                 risk_matrix: dict, log_fn: Callable[[str], None] | None = None):
        self.run_id = run_id
        self.client = client
        self.scorer_for = scorer_for
        self.risk_matrix = risk_matrix
        self.log = log_fn or (lambda _msg: None)

    def run(self, cases: list[TestCase], suite_label: str) -> tuple[list[TestResult], RunSummary]:
        started_at = now_utc_iso()
        results: list[TestResult] = []

        for case in cases:
            self.log(f"[{case.id}] {case.name} ({case.risk_level})")
            result = self._run_one(case)
            results.append(result)
            self.log(f"    -> {result.status} (score={result.score})")

        completed_at = now_utc_iso()
        summary = self._summarize(results, suite_label, started_at, completed_at)
        return results, summary

    # ---- per-test execution ------------------------------------------------

    def _run_one(self, case: TestCase) -> TestResult:
        primary = self.client.complete(case.prompt)
        paired = None
        if case.paired_prompt:
            paired = self.client.complete(case.paired_prompt)

        scorer = self.scorer_for(case.category)
        scoring = scorer(
            case,
            primary.text,
            paired.text if paired else None,
        )

        # If the model call itself failed, force NEEDS_REVIEW for human triage.
        error_msg = primary.error or (paired.error if paired else None)
        if error_msg:
            scoring = {
                **scoring,
                "status": STATUS_NEEDS_REVIEW,
                "score": 1,
                "scoring_reason": f"Model call error: {error_msg}",
            }

        # Sum token counts and cost across primary + paired calls. None on
        # either side propagates as "unknown" rather than silently zeroing.
        def _sum_opt(a: int | None, b: int | None) -> int | None:
            if a is None and b is None:
                return None
            return (a or 0) + (b or 0)

        prompt_tokens = _sum_opt(
            primary.prompt_tokens, paired.prompt_tokens if paired else None,
        )
        completion_tokens = _sum_opt(
            primary.completion_tokens, paired.completion_tokens if paired else None,
        )
        total_tokens = _sum_opt(
            primary.total_tokens, paired.total_tokens if paired else None,
        )
        cost_usd: float | None
        if primary.cost_usd is None and (paired is None or paired.cost_usd is None):
            cost_usd = None
        else:
            cost_usd = (primary.cost_usd or 0.0) \
                + ((paired.cost_usd or 0.0) if paired else 0.0)

        return TestResult(
            run_id=self.run_id,
            test_id=case.id,
            category=case.category,
            test_name=case.name,
            description=case.description,
            expected_behavior=case.expected_behavior,
            risk_level=case.risk_level,
            prompt=case.prompt,
            response=primary.text,
            paired_prompt=case.paired_prompt,
            paired_response=paired.text if paired else None,
            model=self.client.model,
            provider=self.client.provider,
            temperature=getattr(self.client, "temperature", 0.0),
            timestamp=now_utc_iso(),
            latency_ms=primary.latency_ms + (paired.latency_ms if paired else 0),
            status=scoring["status"],
            score=scoring["score"],
            scoring_reason=scoring["scoring_reason"],
            manual_review_required=case.manual_review_required or scoring["status"] == STATUS_NEEDS_REVIEW,
            detector_results=scoring.get("detector_results", []),
            error=error_msg,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
        )

    # ---- aggregate ---------------------------------------------------------

    def _summarize(self, results: list[TestResult], suite_label: str,
                   started_at: str, completed_at: str) -> RunSummary:
        total = len(results)
        pass_count = sum(1 for r in results if r.status == STATUS_PASS)
        fail_count = sum(1 for r in results if r.status == STATUS_FAIL)
        review_count = sum(1 for r in results if r.status == STATUS_NEEDS_REVIEW)
        error_count = sum(1 for r in results if r.error)

        pass_rate = (pass_count / total) if total else 0.0
        weighted_pass_rate = self._weighted_pass_rate(results)
        avg_score = (sum(r.score for r in results) / total) if total else 0.0

        by_category: dict[str, dict] = {}
        for r in results:
            cat = by_category.setdefault(r.category, {
                "total": 0, "pass": 0, "fail": 0, "needs_review": 0,
                "total_tokens": 0, "total_cost_usd": 0.0,
            })
            cat["total"] += 1
            if r.status == STATUS_PASS:
                cat["pass"] += 1
            elif r.status == STATUS_FAIL:
                cat["fail"] += 1
            else:
                cat["needs_review"] += 1
            cat["total_tokens"] += r.total_tokens or 0
            cat["total_cost_usd"] += r.cost_usd or 0.0
        for cat in by_category.values():
            cat["pass_rate"] = (cat["pass"] / cat["total"]) if cat["total"] else 0.0

        critical_failures = [r.test_id for r in results
                             if r.status == STATUS_FAIL and r.risk_level == "critical"]
        high_risk_failures = [r.test_id for r in results
                              if r.status == STATUS_FAIL and r.risk_level == "high"]

        total_prompt_tokens = sum(r.prompt_tokens or 0 for r in results)
        total_completion_tokens = sum(r.completion_tokens or 0 for r in results)
        total_tokens = sum(r.total_tokens or 0 for r in results)
        total_cost_usd = sum(r.cost_usd for r in results if r.cost_usd is not None)
        # An errored call having no cost is expected, not "incomplete". Only
        # non-errored calls without cost flag the run as partial.
        cost_complete = all((r.cost_usd is not None) or bool(r.error) for r in results)

        p50, p95, p99 = _latency_percentiles(
            [r.latency_ms for r in results if not r.error]
        )

        return RunSummary(
            run_id=self.run_id,
            started_at=started_at,
            completed_at=completed_at,
            suite=suite_label,
            model=self.client.model,
            provider=self.client.provider,
            temperature=getattr(self.client, "temperature", 0.0),
            total_tests=total,
            pass_count=pass_count,
            fail_count=fail_count,
            needs_review_count=review_count,
            error_count=error_count,
            pass_rate=pass_rate,
            weighted_pass_rate=weighted_pass_rate,
            average_score=avg_score,
            by_category=by_category,
            critical_failures=critical_failures,
            high_risk_failures=high_risk_failures,
            report_path="",     # filled in by caller after report write
            evidence_dir="",    # filled in by caller after evidence write
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            total_tokens=total_tokens,
            total_cost_usd=total_cost_usd,
            cost_complete=cost_complete,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
        )

    def _weighted_pass_rate(self, results: list[TestResult]) -> float:
        if not results:
            return 0.0
        total_weight = 0
        passing_weight = 0
        for r in results:
            w = int(self.risk_matrix["levels"].get(r.risk_level, {}).get("weight", 1))
            total_weight += w
            if r.status == STATUS_PASS:
                passing_weight += w
        return (passing_weight / total_weight) if total_weight else 0.0


def _latency_percentiles(latencies: list[int]) -> tuple[int, int, int]:
    """Return (p50, p95, p99) integer latencies.

    For N < 5 we refuse to fabricate quantiles from too few samples and
    return max() across the board instead — an honest signal that still
    shows non-zero. Empty list returns zeros.
    """
    if not latencies:
        return 0, 0, 0
    if len(latencies) < 5:
        m = max(latencies)
        return m, m, m
    qs = statistics.quantiles(latencies, n=100, method="inclusive")
    # `quantiles(n=100)` returns 99 cut points: indexes 0..98 = P1..P99.
    return int(qs[49]), int(qs[94]), int(qs[98])
