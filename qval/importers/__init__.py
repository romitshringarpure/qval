"""Pluggable eval-tool importers (F-03).

Each external eval tool gets a ``BaseImporter`` subclass that maps its results
into the canonical schema, registered by name. The CLI and downstream features
talk to the registry, never to a specific tool — adding DeepEval (F-09) or any
other tool adds a module here and registers it; nothing else changes.

    from qval.importers import get_importer, available_tools
    run = get_importer("promptfoo").import_path("results.json")
"""

from .base import BaseImporter, resolve_severity, split_provider_model
from .registry import register, get_importer, available_tools

# Import concrete importers so they self-register with the registry.
from . import promptfoo  # noqa: F401
from . import deepeval   # noqa: F401

__all__ = [
    "BaseImporter",
    "resolve_severity",
    "split_provider_model",
    "register",
    "get_importer",
    "available_tools",
]
