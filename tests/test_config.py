import json
from pathlib import Path

import pytest

from qval.config import find_project_root, load_project_config, ProjectConfigError


def test_load_yaml_config(tmp_path):
    (tmp_path / "qval.yaml").write_text("provider: mock\nmodel: demo\n", encoding="utf-8")
    cfg = load_project_config(tmp_path / "qval.yaml")
    assert cfg["provider"] == "mock"
    assert cfg["model"] == "demo"


def test_load_json_config(tmp_path):
    p = tmp_path / "qval.json"
    p.write_text(json.dumps({"provider": "mock"}), encoding="utf-8")
    cfg = load_project_config(p)
    assert cfg["provider"] == "mock"


def test_find_project_root_locates_qval_yaml(tmp_path):
    (tmp_path / "qval.yaml").write_text("provider: mock\n", encoding="utf-8")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert find_project_root(start=sub) == tmp_path


def test_find_project_root_returns_none_when_absent(tmp_path):
    assert find_project_root(start=tmp_path) is None


def test_missing_config_raises(tmp_path):
    with pytest.raises(ProjectConfigError):
        load_project_config(tmp_path / "nope.yaml")


def test_non_mapping_config_raises(tmp_path):
    # A YAML scalar parses fine via safe_load but is not a valid config mapping.
    p = tmp_path / "qval.yaml"
    p.write_text("42\n", encoding="utf-8")
    with pytest.raises(ProjectConfigError):
        load_project_config(p)


def test_find_config_file_returns_path(tmp_path):
    cfg = tmp_path / "qval.yaml"
    cfg.write_text("provider: mock\n", encoding="utf-8")
    from qval.config import find_config_file
    assert find_config_file(start=tmp_path) == cfg
