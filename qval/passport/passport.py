"""Build an AI Release Passport from a canonical run (F-13).

Assembles the signed ``core`` (system identity + decision + approver + summary +
governance + a content-addressed manifest of the evidence artifacts), signs
``canonical(core)`` with the issuer's private key, and writes a self-contained
bundle. The signed payload *contains* the artifact manifest, so both artifact
tampering (hash mismatch) and claim tampering (signature mismatch) are caught by
``verify``.

Guardrail: a passport records *who approved* the release; it never asserts the
AI is safe. qval is the instrument, not the certifier.
"""
from __future__ import annotations

import json
from pathlib import Path

from qval.canonical import (
    CanonicalRun,
    STATUS_PASSED, STATUS_FAILED, STATUS_NEEDS_REVIEW, STATUS_BLOCKED,
    SEVERITY_CRITICAL,
)
from qval.reports.canonical_report import render_markdown, render_html
from qval.utils.file_loader import outputs_dir
from qval.utils.time_utils import now_utc_iso
from . import signing
from .manifest import build_manifest, canonical_bytes, sha256_hex

FORMAT = "qval-release-passport/v1"
PASSPORT_FILE = "passport.json"
PUBKEY_FILE = "issuer.pub"

DISCLAIMER = (
    "This passport verifies integrity, provenance, and the named approver — "
    "not that the AI system is safe. The release was authorized by the approver, "
    "not by qval. qval is the instrument, not the certifier."
)

# Findings that count as a failure for the critical-failure headline.
_FAILING = frozenset({STATUS_FAILED, STATUS_BLOCKED})


class PassportError(Exception):
    """Raised when a passport cannot be built (e.g. no approver)."""


def build_passport(run: CanonicalRun, *, private_pem: bytes, approver: str = "",
                   system_name: str = "", version: str = "",
                   out_dir=None) -> tuple[dict, Path]:
    """Build, sign, and write a passport bundle. Returns (passport dict, dir)."""
    public_pem = signing.public_pem_for(private_pem)
    core, artifacts = assemble_core(
        run, approver=approver, system_name=system_name, version=version,
        public_pem=public_pem)

    signature = signing.sign_data(private_pem, canonical_bytes(core)).hex()
    passport = {
        "format": FORMAT,
        "core": core,
        "signature": {
            "algo": signing.ALGORITHM,
            "value": signature,
            "public_key_pem": public_pem.decode("utf-8"),
        },
        "disclaimer": DISCLAIMER,
    }

    out_dir = Path(out_dir) if out_dir else outputs_dir() / "passports" / core["passport_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    for path, data in artifacts:
        (out_dir / path).write_bytes(data)
    (out_dir / PASSPORT_FILE).write_text(
        json.dumps(passport, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / PUBKEY_FILE).write_bytes(public_pem)
    return passport, out_dir


def assemble_core(run: CanonicalRun, *, approver: str, system_name: str,
                  version: str, public_pem: bytes) -> tuple[dict, list]:
    """Build the signed ``core`` dict and the (path, bytes) artifact list.

    Pure: no signing, no disk. The same artifacts hashed here are written to the
    bundle, so ``verify`` re-hashing them reproduces the manifest exactly.
    """
    resolved_approver = approver or _derive_approver(run)
    if not resolved_approver:
        raise PassportError(
            "a passport requires an approver: pass --approver, or have an "
            "approved finding in the run (qval review decide ... --decision approve)")

    artifacts = _artifacts(run)
    core = {
        "passport_id": f"passport_{run.run_id}",
        "issued_at": now_utc_iso(),
        "system": {
            "name": system_name or run.suite or run.run_id,
            "version": version or run.prompt_version or "unspecified",
            "model": run.model,
            "provider": run.provider,
        },
        "decision": {
            "verdict": run.decision.verdict if run.decision else "UNGATED",
            "approver": resolved_approver,
            "policy_version": run.decision.policy_version if run.decision else "",
        },
        "summary": _summary(run),
        "governance": _governance(run),
        "manifest": build_manifest(artifacts),
        "issuer": {
            "algo": signing.ALGORITHM,
            "fingerprint": signing.fingerprint(public_pem),
        },
    }
    return core, artifacts


# --- internals --------------------------------------------------------------

def _artifacts(run: CanonicalRun) -> list[tuple[str, bytes]]:
    run_json = (json.dumps(run.to_dict(), indent=2, ensure_ascii=False) + "\n")
    md = render_markdown(run, None, run.decision)
    html = render_html(run, None, run.decision)
    return [
        ("run.json", run_json.encode("utf-8")),
        ("report.md", md.encode("utf-8")),
        ("report.html", html.encode("utf-8")),
    ]


def _summary(run: CanonicalRun) -> dict:
    findings = run.findings
    total = len(findings)
    passed = sum(1 for f in findings if f.status == STATUS_PASSED)
    failed = sum(1 for f in findings if f.status == STATUS_FAILED)
    review = sum(1 for f in findings if f.status == STATUS_NEEDS_REVIEW)
    critical = sum(1 for f in findings
                   if f.severity == SEVERITY_CRITICAL and f.status in _FAILING)
    return {
        "tests": total,
        "passed": passed,
        "failed": failed,
        "needs_review": review,
        "critical_failures": critical,
        "pass_rate": round(passed / total, 4) if total else 1.0,
    }


def _governance(run: CanonicalRun) -> list[dict]:
    if not run.controls:
        return []
    from qval.controls import coverage
    return [
        {"control_id": c.control_id, "framework": c.framework, "status": c.status}
        for c in coverage(run)
    ]


def _derive_approver(run: CanonicalRun) -> str:
    """Most recent reviewer who approved, across all findings (F-10)."""
    approvals = [
        r for f in run.findings for r in f.reviewers if r.decision == "approve"
    ]
    if not approvals:
        return ""
    approvals.sort(key=lambda r: r.decided_at)
    return approvals[-1].reviewer_id


def load_passport(passport_dir) -> dict:
    """Read a passport.json from a bundle directory."""
    path = Path(passport_dir) / PASSPORT_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PassportError(f"no {PASSPORT_FILE} in {passport_dir}")
    except json.JSONDecodeError as e:
        raise PassportError(f"{path} is not valid JSON: {e}")
