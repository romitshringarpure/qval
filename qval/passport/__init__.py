"""AI Release Passport (F-13) — verifiable AI releases.

The product's front door: seal a canonical run's decision + evidence into a
signed, content-addressed credential (`build_passport`) and verify it
independently against a published Ed25519 key (`verify_passport`). Trustless by
design — an outside auditor checks it without trusting qval or the issuer.

    from qval.passport import build_passport, verify_passport, generate_keypair
"""

from .signing import (
    generate_keypair, KeyPair, fingerprint, short_fingerprint,
    public_pem_for, SigningError, ALGORITHM,
)
from .passport import (
    build_passport, assemble_core, load_passport, PassportError,
    DISCLAIMER, FORMAT, PASSPORT_FILE, PUBKEY_FILE,
)
from .verify import verify_passport, VerifyResult
from .manifest import sha256_hex, canonical_bytes, build_manifest

__all__ = [
    "generate_keypair", "KeyPair", "fingerprint", "short_fingerprint",
    "public_pem_for", "SigningError", "ALGORITHM",
    "build_passport", "assemble_core", "load_passport", "PassportError",
    "DISCLAIMER", "FORMAT", "PASSPORT_FILE", "PUBKEY_FILE",
    "verify_passport", "VerifyResult",
    "sha256_hex", "canonical_bytes", "build_manifest",
]
