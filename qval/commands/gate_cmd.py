"""`qval gate` — diff a run against a baseline and emit a release decision (F-04).

Loads two canonical runs, computes a diff, applies the built-in gate rules, and
prints a GO / CONDITIONAL-GO / NO-GO decision. Exit code is the CI signal:
NO-GO -> 1, otherwise 0; input errors -> 2.
"""
from __future__ import annotations

import argparse
import dataclasses

from qval.canonical import ALL_SEVERITIES, DECISION_NO_GO
from qval.canonical.io import load_canonical, save_canonical
from qval.gate import (
    diff_runs, evaluate, GateThresholds, POLICY_VERSION,
    load_policy, discover_policy, PolicyError,
)


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser(
        "gate",
        help="Diff a run against a baseline and emit a GO/CONDITIONAL-GO/NO-GO decision.",
        description="Compare a current canonical run against a baseline and "
                    "produce a release decision.",
    )
    sub.add_argument("--current", required=True,
                     help="Path to the current canonical run.json.")
    sub.add_argument("--baseline", default=None,
                     help="Path to the baseline run.json. Omit to gate on "
                          "absolute current state (first release).")
    sub.add_argument("--out", default=None,
                     help="Write the current run with the decision attached here.")
    sub.add_argument("--policy", default=None,
                     help="Path to a policy.yaml (F-06). Default: auto-discover a "
                          "policy.yaml at/above the cwd, else built-in rules.")
    sub.add_argument("--no-policy", action="store_true",
                     help="Ignore any policy file; use built-in rules.")
    sub.add_argument("--min-pass-rate", type=float, default=None,
                     help="Fail (NO-GO) if current pass-rate is below this (0-1). "
                          "Overrides the policy.")
    sub.add_argument("--block-severity", default=None,
                     help="Comma-separated severities whose NEW failures block. "
                          "Overrides the policy. Default: critical,high.")
    sub.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    try:
        thresholds, policy_version = _resolve_policy(args)
    except (ValueError, PolicyError) as e:
        print(f"qval gate: {e}")
        return 2

    try:
        current = load_canonical(args.current)
        baseline = load_canonical(args.baseline) if args.baseline else None
    except ValueError as e:
        print(f"qval gate: {e}")
        return 2

    diff = diff_runs(baseline, current)
    decision = evaluate(diff, thresholds, policy_version=policy_version)
    _print_decision(decision)

    if args.out:
        current.decision = decision
        save_canonical(current, args.out)
        print(f"\nGated run written to {args.out}")

    return 1 if decision.verdict == DECISION_NO_GO else 0


def _resolve_policy(args: argparse.Namespace) -> tuple[GateThresholds, str]:
    """Build the thresholds + provenance stamp from policy file and CLI flags.

    Precedence: built-in defaults < policy file < explicit CLI flags. A policy
    comes from ``--policy`` (explicit), or auto-discovery unless ``--no-policy``.
    """
    thresholds = GateThresholds()
    policy_version = POLICY_VERSION

    if not args.no_policy:
        policy_path = args.policy or discover_policy()
        if policy_path is not None:
            loaded = load_policy(policy_path)
            thresholds, policy_version = loaded.thresholds, loaded.version

    overrides: dict = {}
    if args.block_severity is not None:
        sevs = frozenset(s.strip() for s in args.block_severity.split(",") if s.strip())
        bad = sevs - set(ALL_SEVERITIES)
        if bad:
            raise ValueError(f"invalid --block-severity {sorted(bad)}; "
                             f"choose from {ALL_SEVERITIES}")
        overrides["block_new_severities"] = sevs
    if args.min_pass_rate is not None:
        overrides["min_pass_rate"] = args.min_pass_rate

    if overrides:
        thresholds = dataclasses.replace(thresholds, **overrides)
    return thresholds, policy_version


def _print_decision(decision) -> None:
    print(f"DECISION: {decision.verdict}")
    for reason in decision.rationale:
        print(f"  - {reason}")
