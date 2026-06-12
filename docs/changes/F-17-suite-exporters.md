# F-17 · Suite Exporters — Change Record

**Status:** ✅ Done
**Date:** 2026-06-11
**Sprint:** 6
**Depends on:** F-01 (canonical schema / TestCase), F-02 (CLI foundation), F-03 (importer seam, mirrored)

---

## 1. What this is

`qval export <tool> --suite <name> --out <path>` — the **reverse** of
`qval import`. Take a qval native suite (`test_cases/*.json` — the `TestCase`
shape) and render it into a **runnable config for another eval tool**
(Promptfoo, DeepEval), plus a **fidelity report** of what translated cleanly vs
degraded.

Where importers (F-03/F-09) bring an external tool's *results* into the
canonical schema for governance, exporters push qval's *authored suites* back
out so other tools can execute them. Together they make qval a **system of
record** for test intent: author once in qval, run anywhere, re-import the
results for the gate / report / evidence pack.

**One-line:** F-03 proved external results flow *in*; F-17 makes curated suites
flow *out*, and is honest (via the fidelity report) about what each target
tool can and cannot express.

---

## 2. Architecture — pluggable exporters (mirror of the importer seam)

```
qval export <tool> --suite <name> --out <path>
        │
        ▼
commands/export_cmd.py     CLI: runtime-validate tool+suite, load suite, write config + fidelity, print table
        │
        ▼
exporters/registry.py      _EXPORTERS dict · register() · get_exporter() · available_tools()
exporters/base.py          BaseExporter (ABC) · ExportResult · WrittenExport · export_to_path() template
exporters/fidelity.py      FidelityReport · FieldFidelity · render_table() / render_markdown()
exporters/promptfoo.py     PromptfooExporter(BaseExporter)  → promptfooconfig.yaml
exporters/deepeval.py      DeepEvalExporter(BaseExporter)   → standalone pytest file
        │
        ▼
<path>                     the tool's config
<path>.fidelity.md         per-field translation report (written alongside)
```

### 2.1 `BaseExporter` contract

```python
class BaseExporter(ABC):
    tool_name: str                                  # "promptfoo" / "deepeval"
    default_extension: str                          # ".yaml" / ".py"

    @abstractmethod
    def export_suite(self, cases, suite_name) -> ExportResult:
        ...                                         # pure: cases -> (text, fidelity)

    def export_to_path(self, cases, suite_name, out_path) -> WrittenExport:
        ...                                         # template: render, write config + <path>.fidelity.md
```

`export_suite` is pure (no I/O) so it is trivially testable; `export_to_path`
is the thin template that writes both artifacts. Registry is a name→instance
dict identical in shape to `importers/registry.py`, so the CLI's tool list is
derived, never hard-coded — a third exporter is one module.

---

## 3. Promptfoo mapping

Each qval case → one promptfoo **test**: `vars.input` = prompt, `description` =
`"<id> · <name>"`, plus a `metadata` block. Schema researched first and cited in
the generated file header:
- config: <https://www.promptfoo.dev/docs/configuration/reference/>
- asserts: <https://www.promptfoo.dev/docs/configuration/expected-outputs/>

| qval field | promptfoo | Fidelity |
|---|---|---|
| `prompt` | `tests[].vars.input` (template `prompts: ["{{input}}"]`) | clean |
| `expected_behavior` | `assert: [{type: llm-rubric, value: <text>}]` | clean |
| `name` / `description` | `tests[].description` | clean |
| `detectors: [refusal_detector]` | extra `assert: {type: icontains-any, value: [refusal markers]}` | approximated |
| `detectors` (no equivalent) | commented placeholder in the file header | degraded |
| `paired_prompt` | a **second** test; both share `metadata.paired_group: <id>` | clean |
| `risk_level`, `manual_review_required`, `scoring_type`, `tags` | `tests[].metadata.*` (preserved, not enforced) | degraded |

- Output is `yaml.safe_dump` (stdlib + PyYAML only). PyYAML can't carry inline
  comments, so the cited URLs, the `providers` note, and the per-case
  "unsupported detector" placeholders live in a prepended `#` header block; the
  YAML body still round-trips through `yaml.safe_load`.
- `providers` defaults to `openai:gpt-4o` (runnable out of the box; the user
  swaps in their target).
- `DETECTOR_ASSERTS` is the one extension point: add a detector→assert factory
  to give another detector a deterministic equivalent.

## 4. DeepEval mapping

Generates a **standalone pytest file** using DeepEval's `LLMTestCase` + `GEval`
pattern. Each case → a `test_<category>_<id>()`; a `paired_prompt` adds a
`_paired` test.

- `input` = prompt; `actual_output` = `model_under_test(prompt)` — a stub that
  raises `NotImplementedError`, which the user wires to their LLM.
