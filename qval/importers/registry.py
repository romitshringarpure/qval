"""Importer registry (F-03).

Maps a tool name to its importer instance. The CLI derives its available
``tool`` choices from ``available_tools()``, so registering a new importer
(e.g. DeepEval in F-09) makes it appear in ``qval import --help`` with zero CLI
changes.
"""
from __future__ import annotations

from .base import BaseImporter

_IMPORTERS: dict[str, BaseImporter] = {}


def register(importer: BaseImporter) -> BaseImporter:
    """Register an importer instance under its ``tool_name``. Returns it."""
    if not importer.tool_name:
        raise ValueError(f"{type(importer).__name__} has no tool_name")
    _IMPORTERS[importer.tool_name] = importer
    return importer


def get_importer(tool: str) -> BaseImporter:
    """Look up an importer by tool name. Raises ValueError if unknown."""
    try:
        return _IMPORTERS[tool]
    except KeyError:
        known = ", ".join(available_tools()) or "(none registered)"
        raise ValueError(f"unknown import tool {tool!r}; available: {known}")


def available_tools() -> list[str]:
    """Sorted list of registered tool names."""
    return sorted(_IMPORTERS)
