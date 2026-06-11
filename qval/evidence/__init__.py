"""Evidence packs (F-08).

Builds and verifies the tamper-evident audit bundle for a canonical run: the
run, its reports, and a signed manifest of sha256 hashes.

    from qval.evidence import build_pack, verify_pack
"""

from .builder import (
    build_pack, verify_pack, EvidencePackError,
    ALL_MODES, MODE_REGULATED, MODE_INTERNAL, MODE_PUBLIC_DEMO, MODE_HASH_ONLY,
    MANIFEST_NAME,
)

__all__ = [
    "build_pack", "verify_pack", "EvidencePackError",
    "ALL_MODES", "MODE_REGULATED", "MODE_INTERNAL", "MODE_PUBLIC_DEMO",
    "MODE_HASH_ONLY", "MANIFEST_NAME",
]
