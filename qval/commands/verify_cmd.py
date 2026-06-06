"""`qval verify` — independently verify an AI Release Passport (F-13).

Re-hashes the bundle's artifacts, re-checks the Ed25519 signature over the
passport core, and prints a verdict. Trustless when given the issuer's
**published** public key via ``--pubkey``; without it, falls back to the
embedded key and warns. A failed verification exits non-zero so CI can gate on
release integrity.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from qval.passport import verify_passport, DISCLAIMER


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser(
        "verify",
        help="Independently verify an AI Release Passport's integrity + provenance.",
        description="Re-hash the evidence and check the signature. Proves "
                    "integrity, provenance, and who approved — not AI safety.",
    )
    sub.add_argument("passport", help="Passport bundle directory.")
    sub.add_argument("--pubkey", default=None,
                     help="Issuer's PUBLISHED public key PEM (trustless). "
                          "Omit to use the embedded key (warns).")
    sub.add_argument("--fingerprint", default=None,
                     help="Pin the expected issuer fingerprint (ed25519:<hex>).")
    sub.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    pubkey_pem = None
    if args.pubkey:
        try:
            pubkey_pem = Path(args.pubkey).read_bytes()
        except OSError as e:
            print(f"qval verify: cannot read --pubkey: {e}")
            return 2

    result = verify_passport(args.passport, pubkey_pem=pubkey_pem,
                             expected_fingerprint=args.fingerprint)

    if not result.ok:
        print(f"✗ TAMPERED / UNVERIFIED — {args.passport}")
        for p in result.problems:
            print(f"  - {p}")
        for w in result.warnings:
            print(f"  ! {w}")
        return 2

    _print_verified(result)
    return 0


def _print_verified(result) -> None:
    core = result.core
    sysd = core.get("system", {})
    dec = core.get("decision", {})
    summ = core.get("summary", {})
    trust = "trustless (pinned key)" if result.key_source == "pinned" \
        else "embedded key — see warning"

    print(f"✓ VERIFIED — evidence unaltered ({trust})")
    print(f"  system:   {sysd.get('name')} {sysd.get('version')} "
          f"({sysd.get('provider')}/{sysd.get('model')})")
    print(f"  tests:    {summ.get('tests')} "
          f"(critical failures: {summ.get('critical_failures')})")
    print(f"  decision: {dec.get('verdict')}")
    print(f"  approver: {dec.get('approver')}")
    print(f"  issuer:   {core.get('issuer', {}).get('fingerprint')}")
    for w in result.warnings:
        print(f"  ! {w}")
    print(f"\n{DISCLAIMER}")
