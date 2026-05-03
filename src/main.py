"""CLI entry point for the AI Quality Evaluation Framework.

Usage examples:

    python src/main.py --suite all
    python src/main.py --suite safety
    python src/main.py --suite bias --model gpt-4o-mini
    python src/main.py --suite all --mock
    python src/main.py --suite hallucination --limit 2

The script wires together the four building blocks of the framework:
  - file loader (configs and test cases),
  - model client (OpenAI or mock),
  - test runner (executes a suite, scores each test),
  - report generator + response logger (writes evidence pack and reports).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python src/main.py` from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.engine.model_client import ModelClient, OpenAIClient, MockClient
from src.engine.response_logger import ResponseLogger
from src.engine.schemas import TestCase
from src.engine.test_runner import TestRunner
from src.reports.report_generator import generate_reports
from src.scorers.base_scorer import get_scorer
from src.utils.file_loader import (
    load_model_config, load_scoring_config, load_risk_matrix,
    load_test_suite, load_all_suites, ALL_SUITES, OUTPUTS_DIR,
)
from src.utils.time_utils import generate_run_id, now_utc_iso


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ai-quality-eval",
        description="Run a QA-style evaluation suite against an LLM.",
    )
    parser.add_argument(
        "--suite", default="all",
        choices=["all", *ALL_SUITES],
        help="Which test suite to run. Default: all.",
    )
    parser.add_argument(
        "--model", default=None,
        help="Override the model defined in config/model_config.json.",
    )
    parser.add_argument(
        "--mock", action="store_true",
        help="Use the offline mock provider. No API key required.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only run the first N test cases of the selected suite.",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Seed for the mock provider (also used for run order stability).",
    )
    return parser.parse_args(argv)


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
        )
    raise ValueError(f"Unsupported provider {provider!r}. "
                     f"Use 'openai' or run with --mock.")


def load_cases(suite: str, limit: int | None) -> tuple[list[TestCase], str]:
    """Load TestCase objects for the requested suite name."""
    if suite == "all":
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Load configs
    model_config = load_model_config()
    scoring_config = load_scoring_config()
    risk_matrix = load_risk_matrix()

    # Build everything
    run_id = generate_run_id()
    cases, suite_label = load_cases(args.suite, args.limit)
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


if __name__ == "__main__":
    raise SystemExit(main())
