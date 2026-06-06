"""`qval run` — execute a QA-style evaluation suite against an LLM.

This is the native eval pipeline relocated from qval/main.py. Behavior is
unchanged (relocate only): it wires together the file loader, model client,
test runner, and report generator + response logger.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from qval.engine.model_client import ModelClient, OpenAIClient, MockClient
from qval.engine.pricing import load_pricing
from qval.engine.response_logger import ResponseLogger
from qval.engine.schemas import TestCase
from qval.engine.test_runner import TestRunner
from qval.reports.report_generator import generate_reports
from qval.scorers.base_scorer import get_scorer
from qval.utils.file_loader import (
    load_model_config, load_scoring_config, load_risk_matrix,
    load_test_suite, load_all_suites, ALL_SUITES, OUTPUTS_DIR,
)
from qval.utils.time_utils import generate_run_id, now_utc_iso

# run.py lives at qval/commands/run.py, so parents[2] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser(
        "run",
        help="Run a QA-style evaluation suite against an LLM.",
        description="Run a QA-style evaluation suite against an LLM.",
    )
    sub.add_argument(
        "--suite", default="all",
        choices=["all", *ALL_SUITES],
        help="Which test suite to run. Default: all.",
    )
    sub.add_argument(
        "--model", default=None,
        help="Override the model defined in config/model_config.json.",
    )
    sub.add_argument(
        "--mock", action="store_true",
        help="Use the offline mock provider. No API key required.",
    )
    sub.add_argument(
        "--limit", type=int, default=None,
        help="Only run the first N test cases of the selected suite.",
    )
    sub.add_argument(
        "--per-suite-limit", type=int, default=None,
        help="When --suite all, run the first N cases from each category "
             "(single run, single combined report).",
    )
    sub.add_argument(
        "--seed", type=int, default=42,
        help="Seed for the mock provider (also used for run order stability).",
    )
    sub.set_defaults(func=run)


def build_client(config: dict, *, mock: bool, model_override: str | None,
                 seed: int) -> ModelClient:
    """Construct the model client from config + CLI flags."""
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
        from qval.targets import HttpTarget, HttpClient
        target = HttpTarget.from_config(config.get("target", {}))
        return HttpClient(target, model=model_override or "http-target")
    raise ValueError(f"Unsupported provider {provider!r}. "
                     f"Use 'openai', 'http', or run with --mock.")


def load_cases(suite: str, limit: int | None,
               per_suite_limit: int | None = None) -> tuple[list[TestCase], str]:
    """Load TestCase objects for the requested suite name.

    --per-suite-limit only applies when suite == "all"; takes first N cases
    from each category, then concatenates. Useful for a cross-category smoke.
    """
    if suite == "all" and per_suite_limit is not None:
        raws: list[dict] = []
        for s in ALL_SUITES:
            raws.extend(load_test_suite(s)[:per_suite_limit])
        suite_label = f"all (top {per_suite_limit}/cat)"
    elif suite == "all":
        raws = load_all_suites()
        suite_label = "all"
    else:
        raws = load_test_suite(suite)
        suite_label = suite

    cases: list[TestCase] = []
    for raw in raws:
        cases.append(TestCase.from_dict(raw, source=f"test_cases/{raw.get('category', '?')}"))
    if limit is not None:
        cases = cases[:limit]
    return cases, suite_label


def run(args: argparse.Namespace) -> int:
    # Load configs
    model_config = load_model_config()
    scoring_config = load_scoring_config()
    risk_matrix = load_risk_matrix()

    # Build everything
    run_id = generate_run_id()
    cases, suite_label = load_cases(args.suite, args.limit,
                                    per_suite_limit=args.per_suite_limit)
    client = build_client(model_config, mock=args.mock,
                          model_override=args.model, seed=args.seed)
    logger = ResponseLogger(run_id)

    log_lines: list[str] = []

    def log(msg: str) -> None:
        line = f"[{now_utc_iso()}] {msg}"
        log_lines.append(line)
        print(line)

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
    )

    results, summary = runner.run(cases, suite_label=suite_label)

    # Persist evidence pack
    logger.write_raw_prompts(results)
    logger.write_raw_responses(results)
    logger.write_scored_results(results)
    logger.write_manual_review(results)

    # Reports
    md_path, html_path = generate_reports(summary, results, risk_matrix, scoring_config)
    summary.report_path = str(html_path.relative_to(PROJECT_ROOT))
    summary.evidence_dir = str((OUTPUTS_DIR / "evidence" / run_id).relative_to(PROJECT_ROOT))
    logger.write_summary(summary)
    logger.write_run_log(log_lines)

    # Final stdout summary block
    print("")
    print("=" * 64)
    print(f"Run ID:        {run_id}")
    print(f"Suite:         {suite_label}")
    print(f"Provider:      {client.provider}")
    print(f"Model:         {client.model}")
    print(f"Tests run:     {summary.total_tests}")
    print(f"Pass:          {summary.pass_count}")
    print(f"Fail:          {summary.fail_count}")
    print(f"Needs review:  {summary.needs_review_count}")
    print(f"Pass rate:     {summary.pass_rate:.1%}   "
          f"(severity-weighted: {summary.weighted_pass_rate:.1%})")
    print(f"HTML report:   {summary.report_path}")
    print(f"MD report:     {md_path.relative_to(PROJECT_ROOT)}")
    print(f"Evidence:      {summary.evidence_dir}/")
    print("=" * 64)

    # Non-zero exit when there are critical failures — useful for CI gating.
    return 1 if summary.critical_failures else 0
