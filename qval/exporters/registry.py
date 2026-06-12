"""Exporter registry (F-17).

Maps a tool name to its exporter instance — the mirror image of the importer
registry. The CLI derives its available ``tool`` choices from
``available_tools()``, so registering a new exporter makes it selectable in
``qval export`` with zero CLI changes.
"""
from __future__ import annotations

from .base import BaseExporter

_EXPORTERS: dict[str, BaseExporter] = {}


def register(exporter: BaseExporter) -> BaseExporter:
    """Register an exporter instance under its ``tool_name``. Returns it."""
    if not exporter.tool_name:
        raise ValueError(f"{type(exporter).__name__} has no tool_name")
    _EXPORTERS[exporter.tool_name] = exporter
    return exporter


def get_exporter(tool: str) -> BaseExporter:
    """Look up an exporter by tool name. Raises ValueError if unknown."""
    try:
        return _EXPORTERS[tool]
    except KeyError:
        known = ", ".join(available_tools()) or "(none registered)"
        raise ValueError(f"unknown export tool {tool!r}; available: {known}")


def available_tools() -> list[str]:
    """Sorted list of registered tool names."""
    return sorted(_EXPORTERS)
