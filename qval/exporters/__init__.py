"""Pluggable suite exporters (F-17) — the reverse of the importers (F-03/F-09).

Each external eval tool gets a ``BaseExporter`` subclass that renders a qval
native suite (a list of :class:`~qval.engine.schemas.TestCase`) into that tool's
runnable config, registered by name. The CLI talks to the registry, never to a
specific tool — adding a tool adds a module here and registers it.

    from qval.exporters import get_exporter
    result = get_exporter("promptfoo").export_suite(cases, "safety")
    print(result.text)            # promptfooconfig.yaml
    print(result.fidelity.render_table())
"""

from .base import BaseExporter, ExportResult, WrittenExport
from .registry import register, get_exporter, available_tools

# Import concrete exporters so they self-register with the registry.
from . import promptfoo  # noqa: F401
from . import deepeval   # noqa: F401

__all__ = [
    "BaseExporter",
    "ExportResult",
    "WrittenExport",
    "register",
    "get_exporter",
    "available_tools",
]
