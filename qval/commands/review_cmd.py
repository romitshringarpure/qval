"""`qval review` — human-in-the-loop decisions on findings (F-10).

Actions:
  queue   list findings awaiting review, worst-severity first (side-by-side
          with a baseline when given)
  assign  assign an owner to a finding
  decide  record an approve / reject / waive decision (audit trail + status)
  export  export the decision packet as JSON or CSV

`assign` and `decide` persist back to the run file (in place by default, or
``--out``) so decisions accumulate across a review session. Input/usage errors
exit 2.
"""
from __future__ import annotations

import argparse

from qval.canonical.io import load_canonical, save_canonical
from qval.review import (
    review_queue, apply_decision, assign_owner, ReviewError,
    ALL_DECISIONS, to_csv, to_json,
)


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser(
        "review",
        help="Human review workflow: queue, assign, decide, export.",
        description="Triage findings that pass/fail scoring cannot settle.",
    )
    actions = sub.add_subparsers(dest="review_action", metavar="<action>")

    q = actions.add_parser("queue", help="List findings awaiting review.")
    q.add_argument("run", help="Path to the canonical run.json.")
    q.add_argument("--baseline", default=None,
                   help="Baseline run.json for a side-by-side comparison.")
    q.add_argument("--all", action="store_true",
                   help="Include already-resolved (approved/waived) findings.")
    q.set_defaults(func=_queue)

    a = actions.add_parser("assign", help="Assign an owner to a finding.")
    a.add_argument("run")
    a.add_argument("--finding", required=True, help="Finding id to assign.")
    a.add_argument("--owner", required=True, help="Owner (name or id).")
    a.add_argument("--out", default=None, help="Output path (default: in place).")
    a.set_defaults(func=_assign)

    d = actions.add_parser("decide", help="Record approve/reject/waive.")
    d.add_argument("run")
    d.add_argument("--finding", required=True, help="Finding id to decide.")
    d.add_argument("--decision", required=True, choices=list(ALL_DECISIONS))
    d.add_argument("--reviewer", required=True, help="Reviewer id.")
    d.add_argument("--notes", default="", help="Reviewer notes.")
    d.add_argument("--reason", default="",
                   help="Waiver reason (required for --decision waive).")
    d.add_argument("--expires", default="",
                   help="Waiver expiry (ISO-8601 UTC; optional).")
    d.add_argument("--out", default=None, help="Output path (default: in place).")
    d.set_defaults(func=_decide)

    e = actions.add_parser("export", help="Export the decision packet.")
    e.add_argument("run")
    e.add_argument("--format", choices=["json", "csv"], default="json")
    e.add_argument("--out", default=None, help="Output path (default: stdout).")
    e.set_defaults(func=_export)

    sub.set_defaults(func=lambda args: _no_action(sub))


def _no_action(parser) -> int:
    parser.print_help()
    return 2


def _load(path):
    return load_canonical(path)


def _queue(args: argparse.Namespace) -> int:
    try:
        run = _load(args.run)
        baseline = _load(args.baseline) if args.baseline else None
    except ValueError as e:
        print(f"qval review: {e}")
        return 2

    items = review_queue(run, baseline, include_resolved=args.all)
    if not items:
        print("Review queue empty — nothing awaiting a decision.")
        return 0

    print(f"Review queue ({len(items)} item(s), worst severity first):")
    for it in items:
        owner = f" owner={it.owner}" if it.owner else ""
        decided = f" [{it.last_decision}]" if it.last_decision else ""
        print(f"  [{it.severity:>8}] {it.finding_id} ({it.category}) "
              f"{it.status}{owner}{decided} — {it.name}")
        if baseline is not None:
            print(f"             baseline: {it.baseline_status or '—'}")
    return 0


def _assign(args: argparse.Namespace) -> int:
    try:
        run = _load(args.run)
    except ValueError as e:
        print(f"qval review: {e}")
        return 2
    try:
        assign_owner(run, args.finding, args.owner)
    except ReviewError as e:
        print(f"qval review: {e}")
        return 2
    out = args.out or args.run
    save_canonical(run, out)
    print(f"Assigned {args.finding} to {args.owner} (written to {out}).")
    return 0


def _decide(args: argparse.Namespace) -> int:
    try:
        run = _load(args.run)
    except ValueError as e:
        print(f"qval review: {e}")
        return 2
    try:
        finding = apply_decision(
            run, args.finding, reviewer_id=args.reviewer, decision=args.decision,
            notes=args.notes, reason=args.reason, expires_at=args.expires)
    except ReviewError as e:
        print(f"qval review: {e}")
        return 2
    out = args.out or args.run
    save_canonical(run, out)
    print(f"{args.reviewer} {args.decision}d {args.finding} "
          f"-> status {finding.status} (written to {out}).")
    return 0


def _export(args: argparse.Namespace) -> int:
    try:
        run = _load(args.run)
    except ValueError as e:
        print(f"qval review: {e}")
        return 2
    content = to_csv(run) if args.format == "csv" else to_json(run)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"Decision packet written to {args.out}")
    else:
        print(content, end="")
    return 0
