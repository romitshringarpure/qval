# F-09 · DeepEval Importer — Change Record

**Status:** ✅ Done
**Date:** 2026-06-05
**Sprint:** 6
**Depends on:** F-01 (canonical schema), F-03 (importer seam)

---

## 1. What this is

`qval import deepeval <results.json>` normalizes a DeepEval evaluation into the
same `CanonicalRun` the gate, report, control mapping, and evidence pack already
consume. DeepEval has strong traction in ML/research orgs — a different user
base than Promptfoo — so this doubles the "works with your existing tools"
addressable audience without a single change downstream.

```bash
qval import deepeval results.json
qval import deepeval ./run_dir/        # dir containing results.json
```

The F-03 importer seam was built for exactly this: a new tool is one module that
self-registers; the CLI and every consumer stay tool-agnostic.

---

## 2. Architecture — one module, zero CLI edits

```
qval/importers/deepeval.py     DeepEvalImporter(BaseImporter) + register()
qval/importers/__init__.py     import the module so it self-registers
```

`DeepEvalImporter` subclasses `BaseImporter`, implements `to_canonical`, and
calls `register()`. `available_tools()` now returns `["deepeval", "promptfoo"]`,
so `qval import deepeval …` works with no edit to `import_cmd.py`.

---

## 3. Mapping DeepEval → canonical

DeepEval grades each test case with one or more **metrics** (Hallucination,
Bias, Faithfulness …), each carrying a 0–1 score, threshold, pass/fail, and a
judge `reason`. It assigns no risk severity.

| DeepEval | Canonical |
|----------|-----------|
| `input` | `Case.prompt` |
| `expectedOutput` / `expected_output` | `Case.expected_behavior` |
| `actualOutput` / `actual_output` | `Finding.response` |
| `name` | `Case.name` / id |
| case `success`, else all metrics pass | `Finding.status` (passed/failed) |
| driving metric `score` | `Finding.score` |
| failing metric `reason`(s), joined | `Finding.reason` |
| (no severity) | `default_severity` (info), or case `metadata.severity` |
| full `metricsData` | `Finding.extra["metrics"]` |

**Driving metric** = the first *failing* metric (it explains the verdict), else
the first metric. Status precedence: explicit case `success` wins; absent, all
metrics must pass; an empty metric set with no verdict is treated as passing
(nothing failed). Severity uses the F-03 `resolve_severity` posture — explicit
record value → `--default-severity` → `info`, validated (no silent mismap).

---

## 4. Tolerant parsing

DeepEval's serialized shape varies by version and export path, so the parser is
lenient like the Promptfoo one:

- **Records:** a top-level list, or `testCases` / `test_cases` /
  `testResults` / `test_results`.
- **Metrics:** `metricsData` / `metrics_data` / `metrics`.
- **Aliases:** snake_case and camelCase accepted for input/output/expected.

An unlocatable test-case array raises `ValueError` → friendly CLI error, exit 1.

---

## 5. Files

| File | Change |
|------|--------|
| `qval/importers/deepeval.py` | **New.** `DeepEvalImporter` + registration. |
| `qval/importers/__init__.py` | Import `deepeval` so it self-registers. |
| `tests/test_import_deepeval.py` | **New.** 19 tests. |

No CLI, gate, report, or schema changes — the seam carried it.

---

## 6. Tests (TDD)

Registry: deepeval registered + discoverable. Locating: top-level list,
`testCases`, snake `test_results`. Mapping: case fields, snake/camel aliases.
Status: explicit fail, derived-from-metrics (any fail → failed, all pass →
passed), empty metrics default passed. Score/reason: failing metric drives
score + reason, metrics preserved in extra. Severity: default info, override
flag, metadata wins. Run metadata: model + suite from data, suite falls back to
source stem. CLI: import file (passed/failed counts), import dir, bad path
exit 1.

---

## 7. Scope cuts (YAGNI)

Category stays `imported` (same as the Promptfoo importer — no guessing a Qval
category from a DeepEval metric name; an unmapped category surfaces as a control
*gap* in F-07, never a false pass). No model-under-test inference from the judge
`evaluationModel` (that's the grader, not the target). No multi-file merge, no
DeepEval-specific assertion rendering.

---

## 8. Result

`tests/test_import_deepeval.py` — **19 tests**. **Full suite: 192 pass**, no
regressions (+19). End-to-end confirmed: `qval import deepeval results.json`
maps a mixed pass/fail DeepEval run (metric-driven verdicts) into a canonical
`run.json` that `qval gate` / `report` / `map` / `pack` consume unchanged.

```
python -m pytest tests/test_import_deepeval.py -q   # 19 passed
python -m pytest -q                                  # 192 passed
```
