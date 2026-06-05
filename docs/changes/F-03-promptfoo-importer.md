# F-03 · Promptfoo Importer — Change Record

**Status:** ✅ Done
**Date:** 2026-06-05
**Sprint:** 2
**Depends on:** F-01 (canonical schema), F-02 (CLI foundation)

---

## 1. What this is

`qval import promptfoo <path>` — read a [Promptfoo](https://promptfoo.dev)
`results.json` (or a directory containing one) and normalize it into a
canonical `run.json` (the F-01 `CanonicalRun` shape). This makes Qval's core
positioning concrete: *bring your own eval tool, Qval handles governance.* A
team keeps running Promptfoo; Qval turns the output into an auditable artifact
the gate (F-04), reports (F-05), and evidence packs (F-08) all consume.

The importer is built behind a **pluggable seam** so DeepEval (F-09) and any
other eval tool snap in by adding one module — no CLI changes.

**One-line:** F-01 defined the cross-tool contract; F-03 fills it from the
first external tool and proves the seam is real.

---

## 2. Architecture — pluggable importers

```
qval import <tool> <path> [--out run.json] [--default-severity info]
        │
        ▼
commands/import_cmd.py     CLI: tool choices from registry, dispatch, print summary
        │
        ▼
importers/registry.py      IMPORTERS dict · register() · get_importer() · available_tools()
importers/base.py          BaseImporter (ABC) + shared helpers + import_path() template
importers/promptfoo.py     PromptfooImporter(BaseImporter)   ← first concrete importer
        │
        ▼
canonical/io.py            save_canonical(run, path) / load_canonical(path)
        │
        ▼
run.json                   CanonicalRun.to_dict(), schema_version 1.0
```

### 2.1 `BaseImporter` contract

Each tool implements **two** things and inherits the rest:

```python
class BaseImporter(ABC):
    tool_name: str                                   # "promptfoo"

    def load(self, path) -> Any:                      # default: tolerant JSON file-or-dir
        ...

    @abstractmethod
    def to_canonical(self, data, *, default_severity, source) -> CanonicalRun:
        ...                                           # tool-specific field mapping

    def import_path(self, path, *, default_severity) -> CanonicalRun:
        return self.to_canonical(self.load(path), default_severity=default_severity,
                                 source=str(path))    # template method
```

### 2.2 Shared helpers (in `base.py`, every importer reuses)

- `resolve_severity(record_severity, default)` — explicit record severity →
  `default` → `"info"`; validated against `ALL_SEVERITIES`, raises `ValueError`
  on an unknown value (no silent mismap — matches the F-01 mapper posture).
- `split_provider_model("openai:gpt-4o")` → `("openai", "gpt-4o")`; no colon →
  `(value, "")`.
- default `load()` — reads a JSON file, or a directory containing `results.json`.

### 2.3 Registry

`IMPORTERS` is a name→importer dict with `register()`. The CLI derives its
`tool` argument choices from `available_tools()`, so a newly registered
importer appears in `qval import --help` automatically. No entry-point /
plugin-discovery machinery yet (YAGNI) — added only if third-party importers
are needed.

---

## 3. Promptfoo → canonical mapping

The tolerant loader locates the results array at `data["results"]["results"]`
(modern nested), else `data["results"]` if a list, else `data` if a list, else
raises a friendly error naming what was expected.

Per Promptfoo result record → one `Case` + one `Finding` (shared id):

| Promptfoo | Canonical | Notes |
|---|---|---|
| `provider.id` / `provider` str | `CanonicalRun.provider` + `.model` | split on first `:` → `openai:gpt-4o` ⇒ provider `openai`, model `gpt-4o`. Run-level taken from first record; per-record provider stashed in `Finding.extra` when mixed |
| `prompt.raw` / `prompt` str | `Case.prompt` | |
| `prompt.label` / first var / index | `Case.name` | |
| `vars` | `Case.extra["vars"]` | |
| `gradingResult.pass` else `success` | `Finding.status` | `True→passed`, `False→failed` |
| `score` else `gradingResult.score` | `Finding.score` | float or `None` |
| `gradingResult.reason` | `Finding.reason` | |
| `response.output` / `response` str | `Finding.response` | |
| `gradingResult.componentResults` | `Finding.extra["assertions"]` | assertion-level detail (analog of native detectors) |
| `latencyMs`, `response.tokenUsage`, `response.cost` | `Finding.extra` | telemetry — no-loss |
| `severity` in record `vars`/`metadata` | `Finding.severity` | resolution: explicit → `--default-severity` → `info` |

- `case_id` / `finding_id`: `f"{promptIdx}-{testIdx}"` when present, else the
  enumeration index.
- Run-level: `run_id` generated (`generate_run_id`), `source_tool="promptfoo"`,
  `started_at`/`completed_at` from the results timestamp or now, `suite` from
  the config description or file stem, `metadata` carries Promptfoo `stats`,
  `evalId`, the source path, and a mixed-provider flag.

### Severity rationale

Promptfoo grades pass/fail + score but never assigns risk severity. The
importer does **not** fabricate one: every finding defaults to `info` (the
non-risk-graded bucket F-01 added for exactly this case). A `--default-severity`
flag overrides the default, and an explicit `severity` carried in the record's
`vars`/`metadata` wins. Risk weighting is the gate's job (F-04), not the
importer's.

---

## 4. Error handling & exit codes

- Missing path / not a file-or-dir → message, **exit 1**.
- Malformed JSON / no locatable results array → message naming the expected
  shape, exit 1.
- Explicit `severity` outside `ALL_SEVERITIES` → `ValueError` listing allowed
  values.
- `qval import` was a stub returning exit `3`; now real → exit `0` on success,
  `1` on input error.

---

## 5. Files

| File | Change |
|------|--------|
| `qval/importers/__init__.py` | **New.** Package surface — re-exports registry API + `BaseImporter`. |
| `qval/importers/base.py` | **New.** `BaseImporter` ABC, shared helpers, `import_path` template. |
| `qval/importers/registry.py` | **New.** `IMPORTERS`, `register`, `get_importer`, `available_tools`. |
| `qval/importers/promptfoo.py` | **New.** `PromptfooImporter(BaseImporter)`. |
| `qval/canonical/io.py` | **New.** `save_canonical` / `load_canonical` (the helper F-01 deferred here). |
| `qval/canonical/__init__.py` | Export `save_canonical` / `load_canonical`. |
| `qval/commands/import_cmd.py` | **New.** `qval import` CLI handler, tool-agnostic dispatch. |
| `qval/cli.py` | Wire `import_cmd.add_parser`. |
| `qval/commands/stubs.py` | Drop `"import"` from `_STUBS` (keep gate/report). |
| `tests/test_import_promptfoo.py` | **New.** ~12 tests. |
| `docs/FEATURES.md` | F-03 status `planned` → `done`. |
| `README.md` | Update `qval import` row (planned → shipped). |
| `features.html` | Reflect F-03 shipped. |

---

## 6. Tests (TDD)

Mapper (`PromptfooImporter().to_canonical`): nested + flat result formats;
provider split; pass/fail → status; score + reason carried; componentResults →
`Finding.extra`; default `info`; `--default-severity` honored; explicit
`severity` honored; bad severity raises. Loader: directory resolves; malformed
→ error. Registry: `available_tools()` lists promptfoo; `get_importer("nope")`
→ friendly error. CLI + io: `qval import promptfoo <fixture> --out` writes a
valid `run.json`, exit 0, round-trips through `load_canonical` /
`CanonicalRun.from_dict`. Fixtures synthesized; no network.

---

## 7. Scope cuts (YAGNI)

No DeepEval (F-09), no multi-file merge, no nested sub-subparsers, no
entry-point plugin discovery, no per-tool divergent flags. Promptfoo is the
only concrete importer F-03 ships; the seam proves the rest snap in.

---

## 8. Result

`tests/test_import_promptfoo.py` — **24 tests**: mapper (nested + flat formats,
provider split, status, score/reason/response, componentResults + telemetry in
`extra`, severity resolution incl. unknown-raises, no-results-raises), loader
(file, directory, malformed, missing), registry (lists promptfoo, unknown
raises), io round-trip, and CLI (`qval import promptfoo … --out` writes a valid
`run.json`, exit 0; bad path exit 1; `--default-severity` applied).

**Full suite: 92 pass**, no regressions (the `import` stub test was removed as
the command is now real; +24 importer tests).

```
python -m pytest tests/test_import_promptfoo.py -q   # 24 passed
python -m pytest -q                                   # 92 passed
```

End-to-end smoke confirmed: `qval import promptfoo <results.json>` splits
`openai:gpt-4o-mini` into provider/model, honors an explicit `severity: high`
from a record's vars over the `info` default, carries the eval id + stats into
`metadata`, and `qval import --help` lists `{promptfoo}` from the registry.
