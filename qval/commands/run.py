"""`qval run` — execute a QA-style evaluation suite against an LLM.

This is the native eval pipeline relocated from qval/main.py. Behavior is
unchanged (relocate only): it wires together the file loader, model client,
test runner, and report generator + response logger.
"""

from __future__ import annotations

import argparse

from qval.engine.run_service import build_client, execute_run, load_cases
from qval.utils.file_loader import ALL_SUITES, PROJECT_ROOT


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
        "--target-url",
        default=None,
        help="Evaluate an HTTP target URL instead of the configured provider.",
    )
    sub.add_argument(
        "--target-method",
        default="POST",
        help="HTTP method for --target-url. Default: POST.",
    )
    sub.add_argument(
        "--target-body-template",
        default='{"message": "{{input}}"}',
        help="HTTP request body template for --target-url.",
    )
    sub.add_argument(
        "--target-response-path",
        default="$.reply",
        help="JSONPath-lite response field for --target-url. Default: $.reply.",
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


def run(args: argparse.Namespace) -> int:
    target_config = _target_config_from_args(args)
    execution = execute_run(
        suite=args.suite,
        target_config=target_config,
        model_override=args.model,
        limit=args.limit,
        per_suite_limit=args.per_suite_limit,
        seed=args.seed,
        emit_log=print,
    )
    summary = execution.summary
    md_path = execution.markdown_path

    # Final stdout summary block
    print("")
    print("=" * 64)
    print(f"Run ID:        {summary.run_id}")
    print(f"Suite:         {summary.suite}")
    print(f"Provider:      {summary.provider}")
    print(f"Model:         {summary.model}")
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


def _target_config_from_args(args: argparse.Namespace) -> dict | None:
    if args.target_url:
        return {
            "type": "http",
            "url": args.target_url,
            "method": args.target_method,
            "body_template": args.target_body_template,
            "response_path": args.target_response_path,
        }
    if args.mock:
        return {"type": "mock"}
    return None
