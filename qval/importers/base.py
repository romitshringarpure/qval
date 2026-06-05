"""Importer framework (F-03).

A pluggable seam: each external eval tool (Promptfoo F-03, DeepEval F-09, ...)
subclasses ``BaseImporter``, implements ``to_canonical``, and registers itself
(see ``registry``). The CLI and downstream code stay tool-agnostic — they talk
to ``BaseImporter`` and the registry, never to a specific tool. Adding a tool
adds one module; it never edits the CLI.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from qval.canonical import CanonicalRun
from qval.canonical.schema import ALL_SEVERITIES, SEVERITY_INFO


class BaseImporter(ABC):
    """Base class for eval-tool importers.

    Subclasses set ``tool_name`` and implement ``to_canonical``. They inherit a
    tolerant JSON ``load`` (override for tools with a different on-disk layout)
    and the ``import_path`` template that wires load -> to_canonical.
    """

    tool_name: str = ""

    def load(self, path) -> Any:
        """Read a JSON results file, or a directory containing ``results.json``.

        Raises ValueError on a missing path or malformed JSON — the CLI surfaces
        this as a friendly error (exit 1) rather than a raw traceback.
        """
        path = Path(path)
        if path.is_dir():
            path = path / "results.json"
        if not path.is_file():
            raise ValueError(f"no results file at {path}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path} is not valid JSON: {e}")

    @abstractmethod
    def to_canonical(self, data: Any, *, default_severity: str,
                     source: str) -> CanonicalRun:
        """Map a tool's parsed results into a CanonicalRun. Tool-specific."""

    def import_path(self, path, *,
                    default_severity: str = SEVERITY_INFO) -> CanonicalRun:
        """Template method: load the path, then map it to canonical."""
        data = self.load(path)
        return self.to_canonical(data, default_severity=default_severity,
                                 source=str(path))


# --- shared helpers (every importer reuses these) ---------------------------

def resolve_severity(record_severity, default: str) -> str:
    """Pick a finding severity: explicit record value -> default -> info.

    Validates against ``ALL_SEVERITIES`` and raises ValueError on an unknown
    value rather than guessing — a silent mismap would corrupt downstream gate
    decisions (same posture as the F-01 native mappers).
    """
    value = record_severity or default or SEVERITY_INFO
    if value not in ALL_SEVERITIES:
        raise ValueError(
            f"invalid severity {value!r}; must be one of {ALL_SEVERITIES}"
        )
    return value


def split_provider_model(provider: str) -> tuple[str, str]:
    """Split a Promptfoo-style provider id into (provider, model).

    ``'openai:gpt-4o'`` -> ``('openai', 'gpt-4o')``. No colon -> ``(value, '')``.
    Empty -> ``('', '')``.
    """
    if not provider:
        return "", ""
    head, sep, tail = provider.partition(":")
    return (head, tail) if sep else (head, "")
