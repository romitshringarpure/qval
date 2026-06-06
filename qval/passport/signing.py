"""Asymmetric signing for the Release Passport (F-13).

Ed25519 detached signatures are the trust root: the issuer signs with a
**private** key it never shares; anyone verifies with the **published public**
key. This is the difference between trustless verification and a self-hash —
an HMAC (F-08) only proves the holder of the shared secret signed it, which is
useless to an outside auditor.

Thin wrapper over `cryptography` (the one new dependency). Keys are PEM bytes at
the boundary so the rest of the codebase stays free of crypto types.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

ALGORITHM = "ed25519"


class SigningError(Exception):
    """Raised on a missing crypto backend or a malformed key."""


def _backend():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
        return serialization, ed25519
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise SigningError(
            "the 'cryptography' package is required for passport signing; "
            "install it with `pip install cryptography`."
        ) from exc


@dataclass
class KeyPair:
    private_pem: bytes
    public_pem: bytes


def generate_keypair() -> KeyPair:
    """Generate an Ed25519 keypair as (PKCS8 private PEM, SPKI public PEM)."""
    serialization, ed25519 = _backend()
    private = ed25519.Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return KeyPair(private_pem=private_pem, public_pem=public_pem)


def public_pem_for(private_pem: bytes) -> bytes:
    serialization, _ = _backend()
    private = _load_private(private_pem)
    return private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def sign_data(private_pem: bytes, data: bytes) -> bytes:
    """Detached signature over ``data`` (raw bytes; callers hex-encode)."""
    private = _load_private(private_pem)
    return private.sign(data)


def verify_data(public_pem: bytes, signature: bytes, data: bytes) -> bool:
    """Verify a detached signature. Returns False on any failure (never raises
    on a bad signature — only on a malformed key)."""
    serialization, _ = _backend()
    public = _load_public(public_pem)
    try:
        public.verify(signature, data)
        return True
    except Exception:  # noqa: BLE001 - InvalidSignature and friends
        return False


def fingerprint(public_pem: bytes) -> str:
    """Stable issuer fingerprint: ``ed25519:<sha256 of the raw public key>``.

    Over the *raw* key bytes (not the PEM envelope) so whitespace/encoding
    differences never change the fingerprint an auditor pins.
    """
    serialization, _ = _backend()
    public = _load_public(public_pem)
    raw = public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return f"{ALGORITHM}:{hashlib.sha256(raw).hexdigest()}"


def short_fingerprint(public_pem: bytes) -> str:
    fp = fingerprint(public_pem)
    algo, _, digest = fp.partition(":")
    return f"{algo}:{digest[:16]}"


# --- internals --------------------------------------------------------------

def _load_private(private_pem: bytes):
    serialization, ed25519 = _backend()
    try:
        key = serialization.load_pem_private_key(_as_bytes(private_pem), password=None)
    except Exception as exc:  # noqa: BLE001
        raise SigningError(f"could not load private key: {exc}") from exc
    if not isinstance(key, ed25519.Ed25519PrivateKey):
        raise SigningError("private key is not an Ed25519 key")
    return key


def _load_public(public_pem: bytes):
    serialization, ed25519 = _backend()
    try:
        key = serialization.load_pem_public_key(_as_bytes(public_pem))
    except Exception as exc:  # noqa: BLE001
        raise SigningError(f"could not load public key: {exc}") from exc
    if not isinstance(key, ed25519.Ed25519PublicKey):
        raise SigningError("public key is not an Ed25519 key")
    return key


def _as_bytes(pem) -> bytes:
    return pem if isinstance(pem, bytes) else str(pem).encode("utf-8")
