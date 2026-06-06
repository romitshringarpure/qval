# F-06 · Policy-as-Code — Change Record

**Status:** ✅ Done
**Date:** 2026-06-05
**Sprint:** 4
**Depends on:** F-04 (gate engine + `GateThresholds` seam)

---

## 1. What this is

A release team versions its gate rules as a `policy.yaml` in git — reviewed,
diffable, audited — instead of hard-coding thresholds or remembering CLI flags.
`qval gate` reads that file and gates against it; the verdict records *which*
policy produced it.

```bash
qval gate --current latest.json --baseline baseline.json --policy policy.yaml
```
```
DECISION: NO-GO
  - 1 new high finding(s) vs baseline
```
`Decision.policy_version` is stamped `policy:1.0` (or a content hash) so a
reader can tell the verdict came from a policy file, not the built-in rules.

---

## 2. Architecture — fill the F-04 seam, don't reshape it

F-04 deliberately wrote the decision engine against `GateThresholds` as the
policy seam. F-06 fills it: a loader turns `policy.yaml` into a `GateThresholds`
plus a provenance stamp. **The engine is unchanged** except for one new,
opt-in rule (`require_review`); everything else is input construction.

```
qval/gate/policy.py     load_policy(path) -> LoadedPolicy(thresholds, version)
                        discover_policy(start) -> Path | None
qval/gate/decision.py   + require_review_severities; evaluate(..., policy_version=)
qval/commands/gate_cmd.py  --policy / --no-policy; flag-over-policy precedence
```

---

## 3. Policy schema

All keys optional; omission falls back to the built-in default, so a partial
policy is valid. The loader is **strict about shape** (wrong types raise
`PolicyError`) and **lenient about omission**.

```yaml
version: "1.0"               # -> Decision.policy_version = "policy:1.0"
release_policy:
  block_on:                  # NEW failures at these severities -> NO-GO
    - severity: critical
    - severity: high
  critical_floor: true       # any current critical failure -> NO-GO
  pass_rate_floor: 0.90       # current pass-rate below this -> NO-GO
  require_review:            # failures here -> CONDITIONAL-GO (sign-off)
    - severity: medium
```

| Policy key | `GateThresholds` field |
|------------|------------------------|
| `block_on[].severity` | `block_new_severities` |
| `critical_floor` | `critical_floor` |
| `pass_rate_floor` | `min_pass_rate` |
| `require_review[].severity` | `require_review_severities` *(new)* |

An **empty list** is meaningful (e.g. `block_on: []` disables new-failure
blocking) and distinct from an absent key (keeps the default).

### 3.1 `require_review` — the one new rule

A failure at a `require_review` severity never blocks but forces
**CONDITIONAL-GO** so a human signs off. It is suppressed for findings already
named as new failures (no double-counting) and is independent of the
finding-level `needs_review` status that F-04 already handled.

---

## 4. Provenance stamp

`Decision.policy_version` answers "what rules produced this verdict?":

- built-in rules → `builtin-v1` (unchanged from F-04)
- policy with a `version:` → `policy:<version>`
- policy without one → `policy:sha256:<8-hex>` of the file contents

The hash fallback means an unversioned policy still produces a stable,
tamper-evident identifier.

---

## 5. Resolution & precedence

```
built-in defaults  <  policy file  <  explicit CLI flags
```

- Policy source: `--policy PATH` (explicit), else **auto-discovery** of a
  `policy.yaml`/`policy.yml` at or above the cwd (walks up like project-config
  discovery), unless `--no-policy` forces built-in rules.
- `--block-severity` / `--min-pass-rate` override the policy per-run (urgent
  hotfix without editing the file).
- `PolicyError` (missing/malformed/unknown severity/out-of-range floor) →
  friendly message, **exit 2** (same class as a bad run path).

---

## 6. Files

| File | Change |
|------|--------|
| `qval/gate/policy.py` | **New.** `load_policy`, `discover_policy`, `LoadedPolicy`, `PolicyError`. |
| `qval/gate/decision.py` | `require_review_severities` on `GateThresholds`; `evaluate(..., policy_version=)`; require_review → CONDITIONAL. |
| `qval/gate/__init__.py` | Export the policy surface. |
| `qval/commands/gate_cmd.py` | `--policy` / `--no-policy`; `_resolve_policy` (precedence). |
| `qval/templates/policy.yaml` | Refreshed to the live schema (`version`, `critical_floor`, comments). |
| `tests/test_policy.py` | **New.** 17 tests. |

---

## 7. Tests (TDD)

Loader: full map of all fields, partial keeps defaults, empty file = defaults +
hash stamp, version → stamp, content-hash fallback, unknown severity rejected,
non-mapping rejected, out-of-range floor rejected, missing file raises, empty
`block_on` disables blocking. Discovery: finds upward, None when absent.
Engine: require_review forces CONDITIONAL, policy_version stamped. CLI: policy
blocks + stamps version, flag overrides policy, `--no-policy` uses built-in,
bad policy exit 2.

---

## 8. Scope cuts (YAGNI)

No waivers (the `Waiver` object + `STATUS_WAIVED` ship with the F-10 review
workflow), no per-category or per-control thresholds (F-07 lands controls
first), no policy inheritance/includes, no JSON-schema validation library
(hand-rolled shape checks keep zero install weight).

---

## 9. Result

`tests/test_policy.py` — **17 tests**. **Full suite: 139 pass**, no regressions
(+17). End-to-end confirmed: `qval gate --current cur.json --policy policy.yaml
--out gated.json` blocks a new `high` failure (NO-GO, exit 1) and writes
`decision.policy_version=policy:1.0`; `--block-severity critical` over the same
policy relaxes the same `high` to CONDITIONAL-GO; `--no-policy` ignores an
`block_on: []` file and restores built-in critical/high blocking.

```
python -m pytest tests/test_policy.py -q   # 17 passed
python -m pytest -q                         # 139 passed
```
