"""`qval passport` — issue an AI Release Passport (F-13, flagship).

Actions:
  keygen   generate an Ed25519 issuer keypair (publish the .pub!)
  create   seal a canonical run into a signed, verifiable passport bundle
  show     print a passport's claims (no crypto)

The signing key comes from ``--key`` or ``$QVAL_PASSPORT_KEY`` (a path to a
private PEM). A passport records *who approved* the release — it never certifies
the AI is safe. Usage/IO errors exit 2.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from qval.canonical.io import load_canonical
from qval.passport import (
    generate_keypair, build_passport, load_passport, fingerprint,
    short_fingerprint, PassportError, SigningError, DISCLAIMER,
)

ENV_KEY = "QVAL_PASSPORT_KEY"


def add_parser(subparsers) -> None:
    sub = subparsers.add_parser(
        "passport",
        help="Issue a verifiable AI Release Passport (keygen / create / show).",
        description="Seal a release decision + evidence into a signed, "
                    "independently verifiable credential.",
    )
    actions = sub.add_subparsers(dest="passport_action", metavar="<action>")

    k = actions.add_parser("keygen", help="Generate an Ed25519 issuer keypair.")
    k.add_argument("--out", default="issuer_key",
                   help="Private key path; public key written to <out>.pub.")
    k.add_argument("--force", action="store_true", help="Overwrite existing keys.")
    k.set_defaults(func=_keygen)

    c = actions.add_parser("create", help="Create a signed passport from a run.")
    c.add_argument("--from", dest="run", required=True,
                   help="Path to the canonical run.json.")
    c.add_argument("--approver", default="",
                   help="Who authorizes this release (required unless the run "
                        "has an approved finding).")
    c.add_argument("--system", default="", help="System name (default: run suite).")
    c.add_argument("--version", default="", help="System version.")
    c.add_argument("--key", default=None,
                   help=f"Issuer private key PEM. Falls back to ${ENV_KEY}.")
    c.add_argument("--out", default=None,
                   help="Bundle directory. Default: outputs/passports/<id>.")
    c.set_defaults(func=_create)

    s = actions.add_parser("show", help="Print a passport's claims (no crypto).")
    s.add_argument("passport", help="Passport bundle directory.")
    s.set_defaults(func=_show)

    sub.set_defaults(func=lambda args: _no_action(sub))


def _no_action(parser) -> int:
    parser.print_help()
    return 2


def _keygen(args: argparse.Namespace) -> int:
    priv = Path(args.out)
    pub = Path(f"{args.out}.pub")
    if not args.force and (priv.exists() or pub.exists()):
        print(f"qval passport: refusing to overwrite {priv} / {pub} (use --force).")
        return 2
    kp = generate_keypair()
    priv.write_bytes(kp.private_pem)
    try:
        os.chmod(priv, 0o600)
    except OSError:
        pass
    pub.write_bytes(kp.public_pem)
    print(f"Issuer keypair written:\n  private: {priv} (keep secret)\n  public:  {pub}")
    print(f"  fingerprint: {short_fingerprint(kp.public_pem)}")
    print("\nPUBLISH the public key (commit it / post it at a known URL) so "
          "auditors can pin it and verify trustlessly.")
    return 0


def _create(args: argparse.Namespace) -> int:
    try:
        private_pem = _read_key(args.key)
    except (ValueError, OSError) as e:
        print(f"qval passport: {e}")
        return 2
    try:
        run = load_canonical(args.run)
    except ValueError as e:
        print(f"qval passport: {e}")
        return 2
    try:
        passport, out_dir = build_passport(
            run, private_pem=private_pem, approver=args.approver,
            system_name=args.system, version=args.version, out_dir=args.out)
    except (PassportError, SigningError) as e:
        print(f"qval passport: {e}")
        return 2

    core = passport["core"]
    pub_pem = passport["signature"]["public_key_pem"].encode("utf-8")
    print(f"AI Release Passport written to {out_dir}")
    _print_core(core)
    print(f"  issuer fingerprint: {short_fingerprint(pub_pem)}")
    print(f"\nVerify:  qval verify {out_dir} --pubkey <published issuer key>")
    print(f"\n{DISCLAIMER}")
    return 0


def _show(args: argparse.Namespace) -> int:
    try:
        passport = load_passport(args.passport)
    except PassportError as e:
        print(f"qval passport: {e}")
        return 2
    _print_core(passport.get("core", {}))
    print(f"\n{passport.get('disclaimer', DISCLAIMER)}")
    return 0


def _print_core(core: dict) -> None:
    sysd = core.get("system", {})
    dec = core.get("decision", {})
    summ = core.get("summary", {})
    print(f"  system:   {sysd.get('name')} {sysd.get('version')} "
          f"({sysd.get('provider')}/{sysd.get('model')})")
    print(f"  decision: {dec.get('verdict')}  approver: {dec.get('approver')}")
    print(f"  tests:    {summ.get('tests')} "
          f"(passed {summ.get('passed')}, failed {summ.get('failed')}, "
          f"needs_review {summ.get('needs_review')}, "
          f"critical_failures {summ.get('critical_failures')})")
    gov = core.get("governance", [])
    if gov:
        ctrls = ", ".join(f"{g['control_id']}={g['status']}" for g in gov)
        print(f"  controls: {ctrls}")


def _read_key(key_arg) -> bytes:
    path = key_arg or os.environ.get(ENV_KEY)
    if not path:
        raise ValueError(
            f"no signing key: pass --key <private.pem> or set ${ENV_KEY}. "
            f"Generate one with `qval passport keygen`.")
    data = Path(path).read_bytes()
    return data
