# F-02 · CLI Foundation — Change Record

**Status:** ✅ Done
**Date:** 2026-06-05
**Sprint:** 1
**Depends on:** F-01 (canonical evidence schema)

---

## 1. What this is

A pip-installable `qval` command-line interface. The package becomes installable
via `pip install -e .`, exposing a `qval` console entry point with subcommands:

- **Real today:** `qval init` (scaffold a project), `qval doctor` (validate
  environment + config), `qval run` (run the native eval suite).
- **Stubbed:** `qval gate` (F-04), `qval report` (F-05), `qval import` (F-03) —
  registered in the dispatcher and discoverable in `--help`, but they print a
  "not implemented yet" message and exit `3` until their feature lands.

**One-line:** F-01 made Qval a library with a stable contract; F-02 makes it an
installable tool with a CLI surface a user can actually run.

---

## 2. What changed (files)

| File | Change |
|------|--------|
| `src/` → `qval/` | **Renamed.** Package root is now an importable `qval` package; all intra-package imports updated accordingly. |
| `pyproject.toml` | **New.** Package metadata, dependencies, `qval = "qval.cli:main"` console entry point, `requires-python = ">=3.9"`, `[dev]` extra (pytest), template package-data. |
| `qval/config.py` | **New.** Locates and loads a project's `qval.yaml` / `qval.yml` / `qval.json` via `yaml.safe_load`. |
| `qval/cli.py` | **New.** argparse-based dispatcher; wires subparsers to command handlers; `main()` is the console entry point. |
| `qval/__main__.py` | **New.** Enables `python -m qval`, delegating to `qval.cli.main`. |
| `qval/commands/__init__.py` | **New.** Command package surface. |
| `qval/commands/stubs.py` | **New.** Generates handlers for not-yet-implemented commands; exits `3`. |
| `qval/commands/init.py` | **New.** Scaffolds `qval.yaml`, `policy.yaml`, and `suites/` from templates. |
| `qval/commands/doctor.py` | **New.** Validates Python version, config presence, and environment. |
| `qval/commands/run.py` | **New.** Native eval run handler (wraps the existing engine pipeline). |
| `qval/templates/*` | **New.** `qval.yaml`, `policy.yaml`, and `suites/example.json` emitted by `qval init`. |
| `qval/main.py` | Reduced to a thin backward-compatible shim → `qval.cli.main`. |
| `tests/test_cli.py`, `tests/test_config.py` | **New.** Cover the dispatcher, stub exit codes, init/doctor behavior, and the config loader. |

---

## 3. Design choices

- **argparse subparsers (zero dependency).** The CLI dispatcher uses stdlib
  `argparse` with subparsers rather than a third-party framework (Click/Typer),
  keeping the install footprint minimal and matching the project's stdlib-first
  posture.
- **YAML-or-JSON config loader.** The loader uses `yaml.safe_load`, which parses
  JSON as a subset of YAML — so a project can use `qval.yaml` or `qval.json`
  interchangeably without a second code path.
- **Stub exit code `3`.** Unimplemented commands exit `3`, deliberately distinct
  from argparse's usage error (`2`) and a generic runtime failure (`1`). A caller
  or CI script can tell "this command isn't built yet" apart from "this command
  failed."
- **`requires-python` relaxed 3.10 → 3.9.** The codebase uses
  `from __future__ import annotations`, so the 3.10-only deferred-annotation
  behavior is not required at runtime. Lowering the floor to 3.9 widens
  compatibility at no cost; CI now tests 3.9 through 3.12.
- **`main.py` reduced to a shim.** The legacy `python qval/main.py` path still
  works (it imports and calls `qval.cli.main`), so nothing that depended on the
  old entry point breaks while `qval` becomes the documented interface.

---

## 4. Known limitation / follow-up

`qval run` currently resolves `test_cases/` and `config/` relative to the
installed package (repo-rooted). As a result, a project freshly created with
`qval init` in an arbitrary directory is scaffolded but **not yet runnable
end-to-end** — `qval run` still reads the repo checkout's data, not the new
project's. Project-aware path resolution (cwd/config-driven `test_cases` and
`config`, plus `suites_dir` discovery) is tracked as a follow-up. For now the
documented quickstart is framed in the context of the cloned repo, where
`qval run --mock` works end-to-end.

---

## 5. Tests

`tests/test_cli.py` and `tests/test_config.py` cover the dispatcher, stub exit
codes, `init`/`doctor`, and the config loader, on top of the existing suites.

**Result:** full suite **69 pass**, no regressions.

```
python -m pytest tests/ -q   # 69 passed
```
