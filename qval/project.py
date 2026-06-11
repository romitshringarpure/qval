"""Project-aware path resolution (U-00).

A Qval project is anchored by a ``qval.yaml`` at its root, discovered git-style
by walking up from the current directory. Every path the CLI touches — test
cases, config, outputs, policy — resolves relative to that root, so a freshly
``qval init``-scaffolded project in an empty directory is runnable regardless
of where the ``qval`` package itself is installed.

Discovery is layered on top of :mod:`qval.config`, which already owns the
walk-up and the qval.yaml/json parsing. This module adds the resolved
:class:`Project` value object and a process-wide "active project" that the
existing file-loader consumers read at call time.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qval.config import find_project_root as _find_root_dir, load_project_config

#: The actionable error shown when no project is found.
NO_PROJECT_MESSAGE = (
    "No qval project found. Run 'qval init' to create one, or cd into a project."
)


class ProjectNotFoundError(Exception):
    """Raised when a command needs a project but none is discoverable."""


@dataclass(frozen=True)
class Project:
    """Resolved, absolute paths for one Qval project."""

    root: Path
    test_cases_dir: Path
    config_dir: Path
    outputs_dir: Path
    policy_path: Path


def _resolve(root: Path, config: dict, key: str, default: str) -> Path:
    """Resolve an override key from qval.yaml relative to ``root``."""
    value = config.get(key, default)
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (root / candidate)


def project_for_root(root: Path) -> Project:
    """Build a :class:`Project` for a known root, honouring qval.yaml overrides."""
    root = Path(root).resolve()
    config: dict = {}
    cfg_file = _config_file_in(root)
    if cfg_file is not None:
        try:
            config = load_project_config(cfg_file)
        except Exception:
            # A malformed config still yields a usable default layout; doctor
            # is the command that surfaces the parse error.
            config = {}
    return Project(
        root=root,
        test_cases_dir=_resolve(root, config, "test_cases_dir", "test_cases"),
        config_dir=_resolve(root, config, "config_dir", "config"),
        outputs_dir=_resolve(root, config, "outputs_dir", "outputs"),
        policy_path=_resolve(root, config, "policy_path", "policy.yaml"),
    )


def _config_file_in(root: Path) -> Path | None:
    for name in ("qval.yaml", "qval.yml", "qval.json"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def find_project_root(start: Path | None = None) -> Project | None:
    """Discover the project containing ``start`` (default cwd).

    Returns a resolved :class:`Project`, or ``None`` when no qval.yaml is found
    at or above ``start``.
    """
    root = _find_root_dir(start)
    if root is None:
        return None
    return project_for_root(root)


def require_project(start: Path | None = None) -> Project:
    """Like :func:`find_project_root` but raise an actionable error when absent."""
    proj = find_project_root(start)
    if proj is None:
        raise ProjectNotFoundError(NO_PROJECT_MESSAGE)
    return proj


# --- Active project ---------------------------------------------------------
# Existing consumers (file_loader, response_logger, report_generator) read path
# roots from module-level globals computed at import time. Rather than thread a
# Project through every signature, a command sets the active project once at
# startup and those consumers resolve against it at call time.

_ACTIVE: Project | None = None


def _repo_checkout_root() -> Path:
    """The repo checkout the package is installed from (legacy fallback)."""
    return Path(__file__).resolve().parents[1]


def repo_checkout_project() -> Project:
    """The project rooted at the repo checkout — the pre-U-00 default layout."""
    return project_for_root(_repo_checkout_root())


def set_active_project(project: Project) -> None:
    global _ACTIVE
    _ACTIVE = project


def clear_active_project() -> None:
    global _ACTIVE
    _ACTIVE = None


def get_active_project() -> Project:
    """The active project, or the repo-checkout fallback when none is set."""
    return _ACTIVE if _ACTIVE is not None else repo_checkout_project()
