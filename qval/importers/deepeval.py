"""DeepEval importer (F-09).

Maps a DeepEval results JSON into a ``CanonicalRun`` via the F-03 importer seam
— same canonical target as the Promptfoo importer, a different source tool, so
the gate / report / controls / pack all consume DeepEval runs unchanged.

DeepEval grades each test case with one or more *metrics* (Hallucination, Bias,
Faithfulness …), each carrying a 0–1 score, a threshold, a pass/fail, and a
judge ``reason``. It assigns no risk severity, so findings default to ``info``
(overridable; an explicit ``severity`` in a case's metadata wins). The parser is
tolerant of DeepEval's snake_case / camelCase and layout variants — see
``_locate_test_cases`` and ``_metrics``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from qval.canonical import (
    CanonicalRun, Case, Finding,
    STATUS_PASSED, STATUS_FAILED,
)
from qval.utils.time_utils import generate_run_id, now_utc_iso
from .base import BaseImporter, resolve_severity
from .registry import register


class DeepEvalImporter(BaseImporter):
    """Importer for DeepEval evaluation output."""

    tool_name = "deepeval"

    def to_canonical(self, data: Any, *, default_severity: str,
                     source: str) -> CanonicalRun:
        records = _locate_test_cases(data)

        cases: list[Case] = []
        findings: list[Finding] = []
        for i, rec in enumerate(records):
            cid = _record_id(rec, i)
            cases.append(_to_case(rec, cid))
            findings.append(_to_finding(rec, cid, default_severity))

        return CanonicalRun(
            run_id=generate_run_id(),
            source_tool=self.tool_name,
            model=_model(data),
            provider=_provider(data),
            completed_at=now_utc_iso(),
            suite=_suite_name(data, source),
            cases=cases,
            findings=findings,
            metadata={"source_path": source},
        )


# --- locating the test cases (tolerant) -------------------------------------

def _locate_test_cases(data: Any) -> list:
    """Find the list of test-case records across DeepEval layout variants.

    Order: a top-level list -> ``testCases`` / ``test_cases`` ->
    ``testResults`` / ``test_results``. Raises ValueError if none match.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("testCases", "test_cases", "testResults", "test_results"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    raise ValueError(
        "could not locate a DeepEval test-case array; expected a top-level "
        "list, or data['testCases'] / data['test_results']"
    )


# --- per-record field extraction --------------------------------------------

def _record_id(rec: dict, i: int) -> str:
    return str(rec.get("name") or rec.get("id") or i)


def _first(rec: dict, *keys, default=""):
    """Return the first present, non-None value among snake/camel key aliases."""
    for key in keys:
        if rec.get(key) is not None:
            return rec[key]
    return default


def _metrics(rec: dict) -> list[dict]:
    raw = (rec.get("metricsData") or rec.get("metrics_data")
           or rec.get("metrics") or [])
    return [m for m in raw if isinstance(m, dict)]


def _metric_success(metric: dict) -> bool:
    return bool(_first(metric, "success", default=True))


def _to_case(rec: dict, cid: str) -> Case:
    extra: dict[str, Any] = {}
    metadata = rec.get("metadata") or rec.get("additionalMetadata")
    if isinstance(metadata, dict) and metadata:
        extra["metadata"] = metadata
    return Case(
        case_id=cid,
        name=str(rec.get("name") or f"case-{cid}"),
        category="imported",
        prompt=str(_first(rec, "input", "prompt")),
        expected_behavior=str(_first(rec, "expectedOutput", "expected_output")),
        source_tool="deepeval",
        extra=extra,
    )


def _to_finding(rec: dict, cid: str, default_severity: str) -> Finding:
    metrics = _metrics(rec)

    # Status: explicit case success wins; else all metrics must pass; an empty
    # metric set with no verdict is treated as passing (nothing failed).
    success = _first(rec, "success", default=None)
    if success is None:
        success = all(_metric_success(m) for m in metrics) if metrics else True
    status = STATUS_PASSED if success else STATUS_FAILED

    driver = _driving_metric(metrics)
    score = driver.get("score") if driver else None
    reason = _reason(metrics) if metrics else str(rec.get("reason", ""))

    extra: dict[str, Any] = {}
    if metrics:
        extra["metrics"] = metrics

    return Finding(
        finding_id=cid,
        case_id=cid,
        status=status,
        severity=resolve_severity(_record_severity(rec), default_severity),
        score=float(score) if isinstance(score, (int, float)) else None,
        reason=reason,
        response=str(_first(rec, "actualOutput", "actual_output", "response")),
        control_ids=[],
        extra=extra,
    )


def _driving_metric(metrics: list[dict]) -> dict | None:
    """The metric that best explains the verdict: first failing one, else first."""
    for m in metrics:
        if not _metric_success(m):
            return m
    return metrics[0] if metrics else None


def _reason(metrics: list[dict]) -> str:
    """Join the reasons of failing metrics; fall back to all metric reasons."""
    failing = [m for m in metrics if not _metric_success(m)]
    chosen = failing or metrics
    parts = []
    for m in chosen:
        name = m.get("name", "metric")
        why = m.get("reason")
        if why:
            parts.append(f"{name}: {why}")
    return " | ".join(parts)


def _record_severity(rec: dict):
    for container in (rec.get("metadata"), rec.get("additionalMetadata")):
        if isinstance(container, dict) and container.get("severity"):
            return container["severity"]
    return rec.get("severity")


# --- run-level metadata -----------------------------------------------------

def _model(data: Any) -> str:
    if isinstance(data, dict):
        return str(_first(data, "model", "evaluationModel", default=""))
    return ""


def _provider(data: Any) -> str:
    if isinstance(data, dict):
        return str(data.get("provider", ""))
    return ""


def _suite_name(data: Any, source: str) -> str:
    if isinstance(data, dict):
        name = _first(data, "testRunName", "name", "suite", default="")
        if name:
            return str(name)
    return Path(source).stem if source else ""


# Self-register on import so the registry / CLI discover this tool.
register(DeepEvalImporter())
