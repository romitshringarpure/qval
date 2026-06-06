# F-08 · Evidence Pack — Change Record

**Status:** ✅ Done
**Date:** 2026-06-05
**Sprint:** 4
**Depends on:** F-01 (`Artifact` + `EvidencePack` fields), F-05 (reports to seal)

---

## 1. What this is

`qval pack` seals a canonical run into a **tamper-evident audit bundle**: the
run, its rendered reports, and a signed manifest of sha256 hashes. This is the
artifact a regulated or quality-conscious team retains to prove *what was
tested and decided* — and to detect if anyone altered it afterward.

```bash
qval pack gated.json --mode regulated            # QVAL_SIGNING_KEY signs it
qval pack --verify outputs/evidence/run_x         # re-walk the hash chain
```
```
Evidence pack written to outputs/evidence/run_x (regulated, signed)
  pack_id: pack_run_x
  manifest_sha256: 17de2b01…
  artifacts: 3
```

The `Artifact` and `EvidencePack` objects already existed (F-01, unfilled).
F-08 fills them and adds the bundle on disk.

---

## 2. Tamper-evidence chain

```
each artifact ── sha256 ──► manifest entry
sorted entries ── sha256 ──► manifest_sha256
manifest_sha256 ── HMAC(key) ──► signature   (optional)
```

- Re-hashing any artifact detects content tampering.
- Re-hashing the manifest detects entry tampering (`manifest_sha256 mismatch`).
- The HMAC signature detects manifest substitution by anyone without the key.

The manifest hash is computed over **sorted** `(path, sha256)` pairs, so it is
order-independent and stable. `verify_pack` walks the whole chain backward and
returns a list of problems (empty = intact).

---

## 3. Artifacts

| Artifact | File | Media type |
|----------|------|------------|
| `canonical_run` | `run.json` | application/json |
| `report_markdown` | `report.md` | text/markdown |
| `report_html` | `report.html` | text/html |

The sealed `run.json` is the run **with its `evidence_pack` pointer stripped**
— otherwise hashing the run would be circular (the hash would feed the pack
that the run points back to). Reports reflect the run's own gate decision and
control coverage if those were attached upstream (`map` / `gate`).

---

## 4. Modes

| Mode | Raw artifacts | Signing |
|------|---------------|---------|
| `regulated` | written | **required** (no key → error) |
| `internal` (default) | written | optional |
| `public-demo` | written | optional |
| `hash-only` | **withheld** (manifest only) | optional |

`hash-only` proves *what ran* via hashes without disclosing prompts/responses —
useful when the content is sensitive but the audit trail must exist.
`verify_pack` skips the absent-file checks for a hash-only pack and still
verifies the manifest hash and signature.

---

## 5. Signing key & retention

- Key source: `--key` flag or the `QVAL_SIGNING_KEY` env var (CI secret).
- Signature is `HMAC-SHA256(manifest_sha256, key)` (stdlib `hmac`; verification
  uses `compare_digest`). No external crypto dependency.
- `--ttl-days N` records a retention TTL in the manifest (enforcement is a
  storage-layer concern, out of scope; the value travels with the bundle).

---

## 6. CLI & exit codes

```bash
qval pack <run.json> [--out DIR] [--mode MODE] [--ttl-days N] [--key K]
qval pack --verify DIR [--key K]
```

- Build default dir: `outputs/evidence/<run_id>`.
- **Exit codes:** success → `0`; failed verification → **`1`** (CI can gate on
  pack integrity); bad input / mode / missing-key → `2`.

---

## 7. Files

| File | Change |
|------|--------|
| `qval/evidence/builder.py` | **New.** `build_pack`, `verify_pack`, `EvidencePackError`, modes, hashing/signing. |
| `qval/evidence/__init__.py` | **New.** Package surface. |
| `qval/commands/pack_cmd.py` | **New.** `qval pack` (build + `--verify`). |
| `qval/cli.py` | Wire `pack_cmd.add_parser`. |
| `tests/test_evidence.py` | **New.** 20 tests. |

---

## 8. Tests (TDD)

Build: writes all artifacts + manifest, run.json excludes the pack pointer,
unsigned without a key, signed with one, TTL recorded. Verify: clean pack OK,
artifact tampering caught, wrong key caught, signature-without-key flagged,
manifest tampering caught, missing manifest. Modes: hash-only writes only the
manifest and still verifies, regulated without a key raises, regulated with a
key signs, unknown mode raises. CLI: build exit 0, verify round-trip exit 0,
tampered verify exit 1, regulated-no-key exit 2, no-args exit 2.

---

## 9. Scope cuts (YAGNI)

No zip/tar archiving (a directory is portable and diffable; archiving is a
trivial later wrapper), no asymmetric signatures / external KMS (HMAC with a
shared secret is enough for tamper-evidence; PKI is a later need), no TTL
*enforcement* (recorded, not swept), no encryption-at-rest (a storage concern),
no embedding raw prompt/response logs beyond what the canonical run carries.

---

## 10. Result

`tests/test_evidence.py` — **20 tests**. **Full suite: 173 pass**, no
regressions (+20). End-to-end confirmed —
`map → gate --policy → pack --mode regulated → pack --verify`:
the mapped run carries `OWASP-LLM-02`/`OWASP-LLM-01`, the gate returns NO-GO
(`policy:1.0`, new critical + pass-rate floor), the regulated pack writes a
signed manifest over 3 artifacts, and `--verify` reports **OK** (exit 0) while
a one-byte edit to `report.md` flips it to **INVALID** (exit 1).

```
python -m pytest tests/test_evidence.py -q   # 20 passed
python -m pytest -q                           # 173 passed
```
