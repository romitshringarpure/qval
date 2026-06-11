# Qval Feature Tracker — Open-Source Core

**Internal planning doc. Gitignored. Do not push to GitHub.**

> ⚠️ **Status correction (2026-06-10):** this file claimed F-06–F-13 shipped on 2026-06-06, including fabricated artifacts (`qval/passport/*`, `qval review`, `tests/test_passport.py`) that do not exist in the repo. Verified shipped surface (commit `1462179`): **F-01–F-05 + OBS-01 only.** Statuses below corrected. Current strategy + build order: `feature_updated.html` (supersedes this file's positioning).

**Tier:** Open-source / free forever.
**Companion files:** [FEATURES.md](FEATURES.md) (chronological master) · [FEATURES-ENTERPRISE.md](FEATURES-ENTERPRISE.md) (paid product).

---

## Why these are free

Principle: **the release artifact and its verifier are free, forever.** A verifier nobody can audit is worthless — openness *is* the trust. We give away everything that produces and proves a Release Passport. We charge for collaboration, hosting, and multi-team governance (see the enterprise file).

The OSS core must be independently useful: a single engineer can install qval, import their Promptfoo results, gate a release, create a signed Passport, and let anyone verify it — with **zero paid dependency**.

**OSS / paid boundary:** generation + verification = OSS. Collaboration + review + history + hosting = paid.

---

## Status legend

`done` · `in-progress` · `planned` · `deferred`

---

## ★ Hero — current focus (the "why qval exists" demo)

> F-13 is the flagship. It bundles both commands: `qval passport create` + `qval verify`.

### F-13 · AI Release Passport (`qval passport create` + `qval verify`)
**Status:** `planned` (previously misrecorded as done — no `qval/passport/`, no passport/verify commands, no passport tests in the repo; the old "Shipped:" line here described code that was never written) · **Depends on:** F-04, F-05, F-08

`qval passport create` seals decision + evidence into a signed, content-addressed credential: a one-page record (decision GO/NO-GO, test counts, top risks, governance mapping, approver) as static self-contained HTML + machine-readable `passport.json`. `qval verify` re-hashes the artifacts and checks a detached **Ed25519** signature against a **published public key** — `✓ VERIFIED` summary / `✗ TAMPERED` (names the failing artifact, non-zero exit). Works with only the passport + public key: offline, no qval-internal trust.

- **Why OSS (non-negotiable):** the artifact must travel freely AND verification can't sit behind a paywall, or the trust claim dies. This is the credibility of the entire product.
- **Trustless bar:** detached signature + published key + deterministic re-hash. A self-hash check (we own both ends) is **not** acceptable as the hero. Hosted append-only registry is the enterprise upgrade — see F-14 (enterprise file).
- **The demo:** `verify good.passport` → ✓. Edit one byte → `verify` → ✗ TAMPERED. 10 seconds. The iPod moment.
- **Lineage:** F-08 (signed evidence packs) pulled to the front and reframed as the product identity — upgraded from a self-attested HMAC bundle to trustless asymmetric verification. F-08's manifest/redaction/encryption mechanics become the storage layer beneath the Passport.
- **Authority guardrail:** qval prints the passport; the customer's approver authorizes it. Output must never read as a safety certification issued by qval.

---

## Foundation — `done`

- **F-01 · Canonical evidence schema** — shared data model; every downstream feature depends on it.
- **F-02 · CLI foundation** (`qval init / doctor / run`) — install + first-run experience.
- **F-03 · Promptfoo importer** — ride Promptfoo's distribution; zero switching cost.
- **F-04 · Baseline diff + `qval gate`** — GO / CONDITIONAL-GO / NO-GO decision.
- **F-05 · HTML/Markdown release report** — shareable output beyond the CLI.

## Governance core — `planned` (OSS) — corrected from `done`

- **F-06 · Policy-as-code engine** — `planned` (policy.yaml is an unparsed template; `GateThresholds` is the interim mechanism). release thresholds as version-controlled YAML. *OSS on purpose: deliver as free YAML what Credo AI charges SaaS for.*
- **F-07 · Control & compliance mapping** — `planned` (only `Finding.control_ids` exists in the schema). Full OWASP LLM Top 10 2025, NIST AI RMF trustworthiness characteristics, EU AI Act evidence areas, ISO/IEC 42001 scaffold, and custom internal policies with per-case/per-finding overrides. *OSS: the mapping is a public good; the hosted dashboard is paid.*
- **F-08 · Signed evidence pack** — `planned` (`EvidencePack` dataclass in schema only; no export/signing code). SHA-256 manifest + detached signature + redaction modes. The engine under F-13/F-14/F-15. *OSS: see F-15 rationale.*
- **F-10 · Manual review workflow (CLI)** — `planned` (no `qval review` code; `Reviewer`/`Waiver` schema objects exist; U-01 Phase B in `feature_updated.html` builds the primitives). *OSS: single-user CLI. Multi-user reviewer UI + sign-off stays paid (enterprise file).*

## Eval expansion — `planned` (corrected from done) · F-16 `deferred` (OSS)

- **F-09 · DeepEval importer** — `planned` (only `PromptfooImporter` registered). second eval-tool on-ramp, different user base.
- **F-11 · Generic HTTP/API target adapter** — `planned` (no HTTP target code; D-01 in `feature_updated.html` seeds the minimal client). eval any internal AI service, not just model APIs.
- **F-12 · Judge assist for borderline cases** — `planned` (no judge code). LLM pre-triage of `needs_review`; human always final.
- **F-16 · Multi-turn & multimodal** — `deferred`. conversation- and image-level test cases.

*Eval-expansion features stay OSS — they are CLI capabilities. Paid value is collaboration / governance-at-scale, never eval reach.*

---

## What the OSS core must NOT do

Don't reimplement an eval / red-team engine (Promptfoo, Giskard) or an org-wide GRC / AI inventory (OneTrust). qval **imports** their output and **hands off** — never competes. Keep the OSS core to: `import → gate → passport → verify`, plus policy + mapping.
