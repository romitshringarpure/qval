# Qval Feature Tracker — Enterprise / Paid

**Internal planning doc. Gitignored. Do not push to GitHub.**

> ⚠️ **Status correction (2026-06-10):** OSS-side claims referenced here (F-10 CLI "done", shipped passports) were wrong — verified shipped surface is F-01–F-05 + OBS-01 only (commit `1462179`). See corrected `FEATURES.md` / `FEATURES-OSS.md`; strategy superseded by `feature_updated.html`.

**Tier:** Commercial — hosted "Evidence Room" + multi-team governance.
**Companion files:** [FEATURES.md](FEATURES.md) (chronological master) · [FEATURES-OSS.md](FEATURES-OSS.md) (free core).

---

## Monetization principle

**Charge for collaboration, hosting, and multi-team governance — never for the artifact or its verification.** OSS produces and proves a Passport for one engineer. Enterprise is what a *team* needs: shared state, review workflow, history, access control, retention, integrations, support.

**Do not build before OSS PMF.** No hosted product until the OSS core shows traction (stars, real adopters, repeat passport creation). Building the Evidence Room early = burning runway on a SaaS nobody asked for yet.

**Pricing hypothesis:** per-team or per-seat for the hosted Evidence Room; self-host license for regulated buyers who can't use SaaS. Motion: land via the OSS engineer → expand to the governance / compliance team.

---

## Status legend

`done` · `in-progress` · `planned` · `deferred`

---

## Features

### F-15 · Hosted Evidence Room
**Status:** `deferred` (P3) · *was old-scheme F-14 "Hosted collaboration (SaaS)", reframed + expanded.*

The web home where passports live and teams act on them:

- Reviewer workflow UI + sign-off (the paid form of F-10)
- Release history & trend (pass-rate / critical findings release-over-release; diff any two passports)
- RBAC + SSO (SAML / OIDC)
- Retention policy + audit trail
- Jira / ServiceNow integration (push GO/NO-GO + evidence link into the release ticket)
- Self-hosted deployment (licensed) for regulated buyers
- Enterprise support / SLA

**Why paid:** shared state + access control + hosting + support is what teams pay for and won't build themselves. Network effect: more reviews → more evidence → more audit-readiness → harder to rip out.

### F-14 · Public transparency log
**Status:** `deferred` (the moat).

Hosted append-only registry where passports are published. Verification (F-15) then doesn't even need the issuer — even *we* can't backdate or quietly re-issue. Certificate-Transparency / Sigstore-Rekor for AI releases.

**Why paid + why a moat:** the hosted log is infrastructure only we run; it makes qval the system of record for verifiable AI releases. OSS `qval verify` works standalone; the log is the trust-at-scale upgrade.

### F-10 · Manual review workflow (collaborative)
**Status:** `deferred` (paid surface) · CLI primitive **`planned`** in OSS (corrected — no `qval review` code exists; U-01 Phase B in `feature_updated.html` builds it) · **Depends on:** F-06.

Multi-user, audit-trailed review: sorted queue by severity, owner assignment, reviewer notes, approve / reject / waive, side-by-side baseline vs current, decision-packet export.

**Tier note:** the single-user CLI is planned OSS (`qval review` queue/assign/decide/export, JSON+CSV packet — not yet built). The **collaborative, audit-trailed, multi-user** workflow (shared queue, RBAC, sign-off) is the still-deferred paid Evidence Room surface.

---

## Enterprise capability map (OSS vs paid)

| Capability | Tier |
|---|---|
| Exportable evidence packs | OSS (F-08) |
| API access | OSS core + paid hosted API |
| Self-hosted deployment | Paid (licensed) |
| Audit trail | Paid (F-15) |
| Retention policy | Paid (F-15) |
| RBAC | Paid (F-15) |
| SSO (SAML / OIDC) | Paid (F-15) |
| Jira / ServiceNow | Paid (F-15) |
| Reviewer workflow (multi-user) | Paid (F-15 / F-10) |
| Transparency log (hosted) | Paid (F-14) |
| Enterprise support / SLA | Paid |

---

## Build sequence (only after OSS PMF)

1. Exportable packs + API — make the artifact useful (partly OSS already).
2. Self-host + audit trail + retention — the regulated-buyer unlock.
3. RBAC + SSO — multi-team.
4. Jira / ServiceNow — workflow fit.
5. Transparency log — the moat.
