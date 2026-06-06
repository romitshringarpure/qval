# F-13 · AI Release Passport — Change Record

**Status:** ✅ Done
**Date:** 2026-06-06
**Sprint:** 8
**Productizes:** F-08 (evidence pack) — asymmetric, externally verifiable signing
**Depends on:** F-01 (canonical), F-04 (decision), F-05 (report), F-07 (controls), F-08 (artifact hashing), F-10 (approver)

---

## 1. What this is

`qval passport create` seals a canonical run's decision + evidence into a
signed, content-addressed credential; `qval verify` independently checks it.
Verification does **not** require trusting qval or the issuer: an outside
auditor re-hashes the artifacts and checks a detached **Ed25519** signature
against the issuer's **published** public key.

```bash
qval passport keygen --out issuer_key          # publish issuer_key.pub
qval passport create --from run.json --approver "Jane Doe" --key issuer_key
qval verify passport_run_x --pubkey issuer_key.pub
# ✓ VERIFIED — evidence unaltered (trustless) · NO-GO · approver Jane Doe
```

This upgrades F-08's signing from a shared-secret **HMAC** (proves only that the
secret-holder signed it — useless to an outsider) to **asymmetric** signing
(anyone verifies with the public key; only the private-key holder can sign).

---

## 2. Trust model

```
artifact bytes ── sha256 ──► manifest entry           (content-addressed)
manifest + claims = passport "core"
canonical(core) ── Ed25519.sign(PRIVATE) ──► detached signature
PUBLIC key ── published out-of-band ──► auditor pins it
```

The **signed payload is `core`**, which *contains* the artifact manifest and the
human-facing claims (system, decision, approver, summary, governance). So:

- editing an **artifact** → its sha256 no longer matches the manifest → caught;
- editing a **claim** (e.g. `approver`) → `canonical(core)` changes → signature
  fails → caught;
- forging with **another key** → fails against the published/pinned key, and the
  issuer **fingerprint** the auditor pinned no longer matches.

### Key pinning

- `verify --pubkey <published.pem>` → **trustless** (auditor's pinned key).
- no `--pubkey` → uses the embedded key but **warns** and prints the issuer
  fingerprint to pin. Embedded-only is convenience, never the trust root.
- `verify --fingerprint <hex>` → assert the issuer fingerprint explicitly.

`verify` also fails if the verifying key's fingerprint ≠ the `core.issuer`
fingerprint the passport advertises (signed-by-a-different-key detection).

---

## 3. Guardrail — integrity ≠ safety

Every passport and `verify` output carries:

> This passport verifies integrity, provenance, and the named approver — not
> that the AI system is safe. The release was authorized by the approver, not by
> qval. qval is the instrument, not the certifier.

No output reads as a qval-issued safety certification. The verdict and approver
are the customer's; qval records and seals them.

---

## 4. Bundle layout

```
passport_<run_id>/
  passport.json   # core (signed payload) + signature + embedded public key + disclaimer
  run.json        # canonical run (artifact, hashed)
  report.md       # human report (artifact, hashed)
  report.html     # human report (artifact, hashed)
  issuer.pub      # convenience copy of the public key (trust comes from the pinned copy)
```

`core` = `passport_id`, `issued_at`, `system{name,version,model,provider}`,
`decision{verdict,approver,policy_version}`, `summary{tests,passed,failed,
needs_review,critical_failures,pass_rate}`, `governance[{control_id,framework,
status}]`, `manifest{algo,artifacts[]}`, `issuer{algo,fingerprint}`. Approver is
`--approver` or the most-recent F-10 `approve` reviewer; absent → error.

---

## 5. CLI & exit codes

```bash
qval passport keygen --out KEY [--force]
qval passport create --from run.json --approver WHO [--system S --version V] [--key KEY] [--out DIR]
qval passport show <passport_dir>
qval verify <passport_dir> [--pubkey PEM] [--fingerprint HEX]
```

Signing key: `--key` or `$QVAL_PASSPORT_KEY` (private PEM path). Verify OK → `0`;
**TAMPERED / bad signature / fingerprint mismatch / usage error → `2`** (CI can
gate on release integrity).

---

## 6. Files

| File | Change |
|------|--------|
| `qval/passport/signing.py` | **New.** Ed25519 keygen/sign/verify/fingerprint, PEM I/O (`cryptography`). |
| `qval/passport/manifest.py` | **New.** sha256 manifest + canonical serialization (shared by build/verify). |
| `qval/passport/passport.py` | **New.** `assemble_core`, `build_passport`, `load_passport`. |
| `qval/passport/verify.py` | **New.** `verify_passport` → integrity + provenance + summary. |
| `qval/commands/passport_cmd.py` | **New.** `qval passport keygen/create/show`. |
| `qval/commands/verify_cmd.py` | **New.** `qval verify`. |
| `qval/cli.py` | Wire `passport` + `verify`. |
| `requirements.txt`, `pyproject.toml` | Add `cryptography>=41.0`. |
| `tests/test_passport.py` | **New.** 22 tests. |

---

## 7. Tests (TDD)

Signing: sign/verify roundtrip, altered data fails, wrong key fails, fingerprint
stable + keyed. Manifest: canonical bytes order-independent, hashes + sorts.
Assembly: requires approver, derives approver from review, summary +
critical-failure count + governance from controls. Build/verify: bundle written,
good passport verifies (pinned), no-key warns but ok. Tamper/forgery: artifact
byte → fails naming the artifact, core claim → signature fails, wrong pubkey
fails, fingerprint pin match/mismatch, missing bundle. CLI demo: keygen,
create→verify good (VERIFIED + guardrail), tamper one byte → TAMPERED exit 2,
create requires approver / key.

---

## 8. Scope cuts (YAGNI / deferred)

Deferred to a later tier: an append-only transparency log (Sigstore/Rekor-style)
so even the issuer can't backdate; keyless/OIDC identity signing; RFC-3161
timestamping. The published-key model defeats outside forgery; those additions
bind the issuer itself. Also out of scope: PDF passport, revocation lists,
multi-signer/threshold signatures, PKI/CA chains (a published Ed25519 key is the
MVP trust anchor). `pack` (F-08) is retained as the internal evidence archive.

---

## 9. Result

`tests/test_passport.py` — **22 tests**. **Full suite: 275 pass**, no
regressions. End-to-end demo: `passport create` from a NO-GO run (1 critical
failure, privacy→OWASP-LLM-02 mapped) writes a signed bundle; `verify --pubkey`
prints **✓ VERIFIED … evidence unaltered** with the guardrail; flipping one byte
of `report.md` yields **✗ TAMPERED: artifact 'report.md' hash mismatch**, exit 2.

```
python -m pytest tests/test_passport.py -q   # 22 passed
python -m pytest -q                           # 275 passed
```
