"""U-00 — project-aware path resolution and a runnable first-run scaffold.

These tests pin the contract that makes a freshly `qval init`-scaffolded
project in an empty directory runnable end-to-end, independent of the repo
checkout the package happens to be installed from.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from qval import project
from qval.cli import main


@pytest.fixture(autouse=True)
def _clean_active_project():
    """No test should leak an active project into the next one."""
    project.clear_active_project()
    yield
    project.clear_active_project()


def _write_project(root: Path, qval_yaml: str = "provider: mock\nmodel: demo\n") -> None:
    (root / "qval.yaml").write_text(qval_yaml, encoding="utf-8")


def test_discovery_from_nested_subdir(tmp_path):
    _write_project(tmp_path)
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)

    proj = project.find_project_root(start=nested)

    assert proj is not None
    assert proj.root == tmp_path
    # Defaults are anchored at the discovered root.
    assert proj.config_dir == tmp_path / "config"
    assert proj.test_cases_dir == tmp_path / "test_cases"
    assert proj.outputs_dir == tmp_path / "outputs"
    assert proj.policy_path == tmp_path / "policy.yaml"


def test_override_keys_are_relative_to_root(tmp_path):
    _write_project(
        tmp_path,
        "provider: mock\n"
        "test_cases_dir: cases\n"
        "config_dir: cfg\n"
        "outputs_dir: build/out\n",
    )

    proj = project.find_project_root(start=tmp_path)

    assert proj.test_cases_dir == tmp_path / "cases"
    assert proj.config_dir == tmp_path / "cfg"
    assert proj.outputs_dir == tmp_path / "build" / "out"


def test_no_project_returns_none(tmp_path):
    assert project.find_project_root(start=tmp_path) is None


def test_require_project_raises_actionable_error(tmp_path):
    with pytest.raises(project.ProjectNotFoundError) as exc:
        project.require_project(start=tmp_path)
    msg = str(exc.value)
    assert "No qval project found" in msg
    assert "qval init" in msg


def test_init_then_run_mock_is_runnable_end_to_end(tmp_path, monkeypatch):
    """The headline acceptance criterion: init an empty dir, then run --mock,
    and get both a report and a canonical run.json with zero edits."""
    monkeypatch.chdir(tmp_path)

    assert main(["init"]) == 0

    # Scaffold is complete and self-describing.
    assert (tmp_path / "qval.yaml").is_file()
    assert (tmp_path / "config" / "model_config.json").is_file()
    assert (tmp_path / "config" / "scoring_config.json").is_file()
    assert (tmp_path / "config" / "risk_matrix.json").is_file()
    suites = list((tmp_path / "test_cases").glob("*_tests.json"))
    assert len(suites) >= 2

    rc = main(["run", "--mock"])
    assert rc in (0, 1)  # 1 only if a critical case fails; both mean it ran

    results_dir = tmp_path / "outputs" / "results"
    canonical = list(results_dir.glob("*.canonical.json"))
    assert canonical, f"no canonical run.json under {results_dir}"

    run = json.loads(canonical[0].read_text(encoding="utf-8"))
    assert run["source_tool"] == "qval"
    assert run["cases"], "canonical run has no cases"

    reports = list((tmp_path / "outputs" / "reports").glob("*.html"))
    assert reports, "no HTML report produced"


def test_run_outside_any_project_reports_actionable_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["run", "--mock"])
    assert rc != 0
    captured = capsys.readouterr()
    assert "No qval project found" in (captured.out + captured.err)
