"""Content-addressed manifest + canonical serialization (F-13).

The passport's integrity rests on two deterministic operations: hashing each
artifact's bytes (so any edit changes its digest) and canonicalizing the signed
``core`` object (so the signature is over a byte-stable form). Both live here so
``build`` and ``verify`` use exactly the same rules — a mismatch in either would
break verification silently.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

HASH_ALGO = "sha256"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(obj: Any) -> bytes:
    """Deterministic JSON bytes: sorted keys, no insignificant whitespace.

    This is what gets signed and re-signed-against, so it must be identical on
    both ends regardless of dict insertion order.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def build_manifest(artifacts: list[tuple[str, bytes]]) -> dict:
    """Build a manifest from (path, bytes) pairs, sorted by path for stability."""
    entries = [{"path": path, "sha256": sha256_hex(data)}
               for path, data in artifacts]
    entries.sort(key=lambda e: e["path"])
    return {"algo": HASH_ALGO, "artifacts": entries}


def manifest_index(manifest: dict) -> dict[str, str]:
    """Map artifact path -> expected sha256 from a manifest."""
    return {e["path"]: e["sha256"] for e in manifest.get("artifacts", [])}
