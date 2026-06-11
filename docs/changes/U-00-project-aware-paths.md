# U-00 · First-run fix & project-aware paths

**Status:** shipped (2026-06-10) · **Supersedes:** TD-05, BL-04 · **Depends:** F-02

## Problem

`qval run`/`doctor` resolved `test_cases/` and `config/` relative to the
installed package's repo checkout (`Path(__file__).parents[2]`). A freshly
`qval init`-scaffolded project in an empty directory was therefore *scaffolded
but not runnable* — every install → init → run funnel died at step one.

## What shipped

- **`qval/project.py`** — git-style project discovery. `find_project_root(start)`
  walks up to the nearest `qval.yaml` and returns a frozen `Project` exposing
  resolved `root`, `test_cases_dir`, `config_dir`, `outputs_dir`, `policy_path`.
  Path keys (`test_cases_dir`, `config_dir`, `outputs_dir`) are overridable in
  `qval.yaml`, resolved relative to the root. `require_project()` raises
  `ProjectNotFoundError` with an actionable message when none is found.
- **Active project.** `set_active_project()` / `get_active_project()` hold the
  resolved project for the process; `qval/utils/file_loader.py` resolves
  `config_dir()` / `test_cases_dir()` / `outputs_dir()` from it at call time
  instead of import-time globals. Falls back to the repo checkout when unset.
- **`run`/`doctor`** set the active project from cwd at startup. `doctor` prints
  the resolved root and every path, and exits non-zero with the actionable
  message when there is no project. `load_all_suites()` skips absent suites so a
  fresh project (which ships a subset) runs under the default `--suite all`.
- **`qval run` emits a canonical run.json** to `outputs/results/<run_id>.canonical.json`
  via the existing `run_summary_to_canonical` + `save_canonical`, closing the
  gap where `run` produced no artifact the gate/report could consume.
- **`qval init` scaffolds a runnable project**: `qval.yaml`, `policy.yaml`,
  `.env.example`, `config/` (model/scoring/risk JSON), `test_cases/` with two
  starter suites (instruction_following + safety), and `outputs/.gitignore`. The
  template config defaults `provider: mock` so first-run is fully offline.
- **Repo checkout** is now a first-class project via a root `qval.yaml`.

## Acceptance

`mkdir fresh && cd fresh && qval init && qval run --mock` produces an HTML report
and a canonical run.json with zero edits. Discovery works from nested
subdirectories; running outside any project prints the actionable error.

## Tests

`tests/test_project_resolution.py` — nested-subdir discovery, override keys,
no-project error, `require_project` message, end-to-end init→run --mock asserting
report + canonical run.json, and the outside-project error path. Existing CLI,
smoke, and observability tests updated for the new scaffold layout, the
`doctor`-fails-without-project contract, and the `outputs_dir()` accessor.
Full suite: 128 passing.
