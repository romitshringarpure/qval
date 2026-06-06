"""Governance control mapping (F-07).

Maps Qval test categories to governance controls (OWASP-LLM, NIST AI RMF),
stamps ``Finding.control_ids`` + ``CanonicalRun.controls``, and computes a
per-control coverage matrix for the gate and report.

    from qval.controls import load_catalog, map_controls, coverage
"""

from .catalog import load_catalog, Catalog, ControlCatalogError, DEFAULT_CATALOG_PATH
from .mapper import (
    map_controls, coverage, ControlCoverage,
    COVERAGE_PASSED, COVERAGE_FAILED, COVERAGE_NEEDS_REVIEW, COVERAGE_NOT_EXERCISED,
)

__all__ = [
    "load_catalog", "Catalog", "ControlCatalogError", "DEFAULT_CATALOG_PATH",
    "map_controls", "coverage", "ControlCoverage",
    "COVERAGE_PASSED", "COVERAGE_FAILED", "COVERAGE_NEEDS_REVIEW",
    "COVERAGE_NOT_EXERCISED",
]
