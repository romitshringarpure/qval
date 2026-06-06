# F-04 · Baseline Diff and `qval gate` — Change Record

**Status:** 🚧 In progress (design approved)
**Date:** 2026-06-05
**Sprint:** 3
**Depends on:** F-01 (canonical schema), F-03 (canonical `run.json` to diff)

---

## 1. What this is

`qval gate` turns two canonical runs into a release decision. It diffs a
**current** run against a **baseline** run and emits **GO / CONDITIONAL-GO /
NO-GO** — the decision artifact a release manager or compliance team signs off
on. This is the step that makes Qval a *decision system*, not just a report
generator: single-run pass/fail is table stakes; *"is this worse than last
time?"* is the release question.

```bash
qval gate --current latest.json --baseline baseline.json
```
```
DECISION: NO-GO
  - 2 new critical findings
  - privacy pass-rate 94% -> 87% (floor: 90%)
  - 1 finding requires human review
```

The `Decision` object already exists in the F-01 schema (unpopulated). F-04
fills it.

---

## 2. Architecture — shared pure engine

A `qval/gate/` package with two **pure** modules that both `qval gate` and the
F-05 report import, so the diff/verdict logic lives in exactly one place.

```
qval/gate/diff.py       diff_runs(baseline | None, current) -> RunDiff
qval/gate/decision.py   GateThresholds + evaluate(diff, thresholds) -> Decision
qval/commands/gate_cmd.py   CLI (load -> diff -> evaluate -> print/persist)
```

### 2.1 The F-06 seam

`GateThresholds` is built-in defaults today. Later **F-06 policy-as-code**
constructs it from `policy.yaml` — no rework, F-06 swaps the *input*, not the
engine. `Decision.policy_version` is stamped `"builtin-v1"` so a reader knows
the verdict came from built-in rules, not a policy file.

---

## 3. Diff (`RunDiff`)

An ephemeral dataclass (derived, not persisted). Findings are paired by
**`case_id`**. With no baseline, the baseline is treated as empty — every
current failure counts as "new" (first-release gating works out of the box).

| Field | Meaning |
|-------|---------|
| `new_failures` | failed in current; absent or not-failing in baseline |
| `severity_regressions` | same case, status pass→fail or severity rank worse |
| `improvements` | failed in baseline, passing in current |
| `category_regressions` | per-`Case.category` pass-rate drop |
| `pass_rate_baseline / current / delta` | run-level pass rate (passed / total findings) |
| `needs_review` | current findings with `status == needs_review` |

Pass rate of an empty run is defined as `1.0` (nothing failing).

---

## 4. Decision rules (`GateThresholds` defaults)

| Trigger | Verdict |
|---------|---------|
| new failure at `critical` / `high` vs baseline | **NO-GO** |
| any `critical` failure in current (new or not — *critical floor*) | **NO-GO** |
| current pass-rate below `min_pass_rate` (opt-in via `--min-pass-rate`) | **NO-GO** |
| new `medium` / `low` failures, or any `needs_review` | **CONDITIONAL-GO** |
| none of the above | **GO** |

`Decision.rationale` is a list of human-readable strings naming each trigger.
Defaults: `block_new_severities={critical, high}`, `critical_floor=True`,
`min_pass_rate=None`. Overridable per-run via `--block-severity` and
`--min-pass-rate`.

---

## 5. CLI & exit codes

```bash
qval gate --current run.json [--baseline base.json] [--out gated.json] \
          [--min-pass-rate 0.9] [--block-severity critical,high]
```

- Prints the `DECISION:` block to stdout (verdict + rationale).
- `--out` writes the current run with `.decision` attached (consumed by F-05).
- **Exit codes:** GO / CONDITIONAL-GO → `0`; **NO-GO → `1`** (CI gate);
  input/usage error → `2`.

`load_canonical` raises `ValueError` on a missing / malformed / schema-mismatch
file; the CLI catches it, prints a friendly message, exits `2`.

---

## 6. Files

| File | Change |
|------|--------|
| `qval/gate/__init__.py` | **New.** Package surface (RunDiff, diff_runs, GateThresholds, evaluate). |
| `qval/gate/diff.py` | **New.** `RunDiff` + `diff_runs`. |
| `qval/gate/decision.py` | **New.** `GateThresholds` + `evaluate`. |
| `qval/commands/gate_cmd.py` | **New.** `qval gate` handler. |
| `qval/cli.py` | Wire `gate_cmd.add_parser`. |
| `qval/commands/stubs.py` | Drop `"gate"` (only `report` remains, until F-05). |
| `tests/test_gate.py` | **New.** ~14 tests. |

---

## 7. Tests (TDD)

Diff: new failure, improvement, severity regression (medium→critical), status
regression (pass→fail), no-baseline = all-new, pass-rate delta, category
regression, identical runs → empty. Decision: GO clean, NO-GO new critical,
NO-GO critical-floor (pre-existing), NO-GO below min-pass-rate, CONDITIONAL on
new medium, CONDITIONAL on needs_review, flag overrides. CLI: prints DECISION,
NO-GO exit 1, GO exit 0, `--out` persists the decision, bad path exit 2.

---

## 8. Scope cuts (YAGNI)

No policy-as-code (F-06 — `GateThresholds` is the seam), no control population
(F-07 — control regressions render when `control_ids` exist, empty until then),
no waiver/reviewer logic (F-10), no trend charts.
