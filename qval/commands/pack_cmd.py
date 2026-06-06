"""`qval pack` — seal a canonical run into a signed evidence pack (F-08).

Build mode (default): writes ``run.json``, ``report.md``, ``report.html`` and a
hashed (optionally HMAC-signed) ``manifest.json`` to an evidence directory.
Verify mode (``--verify DIR``): re-walks the hash chain of an existing pack and
reports any tampering.

Signing key comes from ``--key`` or the ``QVAL_SIGNING_KEY`` environment
variable. Exit 0 on success; bad input/mode/missing-key → 2; a failed
verification → 1 (so CI can gate on pack integrity).
"""
from __future__ import annotations

import argparse
import os

from qval.canonical.io import load_canonical
from qval.evidence import (
    build_pack, verify_pack, EvidencePackError,
    ALL_MODES, MODE_INTERNAL,
)

ENV_SIGNING_KEY = "QVAL_SIGNING_KEY"


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser(
        "pack",
        help="Seal a run into a signed evidence pack, or verify an existing one.",
        description="Build a tamper-evident evidence pack (run + reports + signed "
                    "manifest) from a canonical run, or verify one with --verify.",
    )
    sub.add_argument("run", nargs="?", default=None,
                     help="Path to the canonical run.json to seal (build mode).")
    sub.add_argument("--out", default=None,
                     help="Pack directory. Default: outputs/evidence/<run_id>.")
    sub.add_argument("--mode", default=MODE_INTERNAL, choices=list(ALL_MODES),
                     help="Pack mode. Default: internal.")
    sub.add_argument("--ttl-days", type=int, default=None,
                     help="Retention TTL in days (recorded in the manifest).")
    sub.add_argument("--key", default=None,
                     help=f"Signing key. Falls back to ${ENV_SIGNING_KEY}.")
    sub.add_argument("--verify", default=None, metavar="DIR",
                     help="Verify an existing pack directory instead of building.")
    sub.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    key = args.key or os.environ.get(ENV_SIGNING_KEY)

    if args.verify:
        problems = verify_pack(args.verify, sign_key=key)
        if problems:
            print(f"Evidence pack INVALID: {args.verify}")
            for p in problems:
                print(f"  - {p}")
            return 1
        print(f"Evidence pack OK: {args.verify}")
        return 0

    if not args.run:
        print("qval pack: provide a run.json to seal, or --verify DIR.")
        return 2

    try:
        run_obj = load_canonical(args.run)
    except ValueError as e:
        print(f"qval pack: {e}")
        return 2

    try:
        pack, out_dir = build_pack(run_obj, args.out, mode=args.mode,
                                   sign_key=key, ttl_days=args.ttl_days)
    except EvidencePackError as e:
        print(f"qval pack: {e}")
        return 2

    signed = "signed" if pack.signature else "unsigned"
    print(f"Evidence pack written to {out_dir} ({pack.mode}, {signed})")
    print(f"  pack_id: {pack.pack_id}")
    print(f"  manifest_sha256: {pack.manifest_sha256}")
    print(f"  artifacts: {len(pack.artifacts)}")
    return 0
