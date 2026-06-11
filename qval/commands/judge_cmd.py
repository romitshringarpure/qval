"""`qval judge` — LLM judge-assist for borderline findings (F-12).

Pre-triages eligible (`needs_review`, non-excluded severity) findings with an
LLM judge, annotating each with a suggestion + confidence + rationale and
pinning the judge model/version into run metadata. The human override always
wins: a decision is only auto-applied when the config sets
``require_human_final_decision: false`` and confidence clears the floor.

Reads the `judge_assist` block from the project config (auto-discovered or
``--config``). Persists the annotated run in place (or ``--out``). Input/config
errors exit 2.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from qval.canonical.io import load_canonical, save_canonical
from qval.config import find_config_file, load_project_config, ProjectConfigError
from qval.judge import JudgeConfig, JudgeConfigError, JudgeCache, run_judge, make_llm_judge

_DEFAULT_CACHE = "outputs/judge_cache.json"


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser(
        "judge",
        help="LLM judge-assist: pre-triage borderline (needs_review) findings.",
        description="Annotate eligible findings with an LLM judge's suggestion, "
                    "confidence, and rationale. The human override always wins.",
    )
    sub.add_argument("run", help="Path to the canonical run.json.")
    sub.add_argument("--config", default=None,
                     help="Project config with a judge_assist block "
                          "(default: auto-discover qval.yaml).")
    sub.add_argument("--mock", action="store_true",
                     help="Use the offline mock provider as the judge (no API key).")
    sub.add_argument("--cache", default=_DEFAULT_CACHE,
                     help=f"Judge cache file. Default: {_DEFAULT_CACHE}.")
    sub.add_argument("--no-cache", action="store_true",
                     help="Disable the judge cache.")
    sub.add_argument("--out", default=None, help="Output path (default: in place).")
    sub.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    try:
        project = _load_project_config(args.config)
        config = JudgeConfig.from_config(project)
    except (ProjectConfigError, JudgeConfigError) as e:
        print(f"qval judge: {e}")
        return 2

    try:
        run_obj = load_canonical(args.run)
    except ValueError as e:
        print(f"qval judge: {e}")
        return 2

    try:
        judge_fn = _build_judge_fn(config, project, mock=args.mock)
    except RuntimeError as e:
        print(f"qval judge: {e}")
        return 2

    cache = None if args.no_cache else JudgeCache(args.cache)
    result = run_judge(run_obj, config, judge_fn, cache=cache)

    out = args.out or args.run
    save_canonical(run_obj, out)
    _print_summary(result, config)
    print(f"\nAnnotated run written to {out}")
    return 0


def _load_project_config(config_path) -> dict:
    if config_path:
        return load_project_config(Path(config_path))
    found = find_config_file()
    return load_project_config(found) if found else {}


def _build_judge_fn(config: JudgeConfig, project: dict, *, mock: bool):
    from qval.commands.run import build_client
    client = build_client(
        {**project, "provider": "mock" if mock else project.get("provider", "openai"),
         "model": config.model},
        mock=mock, model_override=config.model, seed=42)
    return make_llm_judge(client)


def _print_summary(result, config: JudgeConfig) -> None:
    mode = ("annotate-only (human decides)" if config.require_human_final_decision
            else f"auto-apply >= {config.min_confidence:.2f} confidence")
    print(f"Judge assist ({config.model}, {mode}):")
    print(f"  evaluated={result.evaluated} cached={result.cached} "
          f"applied={result.applied}")
    for v in result.verdicts:
        tag = " APPLIED" if v.applied else (" cached" if v.cached else "")
        print(f"  {v.finding_id}: {v.suggestion} (conf {v.confidence:.2f}){tag}")
