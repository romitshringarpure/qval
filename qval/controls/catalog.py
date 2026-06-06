"""Governance control catalog (F-07).

Loads ``config/controls.json`` into a :class:`Catalog` that maps a Qval test
*category* (``privacy``, ``safety`` …) to one or more governance *controls*
(OWASP-LLM-02, NIST-AI-RMF-SAFE …). The mapper (``qval/controls/mapper.py``)
uses it to stamp ``Finding.control_ids`` and populate ``CanonicalRun.controls``;
the report renders a coverage matrix from those.

The catalog is data, not code: edit the JSON to match your control framework
without touching Python. The loader validates referential integrity (every
mapped control id must be defined) so a typo fails loudly instead of silently
dropping a control.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from qval.canonical import Control
from qval.utils.file_loader import CONFIG_DIR

DEFAULT_CATALOG_PATH = CONFIG_DIR / "controls.json"


class ControlCatalogError(Exception):
    """Raised when a control catalog is missing, unparseable, or inconsistent."""


@dataclass
class Catalog:
    """A resolved control catalog: id -> Control, plus category -> [id]."""

    controls: dict[str, Control] = field(default_factory=dict)
    category_controls: dict[str, list[str]] = field(default_factory=dict)

    def control_ids_for(self, category: str) -> list[str]:
        """Control ids exercised by a category (empty for an unmapped one)."""
        return list(self.category_controls.get(category, []))

    def control(self, control_id: str) -> Control:
        return self.controls[control_id]

    def mapped_categories(self) -> list[str]:
        return list(self.category_controls)


def load_catalog(path=None) -> Catalog:
    """Load and validate a control catalog (default: ``config/controls.json``)."""
    path = Path(path) if path is not None else DEFAULT_CATALOG_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ControlCatalogError(f"control catalog not found: {path}")
    except json.JSONDecodeError as exc:
        raise ControlCatalogError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ControlCatalogError(f"catalog in {path} must be a mapping")

    controls = _parse_controls(raw.get("controls", {}), path)
    category_controls = _parse_category_map(raw.get("category_controls", {}),
                                            controls, path)
    return Catalog(controls=controls, category_controls=category_controls)


# --- internals --------------------------------------------------------------

def _parse_controls(raw, path) -> dict[str, Control]:
    if not isinstance(raw, dict):
        raise ControlCatalogError(f"'controls' in {path} must be a mapping")
    out: dict[str, Control] = {}
    for control_id, spec in raw.items():
        if not isinstance(spec, dict):
            raise ControlCatalogError(f"control {control_id!r} must be a mapping")
        out[control_id] = Control.from_dict({"control_id": control_id, **spec})
    return out


def _parse_category_map(raw, controls, path) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        raise ControlCatalogError(f"'category_controls' in {path} must be a mapping")
    out: dict[str, list[str]] = {}
    for category, ids in raw.items():
        if not isinstance(ids, list):
            raise ControlCatalogError(
                f"category {category!r} must map to a list of control ids"
            )
        for control_id in ids:
            if control_id not in controls:
                raise ControlCatalogError(
                    f"category {category!r} references undefined control "
                    f"{control_id!r}; define it under 'controls' in {path}"
                )
        out[category] = list(ids)
    return out
