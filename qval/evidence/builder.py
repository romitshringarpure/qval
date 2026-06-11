"""Evidence pack builder + verifier (F-08).

An *evidence pack* is the tamper-evident audit bundle a regulated or
quality-conscious team keeps to prove what was tested and decided: the canonical
run, the rendered reports, and a signed manifest of sha256 hashes. It fills the
F-01 ``Artifact`` + ``EvidencePack`` objects (defined then, populated now).

Tamper-evidence chain:

    each artifact ── sha256 ──► manifest entry
    sorted manifest entries ── sha256 ──► manifest_sha256
    manifest_sha256 ── HMAC(key) ──► signature   (optional)

Re-hashing any artifact, or the manifest, detects tampering; the HMAC signature
detects manifest substitution by anyone without the key. ``verify_pack`` walks
the chain back.

Modes (``EvidencePack.mode``):

* ``regulated``   — full bundle; **signing required** (no key -> error).
* ``internal``    — full bundle; signing optional.
* ``public-demo`` — full bundle; for sharing/demos.
* ``hash-only``   — manifest only, raw artifacts withheld (the bundle proves
                    *what ran* via hashes without disclosing prompts/responses).
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace
from pathlib import Path

from qval.canonical import Artifact, EvidencePack, CanonicalRun
from qval.reports.canonical_report import render_markdown, render_html
from qval.utils.file_loader import outputs_dir
from qval.utils.time_utils import now_utc_iso

MODE_REGULATED = "regulated"
MODE_INTERNAL = "internal"
MODE_PUBLIC_DEMO = "public-demo"
MODE_HASH_ONLY = "hash-only"
ALL_MODES = (MODE_REGULATED, MODE_INTERNAL, MODE_PUBLIC_DEMO, MODE_HASH_ONLY)

MANIFEST_NAME = "manifest.json"

# Artifact kinds + their on-disk filenames / media types.
_ARTIFACTS = [
    ("canonical_run", "run.json", "application/json"),
    ("report_markdown", "report.md", "text/markdown"),
    ("report_html", "report.html", "text/html"),
]


class EvidencePackError(Exception):
    """Raised on an invalid pack request (bad mode, missing signing key)."""


def build_pack(run: CanonicalRun, out_dir=None, *, mode: str = MODE_INTERNAL,
               sign_key: bytes | str | None = None,
               ttl_days: int | None = None) -> tuple[EvidencePack, Path]:
    """Build an evidence pack for ``run``; return (EvidencePack, pack_dir).

    Attaches the pack to ``run.evidence_pack``. The ``run.json`` artifact is the
    run *without* its evidence_pack (so its hash is stable and not circular).
    """
    if mode not in ALL_MODES:
        raise EvidencePackError(f"unknown mode {mode!r}; choose from {ALL_MODES}")
    key = _coerce_key(sign_key)
    if mode == MODE_REGULATED and key is None:
        raise EvidencePackError(
            "regulated packs must be signed; set a signing key "
            "(QVAL_SIGNING_KEY) or use --mode internal"
        )

    out_dir = Path(out_dir) if out_dir else outputs_dir() / "evidence" / run.run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    contents = _render_contents(run)

    artifacts: list[Artifact] = []
    for kind, filename, media_type in _ARTIFACTS:
        data = contents[kind]
        digest = hashlib.sha256(data).hexdigest()
        if mode != MODE_HASH_ONLY:
            (out_dir / filename).write_bytes(data)
        artifacts.append(Artifact(artifact_id=kind, kind=kind, path=filename,
                                  sha256=digest, media_type=media_type))

    manifest_sha256 = _manifest_hash(artifacts)
    signature = _sign(manifest_sha256, key) if key is not None else ""

    pack = EvidencePack(
        pack_id=f"pack_{run.run_id}",
        mode=mode,
        manifest_sha256=manifest_sha256,
        signature=signature,
        created_at=now_utc_iso(),
        retention_ttl_days=ttl_days,
        artifacts=artifacts,
    )
    _write_manifest(out_dir, run, pack)
    run.evidence_pack = pack
    return pack, out_dir


def verify_pack(pack_dir, sign_key: bytes | str | None = None) -> list[str]:
    """Verify a pack on disk; return a list of problems (empty = intact).

    Recomputes each present artifact's sha256, the manifest hash over all
    entries, and (when a key is given) the HMAC signature.
    """
    pack_dir = Path(pack_dir)
    manifest_path = pack_dir / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"manifest not found: {manifest_path}"]
    except json.JSONDecodeError as exc:
        return [f"manifest is not valid JSON: {exc}"]

    problems: list[str] = []
    artifacts = [Artifact.from_dict(a) for a in manifest.get("artifacts", [])]
    hash_only = manifest.get("mode") == MODE_HASH_ONLY

    for art in artifacts:
        fpath = pack_dir / art.path
        if not fpath.exists():
            if not hash_only:
                problems.append(f"missing artifact: {art.path}")
            continue
        actual = hashlib.sha256(fpath.read_bytes()).hexdigest()
        if actual != art.sha256:
            problems.append(f"hash mismatch: {art.path}")

    recomputed = _manifest_hash(artifacts)
    if recomputed != manifest.get("manifest_sha256"):
        problems.append("manifest_sha256 mismatch (manifest tampered)")

    signature = manifest.get("signature") or ""
    key = _coerce_key(sign_key)
    if signature:
        if key is None:
            problems.append("signature present but no key supplied to verify it")
        elif not hmac.compare_digest(signature, _sign(recomputed, key)):
            problems.append("signature mismatch (wrong key or tampered manifest)")

    return problems


# --- internals --------------------------------------------------------------

def _render_contents(run: CanonicalRun) -> dict[str, bytes]:
    # Hash/seal the run as it stands minus any prior pack pointer (avoids a
    # circular hash). Reports reflect the run's own decision if it was gated.
    bare = replace(run, evidence_pack=None)
    run_json = (json.dumps(bare.to_dict(), indent=2, ensure_ascii=False) + "\n")
    md = render_markdown(run, None, run.decision)
    html = render_html(run, None, run.decision)
    return {
        "canonical_run": run_json.encode("utf-8"),
        "report_markdown": md.encode("utf-8"),
        "report_html": html.encode("utf-8"),
    }


def _manifest_hash(artifacts: list[Artifact]) -> str:
    """Stable hash over (path, sha256) pairs, order-independent."""
    lines = sorted(f"{a.path}\x00{a.sha256}" for a in artifacts)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _sign(manifest_sha256: str, key: bytes) -> str:
    return hmac.new(key, manifest_sha256.encode("utf-8"), hashlib.sha256).hexdigest()


def _coerce_key(sign_key) -> bytes | None:
    if sign_key is None or sign_key == "":
        return None
    return sign_key.encode("utf-8") if isinstance(sign_key, str) else sign_key


def _write_manifest(out_dir: Path, run: CanonicalRun, pack: EvidencePack) -> None:
    manifest = {
        "pack_id": pack.pack_id,
        "run_id": run.run_id,
        "mode": pack.mode,
        "created_at": pack.created_at,
        "retention_ttl_days": pack.retention_ttl_days,
        "signed": bool(pack.signature),
        "manifest_sha256": pack.manifest_sha256,
        "signature": pack.signature,
        "artifacts": [
            {
                "artifact_id": a.artifact_id, "kind": a.kind, "path": a.path,
                "sha256": a.sha256, "media_type": a.media_type,
            }
            for a in pack.artifacts
        ],
    }
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
