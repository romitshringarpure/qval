"""Project path resolution for local-first Qval workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qval.config import find_config_file, load_project_config, ProjectConfigError
from qval.utils import file_loader


@dataclass(frozen=True)
class ProjectPaths:
    """Resolved paths the CLI and local UI expose to users."""

    root: Path
    config_file: Path | None
    config_dir: Path
    suites_dir: Path
    outputs_dir: Path

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "config_file": str(self.config_file) if self.config_file else None,
            "paths": {
                "config": str(self.config_dir),
                "suites": str(self.suites_dir),
                "outputs": str(self.outputs_dir),
            },
        }


def resolve_project(start: Path | None = None) -> ProjectPaths:
    """Resolve the local Qval project, falling back to bundled repo paths."""

    config_file = find_config_file(start)
    if config_file is None:
        return ProjectPaths(
            root=file_loader.PROJECT_ROOT,
            config_file=None,
            config_dir=file_loader.CONFIG_DIR,
            suites_dir=file_loader.TEST_CASES_DIR,
            outputs_dir=file_loader.OUTPUTS_DIR,
        )

    root = config_file.parent
    try:
        config = load_project_config(config_file)
    except ProjectConfigError:
        config = {}

    return ProjectPaths(
        root=root,
        config_file=config_file,
        config_dir=_resolve_path(root, config.get("config_dir"), file_loader.CONFIG_DIR),
        suites_dir=_resolve_path(root, config.get("suites_dir"), file_loader.TEST_CASES_DIR),
        outputs_dir=_resolve_path(root, config.get("outputs_dir"), file_loader.OUTPUTS_DIR),
    )


def _resolve_path(root: Path, configured: object, fallback: Path) -> Path:
    if not configured:
        return fallback
    path = Path(str(configured))
    return path if path.is_absolute() else root / path
