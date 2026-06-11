"""Suite-library read model shared by CLI-adjacent surfaces."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from qval.controls.catalog import ControlCatalogError, load_catalog
from qval.engine.schemas import TestCase, ALL_RISK_LEVELS
from qval.utils.file_loader import ALL_SUITES, load_test_suite


def list_suite_library() -> list[dict[str, Any]]:
    """Return all bundled suites with case metadata and control mappings."""

    catalog = _safe_catalog()
    suites: list[dict[str, Any]] = []
    for suite in ALL_SUITES:
        cases = [
            TestCase.from_dict(raw, source=f"test_cases/{suite}")
            for raw in load_test_suite(suite)
        ]
        control_ids = catalog.control_ids_for(suite) if catalog else []
        suites.append({
            "name": suite,
            "case_count": len(cases),
            "categories": sorted({case.category for case in cases}),
            "severities": _ordered_risks({case.risk_level for case in cases}),
            "control_mappings": [
                _control_payload(catalog.control(control_id))
                for control_id in control_ids
            ] if catalog else [],
            "cases": [
                _case_payload(case, catalog.control_ids_for(case.category) if catalog else [],
                              catalog)
                for case in cases
            ],
        })
    return suites


def _case_payload(case: TestCase, control_ids: list[str], catalog) -> dict[str, Any]:
    payload = {
        "id": case.id,
        "name": case.name,
        "category": case.category,
        "severity": case.risk_level,
        "risk_level": case.risk_level,
        "description": case.description,
        "prompt": case.prompt,
        "expected_behavior": case.expected_behavior,
        "scoring_type": case.scoring_type,
        "detectors": list(case.detectors),
        "manual_review_required": case.manual_review_required,
        "tags": list(case.tags),
        "extra": dict(case.extra),
        "control_ids": list(control_ids),
        "controls": [],
    }
    if catalog:
        payload["controls"] = [
            _control_payload(catalog.control(control_id))
            for control_id in control_ids
        ]
    return payload


def _control_payload(control) -> dict[str, Any]:
    return asdict(control)


def _ordered_risks(risks: set[str]) -> list[str]:
    return [risk for risk in ALL_RISK_LEVELS if risk in risks]


def _safe_catalog():
    try:
        return load_catalog()
    except ControlCatalogError:
        return None
