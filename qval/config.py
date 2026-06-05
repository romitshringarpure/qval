"""Project config discovery and loading for the Qval CLI.

A Qval project is identified by a `qval.yaml` (or `qval.json`) file at its root.
The loader uses yaml.safe_load, which also parses JSON, so either format works.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CONFIG_NAMES = ("qval.yaml", "qval.yml", "qval.json")


class ProjectConfigError(Exception):
    """Raised when a project config file is missing or unparseable."""


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up from `start` (default cwd) looking for a qval config file.

    Returns the directory containing it, or None if none is found.
    """
    start = (start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        for name in CONFIG_NAMES:
            if (directory / name).is_file():
                return directory
    return None


def find_config_file(start: Path | None = None) -> Path | None:
    """Return the path to the first qval config file at/above `start`."""
    root = find_project_root(start)
    if root is None:
        return None
    for name in CONFIG_NAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def load_project_config(path: Path) -> dict[str, Any]:
    """Load a qval.yaml/qval.json file into a dict.

    Raises ProjectConfigError if the file is missing or does not parse to a dict.
    """
    path = Path(path)
    if not path.is_file():
        raise ProjectConfigError(f"Config file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:  # also covers JSON syntax errors
        raise ProjectConfigError(f"Could not parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProjectConfigError(f"Config in {path} must be a mapping, got {type(data).__name__}")
    return data
