"""Shared run orchestration for CLI and local UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from qval.canonical.adapter import run_summary_to_canonical
from qval.canonical.io import load_canonical, save_canonical
from qval.canonical.schema import CanonicalRun
from qval.controls import load_catalog, map_controls
from qval.controls.catalog import ControlCatalogError
from qval.engine.model_client import ModelClient, OpenAIClient, MockClient
from qval.project import get_active_project
from qval.engine.pricing import load_pricing
from qval.engine.response_logger import ResponseLogger
from qval.engine.schemas import DetectorResult, TestCase, TestResult, RunSummary
from qval.engine.test_runner import TestRunner
from qval.reports.report_generator import generate_reports
from qval.scorers.base_scorer import get_scorer
from qval.utils.file_loader import (
    ALL_SUITES,
    DEFAULT_SUITES,
    outputs_dir,
    load_all_suites,
    load_model_config,
    load_risk_matrix,
    load_scoring_config,
    load_test_suite,
)
from qval.utils.time_utils import generate_run_id, now_utc_iso

ProgressFn = Callable[[int, int, str | None], None]
LogFn = Callable[[str], None]


@dataclass
class RunExecution:
    run_id: str
    summary: RunSummary
    results: list[TestResult]
    canonical: CanonicalRun
    markdown_path: Path
    html_path: Path
    log_lines: list[str]


def build_client(config: dict, *, mock: bool, model_override: str | None,
                 seed: int) -> ModelClient:
    """Construct the model client from config + caller options."""

    model = model_override or config["model"]
    if mock or config.get("provider") == "mock":
        return MockClient(model=f"mock::{model}", seed=seed)

    provider = config.get("provider", "openai")
    if provider == "openai":
        return OpenAIClient(
            model=model,
            temperature=float(config.get("temperature", 0.2)),
            max_tokens=int(config.get("max_tokens", 800)),
            timeout_seconds=float(config.get("timeout_seconds", 30)),
            system_prompt=config.get("system_prompt", ""),
            retry=config.get("retry", {}),
            pricing=load_pricing(config),
        )
    if provider == "http":
        from qval.targets import HttpClient, HttpTarget

        target = HttpTarget.from_config(config.get("target", {}))
        return HttpClient(target, model=model_override or "http-target")
    raise ValueError(f"Unsupported provider {provider!r}. "
                     f"Use 'openai', 'http', or run with --mock.")


def load_cases(suite: str, limit: int | None,
               per_suite_limit: int | None = None) -> tuple[list[TestCase], str]:
    """Load TestCase objects for the requested suite name."""

    if suite == "all" and per_suite_limit is not None:
        raws: list[dict] = []
        for name in DEFAULT_SUITES:
            raws.extend(load_test_suite(name)[:per_suite_limit])
        suite_label = f"all (top {per_suite_limit}/cat)"
    elif suite == "all":
        raws = load_all_suites()
        suite_label = "all"
    else:
        raws = load_test_suite(suite)
        suite_label = suite

    cases = [
        TestCase.from_dict(raw, source=f"test_cases/{raw.get('category', '?')}")
        for raw in raws
    ]
    if limit is not None:
        cases = cases[:limit]
    return cases, suite_label


def load_cases_for_suites(suites: list[str], *, limit: int | None = None,
                          per_suite_limit: int | None = None) -> tuple[list[TestCase], str]:
    """Load one or more suites for web-triggered runs."""

    if not suites:
        raise ValueError("at least one suite is required")
    if len(suites) == 1:
        return load_cases(suites[0], limit, per_suite_limit=per_suite_limit)
    if "all" in suites:
        return load_cases("all", limit, per_suite_limit=per_suite_limit)

    cases: list[TestCase] = []
    for suite in suites:
        suite_cases, _label = load_cases(suite, None, per_suite_limit=None)
        if per_suite_limit is not None:
            suite_cases = suite_cases[:per_suite_limit]
        cases.extend(suite_cases)
    if limit is not None:
        cases = cases[:limit]
    return cases, ", ".join(suites)


def execute_run(*, suites: list[str] | None = None, suite: str | None = None,
                target_config: dict[str, Any] | None = None,
                model_override: str | None = None,
                limit: int | None = None,
                per_suite_limit: int | None = None,
                seed: int = 42,
                run_id: str | None = None,
                progress_fn: ProgressFn | None = None,
                emit_log: LogFn | None = None) -> RunExecution:
    """Execute a native Qval run and persist native + canonical artifacts."""

    model_config = _model_config_for_target(load_model_config(), target_config,
                                            model_override=model_override)
    scoring_config = load_scoring_config()
    risk_matrix = load_risk_matrix()

    run_id = run_id or generate_run_id()
    selected = suites if suites is not None else [suite or "all"]
    cases, suite_label = load_cases_for_suites(
        selected, limit=limit, per_suite_limit=per_suite_limit,
    )
    client = build_client(
        model_config,
        mock=model_config.get("provider") == "mock",
        model_override=model_config.get("_model_override"),
        seed=seed,
    )
    logger = ResponseLogger(run_id)
    log_lines: list[str] = []

    def log(msg: str) -> None:
        line = f"[{now_utc_iso()}] {msg}"
        log_lines.append(line)
        if emit_log:
            emit_log(line)

    log(f"Run ID:    {run_id}")
    log(f"Suite:     {suite_label}")
    log(f"Provider:  {client.provider}")
    log(f"Model:     {client.model}")
    log(f"Test count:{len(cases)}")

    runner = TestRunner(
        run_id=run_id,
        client=client,
        scorer_for=get_scorer,
        risk_matrix=risk_matrix,
        log_fn=log,
        progress_fn=progress_fn,
    )
    results, summary = runner.run(cases, suite_label=suite_label)

    logger.write_raw_prompts(results)
    logger.write_raw_responses(results)
    logger.write_scored_results(results)
    logger.write_manual_review(results)

    md_path, html_path = generate_reports(summary, results, risk_matrix, scoring_config)
    project_root = get_active_project().root
    summary.report_path = str(html_path.relative_to(project_root))
    summary.evidence_dir = str((outputs_dir() / "evidence" / run_id).relative_to(project_root))
    logger.write_summary(summary)
    logger.write_run_log(log_lines)

    canonical = run_summary_to_canonical(summary, results)
    _apply_controls(canonical)
    save_canonical(canonical, canonical_run_path(run_id))
    # Twin copy under results/ — the documented hand-off artifact for the gate
    # (F-04) and report (F-05) CLIs, and the U-00 acceptance criterion.
    save_canonical(canonical, outputs_dir() / "results" / f"{run_id}.canonical.json")

    return RunExecution(
        run_id=run_id,
        summary=summary,
        results=results,
        canonical=canonical,
        markdown_path=md_path,
        html_path=html_path,
        log_lines=log_lines,
    )


def canonical_run_path(run_id: str) -> Path:
    return outputs_dir() / "evidence" / run_id / "run.json"


def list_run_history() -> list[dict[str, Any]]:
    """Read run summaries from outputs/evidence."""

    evidence_root = outputs_dir() / "evidence"
    if not evidence_root.exists():
        return []

    runs: list[dict[str, Any]] = []
    for summary_path in evidence_root.glob("*/summary.json"):
        try:
            raw = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        runs.append(_history_item(raw, summary_path.parent.name))
    runs.sort(key=lambda item: item.get("started_at") or item.get("completed_at") or "",
              reverse=True)
    return runs


def load_run(run_id: str) -> CanonicalRun:
    """Load a canonical run, reconstructing older native runs when needed."""

    path = canonical_run_path(run_id)
    if path.is_file():
        return load_canonical(path)

    summary_path = outputs_dir() / "evidence" / run_id / "summary.json"
    results_path = outputs_dir() / "results" / f"{run_id}.json"
    try:
        summary_raw = json.loads(summary_path.read_text(encoding="utf-8"))
        results_raw = json.loads(results_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"run not found: {run_id}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"run {run_id} has malformed JSON: {exc}") from exc

    summary = RunSummary(**summary_raw)
    results = [_test_result_from_dict(raw) for raw in results_raw]
    canonical = run_summary_to_canonical(summary, results)
    _apply_controls(canonical)
    return canonical


def _model_config_for_target(default: dict, target_config: dict[str, Any] | None,
                             *, model_override: str | None) -> dict[str, Any]:
    config = dict(default)
    if target_config is None:
        config["_model_override"] = model_override
        return config

    target_type = str(target_config.get("type", "mock"))

    if target_type == "mock":
        config["provider"] = "mock"
        config["_model_override"] = target_config.get("model") or model_override
        return config

    if target_type == "provider":
        provider = str(target_config.get("provider", "openai"))
        config["provider"] = provider
        config["_model_override"] = target_config.get("model") or model_override
        return config

    if target_type == "http":
        config["provider"] = "http"
        config["target"] = {
            key: target_config[key]
            for key in (
                "url", "method", "headers", "body_template", "response_path",
                "content_type", "timeout_seconds", "retry",
            )
            if key in target_config
        }
        config["_model_override"] = target_config.get("model") or "http-target"
        return config

    raise ValueError("target.type must be one of: mock, provider, http")


def _apply_controls(run: CanonicalRun) -> None:
    try:
        map_controls(run, load_catalog())
    except ControlCatalogError:
        return


def _history_item(raw: dict[str, Any], fallback_run_id: str) -> dict[str, Any]:
    return {
        "run_id": raw.get("run_id") or fallback_run_id,
        "suite": raw.get("suite", ""),
        "provider": raw.get("provider", ""),
        "model": raw.get("model", ""),
        "started_at": raw.get("started_at", ""),
        "completed_at": raw.get("completed_at", ""),
        "total_tests": raw.get("total_tests", 0),
        "pass_count": raw.get("pass_count", 0),
        "fail_count": raw.get("fail_count", 0),
        "needs_review_count": raw.get("needs_review_count", 0),
        "error_count": raw.get("error_count", 0),
        "pass_rate": raw.get("pass_rate", 0.0),
        "weighted_pass_rate": raw.get("weighted_pass_rate", 0.0),
        "report_path": raw.get("report_path", ""),
        "evidence_dir": raw.get("evidence_dir", ""),
    }


def _test_result_from_dict(raw: dict[str, Any]) -> TestResult:
    data = dict(raw)
    data["detector_results"] = [
        DetectorResult(**item)
        for item in data.get("detector_results", [])
    ]
    return TestResult(**data)
