"""Exporter framework (F-17) — the reverse of the importer seam (F-03).

Where an importer maps an external tool's *results* into the canonical schema,
an exporter maps a qval native *suite* (a list of :class:`TestCase`) out into a
runnable config for another tool. Each tool subclasses :class:`BaseExporter`,
implements ``export_suite``, and registers itself (see ``registry``). The CLI
stays tool-agnostic — it talks to ``BaseExporter`` and the registry, never to a
specific tool, so adding a third exporter adds one module and nothing else.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from qval.engine.schemas import TestCase
from qval.utils.file_loader import write_text
from .fidelity import FidelityReport


@dataclass
class ExportResult:
    """The rendered config plus the fidelity report describing the translation."""

    text: str
    fidelity: FidelityReport


@dataclass
class WrittenExport:
    """Paths written by :meth:`BaseExporter.export_to_path`, plus the result."""

    output_path: Path
    fidelity_path: Path
    result: ExportResult


class BaseExporter(ABC):
    """Base class for suite exporters.

    Subclasses set ``tool_name`` / ``default_extension`` and implement the pure
    ``export_suite`` (cases -> :class:`ExportResult`). They inherit the
    ``export_to_path`` template that writes both the config and its
    ``PATH.fidelity.md`` sidecar.
    """

    tool_name: str = ""
    default_extension: str = ""

    @abstractmethod
    def export_suite(self, cases: list[TestCase], suite_name: str) -> ExportResult:
        """Render ``cases`` into this tool's config. Pure — no disk I/O."""

    def export_to_path(self, cases: list[TestCase], suite_name: str,
                       out_path) -> WrittenExport:
        """Template method: render, then write the config + fidelity sidecar.

        The fidelity report lands at ``<out_path>.fidelity.md`` so it sits right
        next to whatever the user named the config.
        """
        result = self.export_suite(list(cases), suite_name)
        out_path = Path(out_path)
        write_text(out_path, result.text)
        fidelity_path = out_path.with_name(out_path.name + ".fidelity.md")
        write_text(fidelity_path, result.fidelity.render_markdown())
        return WrittenExport(out_path, fidelity_path, result)
