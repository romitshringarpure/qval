# F-01 · Canonical Evidence Schema — Internal Change Record

**Status:** ✅ Done
**Date:** 2026-06-04
**Sprint:** 1
**Author:** Qval core

---

## 1. What this feature is

A second, tool-agnostic data model that sits *above* the existing native run
schema. Native Qval runs, Promptfoo imports, and DeepEval imports all normalize
INTO this one shape. It is the common contract for the governance layer:
gate (F-04), reports (F-05), policy (F-06), control mapping (F-07), and evidence
packs (F-08) all read/write canonical objects regardless of which eval tool
produced the results.

**One-line:** the canonical schema makes Qval a platform above eval tools rather
than a collection of tool-specific scripts.

---

## 2. Why we built it first

Everything in the roadmap depends on a stable cross-tool data model:

```
Native run ─┐
Promptfoo  ─┼──► [CANONICAL SCHEMA] ──► gate ──► report ──► evidence pack
DeepEval   ─┘        (F-01)            F-04     F-05         F-08
```

The native schema (`src/engine/schemas.py`) assumes *Qval ran the test* — it
carries `detectors`, `scoring_type`, native `risk_level`. Promptfoo and DeepEval
results do not have those fields. Forcing imported data into the native
`TestResult` would bend the model and lose fidelity. Build the canonical model
wrong → rework every downstream feature. Build it right → features snap in.

---

## 3. What changed (files)

| File | Change | Lines |
|------|--------|-------|
| `src/canonical/__init__.py` | **New.** Public API surface — re-exports objects, vocab constants, mappers. | ~55 |
| `src/canonical/schema.py` | **New.** 9 canonical objects, 3 vocabularies, version check, native→canonical mappers. | ~360 |
| `src/canonical/adapter.py` | **New.** Converts native `RunSummary` + `TestResult[]` → `CanonicalRun`. | ~140 |
| `tests/test_canonical_schema.py` | **New.** 12 tests: vocab mapping, validation, JSON roundtrip, version gate, adapter. | ~215 |
| `docs/FEATURES.md` | F-01 status `planned` → `done`. | — |

**Nothing in existing code was modified.** Native pipeline untouched. The
adapter is additive — the runner still produces `TestResult`; translation to
canonical happens on demand.

---

## 4. Technical design

### 4.1 Objects (9)

Top object `CanonicalRun` holds the rest:

| Object | Role | Populated by |
|--------|------|--------------|
| `CanonicalRun` | One eval execution, top-level, serialized to `run.json` | F-01 (now) |
| `Case` | Input side of a test (prompt, expected behavior) | F-01 / importers |
| `Finding` | Result side (status, severity, score, reason) | F-01 / importers |
| `Control` | Governance control (OWASP-LLM-01 etc.) | F-07 |
| `Artifact` | Stored evidence file + sha256 | F-08 |
| `Decision` | GO / CONDITIONAL-GO / NO-GO verdict | F-04 |
| `Waiver` | Approved exception | F-06 / F-10 |
| `Reviewer` | Human review decision | F-10 |
| `EvidencePack` | Signed audit-bundle metadata | F-08 |

Future-feature objects are **defined now, lightly populated**. They are part of
the v1.0 contract so later features attach data without a schema migration or a
rewrite of runs already written to disk.

### 4.2 Vocabularies

- **Severity:** `critical / high / medium / low / info`. Adds `info` over the
  native 4 levels — a non-alarming bucket for tools whose results aren't
  risk-graded. `SEVERITY_RANK` (worst→best) supports severity-regression diffing
  in F-04.
- **Status:** `passed / failed / needs_review / waived / approved / blocked`.
  Superset of native `PASS/FAIL/NEEDS_REVIEW`, adding the governance states the
  gate (F-04) and review workflow (F-10) introduce.
- **Decision:** `GO / CONDITIONAL-GO / NO-GO`.

### 4.3 Native → canonical mapping

| Native | Canonical |
|--------|-----------|
| `PASS` | `passed` |
| `FAIL` | `failed` |
| `NEEDS_REVIEW` | `needs_review` |
| `risk_level: critical/high/medium/low` | same severity strings |

Mappers (`map_native_status`, `map_native_severity`) **raise `ValueError` on
unknown input** rather than guessing — a silent mismap would corrupt every
downstream gate decision.

### 4.4 No-data-loss guarantee

The adapter preserves everything native carries:
- Native run aggregates (`pass_rate`, `by_category`, latency percentiles, cost)
  → `CanonicalRun.metadata`.
- Per-finding detail (detector results, latency, tokens, cost, errors, paired
  response) → `Finding.extra`.
- Paired prompt → `Case.extra`.

Nothing in a native run is dropped in translation.

### 4.5 Versioning

`SCHEMA_VERSION = "1.0"` stamped on every `CanonicalRun`. `from_dict` checks the
**major** component on load and refuses an incompatible major (e.g. `2.0`) with
a clear error. Minor bumps (`1.5`) load fine. This lets importers and consumers
detect mismatches instead of failing silently on a changed shape.

### 4.6 Implementation choices

- **stdlib dataclasses + manual `to_dict`/`from_dict`.** Matches existing
  `schemas.py` style. Zero new dependencies.
- **New module + adapter pattern.** Canonical lives in `src/canonical/`, native
  in `src/engine/`. Governance concerns stay separate from native-run concerns.
- **Validation in `__post_init__`** on `Finding` and `Decision` — invalid
  status/severity/verdict raise at construction, not at use.

---

## 5. Tests

`tests/test_canonical_schema.py` — 12 tests:

- Vocab mappers translate known values; raise on unknown.
- `Finding`/`Decision` reject invalid status/severity/verdict at construction.
- `CanonicalRun` survives JSON round-trip (nested objects intact).
- `from_dict` rejects incompatible major version; accepts minor bump.
- Adapter builds canonical run from native; preserves aggregates in metadata;
  adapter output survives JSON round-trip with `extra` detail intact.

**Result:** 12 new pass. Full suite **48 pass**, no regressions.

```
python -m pytest tests/test_canonical_schema.py -q   # 12 passed
python -m pytest -q                                   # 48 passed
```

---

## 6. What this unblocks

- **F-03 Promptfoo importer** — emits `CanonicalRun` directly (target shape ready).
- **F-04 gate** — diffs `Finding`s, writes `Decision` (objects ready).
- **F-05 report** — renders from `CanonicalRun` (one input shape).
- **F-07 control mapping** — populates `Control` + `Finding.control_ids` (fields ready).
- **F-08 evidence pack** — populates `Artifact` + `EvidencePack` (fields ready).

---

## 7. Follow-ups / known gaps

- No CLI surface yet — canonical is library-only until **F-02** adds
  `qval` commands and `pip install`.
- No `run.json` read/write helper module yet (importers/gate will add a thin
  `load_canonical` / `save_canonical` in F-03/F-04, or extract one then).
- `EvidencePack.retention_ttl_days` and signing fields are placeholders; real
  logic lands in F-08.
- Native adapter is one-directional (native → canonical). No canonical → native
  path; none needed (consumers read canonical).
