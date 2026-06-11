"""Independently verify an AI Release Passport (F-13).

Verification must not require trusting qval or the issuer. It re-hashes the
artifacts (content-addressing catches any byte change), re-canonicalizes the
signed ``core``, and checks the detached Ed25519 signature against a public key.

Trust comes from the key the auditor **pins**:
- ``pubkey_pem`` supplied (the published key, obtained out-of-band) → trustless.
- no key → the embedded key is used, but the result carries a **warning** and
  the issuer fingerprint so the auditor can pin the published key. Embedded-only
  is convenience, never the trust root.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import signing
from .manifest import sha256_hex, canonical_bytes, manifest_index
from .passport import load_passport, PassportError


@dataclass
class VerifyResult:
    ok: bool
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    core: dict = field(default_factory=dict)
    key_source: str = ""          # "pinned" (--pubkey) or "embedded"


def verify_passport(passport_dir, *, pubkey_pem: bytes | None = None,
                    expected_fingerprint: str | None = None) -> VerifyResult:
    """Verify a passport bundle: integrity + provenance. Returns a VerifyResult."""
    passport_dir = Path(passport_dir)
    try:
        passport = load_passport(passport_dir)
    except PassportError as e:
        return VerifyResult(ok=False, problems=[str(e)])

    core = passport.get("core", {})
    sig = passport.get("signature", {})
    result = VerifyResult(ok=False, core=core)

    # 1. Integrity — re-hash every artifact named in the manifest.
    _check_artifacts(passport_dir, core, result)

    # 2. Resolve the verifying key (pinned beats embedded).
    public_pem, embedded_pem = _resolve_key(pubkey_pem, sig, result)
    if public_pem is None:
        return _finalize(result)

    # 3. Provenance — signature over canonical(core).
    _check_signature(core, sig, public_pem, result)

    # 4. Fingerprint pinning + issuer consistency.
    _check_fingerprint(core, public_pem, embedded_pem, expected_fingerprint,
                       pubkey_pem is not None, result)

    return _finalize(result)


# --- steps ------------------------------------------------------------------

def _check_artifacts(passport_dir: Path, core: dict, result: VerifyResult) -> None:
    manifest = core.get("manifest", {})
    expected = manifest_index(manifest)
    if not expected:
        result.warnings.append("manifest lists no artifacts")
    for path, want in expected.items():
        fpath = passport_dir / path
        if not fpath.is_file():
            result.problems.append(f"TAMPERED: missing artifact '{path}'")
            continue
        got = sha256_hex(fpath.read_bytes())
        if got != want:
            result.problems.append(
                f"TAMPERED: artifact '{path}' hash mismatch "
                f"(expected {want[:12]}…, got {got[:12]}…)")


def _resolve_key(pubkey_pem, sig: dict, result: VerifyResult):
    embedded = sig.get("public_key_pem")
    embedded_pem = embedded.encode("utf-8") if isinstance(embedded, str) else None
    if pubkey_pem is not None:
        result.key_source = "pinned"
        return pubkey_pem, embedded_pem
    if embedded_pem is not None:
        result.key_source = "embedded"
        result.warnings.append(
            "verified against the key EMBEDDED in the passport, not a pinned "
            "published key. For trustless verification, obtain the issuer's "
            "published public key out-of-band and pass --pubkey (or pin "
            "--fingerprint).")
        return embedded_pem, embedded_pem
    result.problems.append("no public key supplied and none embedded; cannot verify")
    return None, None


def _check_signature(core: dict, sig: dict, public_pem: bytes,
                     result: VerifyResult) -> None:
    value = sig.get("value", "")
    try:
        signature = bytes.fromhex(value)
    except ValueError:
        result.problems.append("signature is not valid hex")
        return
    if not signing.verify_data(public_pem, signature, canonical_bytes(core)):
        result.problems.append(
            "TAMPERED: signature does not verify over the passport core "
            "(claims altered, or signed by a different key)")


def _check_fingerprint(core: dict, public_pem: bytes, embedded_pem,
                       expected_fingerprint, key_pinned: bool,
                       result: VerifyResult) -> None:
    actual = signing.fingerprint(public_pem)

    if expected_fingerprint:
        want = expected_fingerprint.strip()
        if want not in (actual, signing.short_fingerprint(public_pem)):
            result.problems.append(
                f"fingerprint mismatch: expected {want}, key is {actual}")

    # The passport claims an issuer fingerprint; the verifying key must match it,
    # else the bundle was signed by a different key than it advertises.
    claimed = core.get("issuer", {}).get("fingerprint")
    if claimed and claimed != actual:
        result.problems.append(
            f"issuer fingerprint mismatch: passport claims {claimed}, "
            f"verifying key is {actual}")

    # When pinning an external key, surface if it differs from the embedded one.
    if key_pinned and embedded_pem is not None:
        try:
            if signing.fingerprint(embedded_pem) != actual:
                result.warnings.append(
                    "pinned key differs from the embedded key (expected when the "
                    "embedded key is untrusted; the pinned key is authoritative).")
        except signing.SigningError:
            pass


def _finalize(result: VerifyResult) -> VerifyResult:
    result.ok = not result.problems
    return result