- `expected_behavior` → a `GEval(criteria=...)` string (and the test docstring).
- `risk_level` / `manual_review_required` / `detectors` / `scoring_type` →
  docstring only (deepeval has no equivalent).
- All string literals emitted via `repr()`; docstrings flattened to one line —
  the file is **guaranteed `compile()`-able** standalone.
- qval's env never imports deepeval. The *generated* file imports it inside a
  `try` / `except ImportError` that `pytest.skip`s, so it imports cleanly with
  or without deepeval installed.

## 5. Fidelity report

`FidelityReport` records per-field translation status — `clean` /
`approximated` / `degraded` / `dropped` — with a note and affected case ids.
Printed as an aligned table after export and written to `<path>.fidelity.md`
(a markdown table). This is the feature's honesty contract: a qval suite is
richer than any single tool's config, and the user sees exactly what survived.

---

## 6. CLI & exit codes

- `tool` and `--suite` are validated at **runtime** (not argparse `choices`), so
  an unknown value prints a friendly list-the-options message and exits **1**
  (vs argparse's terse exit 2). `--suite` accepts a core suite name or `all`
  (same set as `qval run`), resolved project-aware (U-00).
- No discoverable project → exit **2** (`require_project`, like `qval run`).
- Success → exit **0**, writes `<out>` + `<out>.fidelity.md`, prints the table.

---

## 7. Files

| File | Change |
|------|--------|
| `qval/exporters/__init__.py` | **New.** Package surface — re-exports registry API + base types. |
| `qval/exporters/base.py` | **New.** `BaseExporter` ABC, `ExportResult`, `WrittenExport`, `export_to_path` template. |
| `qval/exporters/registry.py` | **New.** `register` / `get_exporter` / `available_tools`. |
| `qval/exporters/fidelity.py` | **New.** `FidelityReport` / `FieldFidelity` + table/markdown renderers. |
| `qval/exporters/promptfoo.py` | **New.** `PromptfooExporter`. |
| `qval/exporters/deepeval.py` | **New.** `DeepEvalExporter`. |
| `qval/commands/export_cmd.py` | **New.** `qval export` CLI handler, tool-agnostic dispatch. |
| `qval/cli.py` | Wire `export_cmd.add_parser`. |
| `tests/test_exporters.py` | **New.** 27 tests. |
| `README.md` | Add `qval export` row to the Commands table. |
| `docs/comparison_with_existing_tools.md` | Coexistence: import-in / export-out round trip. |

---

## 8. Tests (TDD) — `tests/test_exporters.py`

Fixture suite has one case per all seven categories plus a paired-bias case, a
`refusal_detector` case, and unsupported-detector cases. Coverage: registry
(lists both, unknown raises); promptfoo (valid YAML via `safe_load`, `vars.input`,
`llm-rubric` carries `expected_behavior`, `refusal_detector` → `icontains-any`,
non-refusal case has only `llm-rubric`, paired → two tests sharing
`paired_group`, count expands, metadata carries risk/review, header cites the
doc + names unsupported detectors); deepeval (`compile()` standalone,
LLMTestCase/GEval/model_under_test/assert_test present, expected_behavior in
criteria, paired → two tests, import guarded); fidelity (risk_level/manual_review
degraded, unsupported detectors named, paired tracked, markdown table header);
`export_to_path` writes both artifacts; CLI (promptfoo + deepeval happy paths,
`--suite all`, unknown tool → 1, unknown suite → 1).

---

## 9. Scope cuts (YAGNI)

One concrete exporter per the two tools that already have importers; no Giskard
/ garak / RAGAS targets, no round-trip re-import guarantee, no provider
auto-detection, no JS-assertion generation for unsupported detectors (left as a
commented placeholder the user fills in). The seam makes the rest additive.

---

## 10. Result

`tests/test_exporters.py` — **27 tests**, all passing. **Full suite: 316 passed,
10 skipped, 0 failed** (baseline 299 + 27 new), no regressions.

```
python -m pytest tests/test_exporters.py -q   # 27 passed
python -m pytest -q                            # 316 passed, 10 skipped
```

End-to-end smoke confirmed: `qval export promptfoo --suite safety` writes a
`safe_load`-valid config (llm-rubric + refusal `icontains-any`, unsupported
detectors as header placeholders) and `qval export deepeval --suite bias`
writes a `compile()`-clean pytest file (10 cases → 20 tests via paired
expansion), each with its `<out>.fidelity.md` sidecar.

> **Note (env):** the repo's runtime uses PEP-604 `X | None` expressions
> (`engine/run_service.py`) that require **Python ≥ 3.10**; the bundled `.venv`
> is 3.9 and cannot import the CLI. Tests for this feature were run on a 3.12
> interpreter. Tracked as a pre-existing tech-debt item (see `docs/TECH_DEBT.md`).
