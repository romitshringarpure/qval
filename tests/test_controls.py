"""F-07 · Control mapping tests.

Covers the catalog loader (+ validation), the mapper (control_ids on findings,
run.controls population), the coverage rollup, the `qval map` CLI, and the
report's control-coverage section.
"""
from __future__ import annotations

import json

import pytest

from qval.canonical import (
    CanonicalRun, Case, Finding,
    STATUS_PASSED, STATUS_FAILED, STATUS_NEEDS_REVIEW,
    SEVERITY_HIGH, SEVERITY_LOW, SEVERITY_CRITICAL,
)
from qval.canonical.io import save_canonical, load_canonical
from qval.controls import (
    load_catalog, map_controls, coverage, ControlCatalogError,
    COVERAGE_PASSED, COVERAGE_FAILED, COVERAGE_NEEDS_REVIEW, COVERAGE_NOT_EXERCISED,
)


# --- helpers ----------------------------------------------------------------

def run_of(specs):
    """specs: list of (case_id, category, status, severity)."""
    cases, findings = [], []
    for cid, cat, status, sev in specs:
        cases.append(Case(case_id=cid, name=cid, category=cat, prompt="p"))
        findings.append(Finding(finding_id=cid, case_id=cid, status=status, severity=sev))
    return CanonicalRun(run_id="r", source_tool="qval", model="m", provider="p",
                        cases=cases, findings=findings)


def write_catalog(tmp_path, obj):
    p = tmp_path / "controls.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


SMALL_CATALOG = {
    "controls": {
        "OWASP-LLM-02": {"framework": "OWASP-LLM", "title": "Sensitive Info"},
        "NIST-AI-RMF-SAFE": {"framework": "NIST-AI-RMF", "title": "Safe"},
    },
    "category_controls": {
        "privacy": ["OWASP-LLM-02"],
        "safety": ["NIST-AI-RMF-SAFE"],
    },
}


# --- catalog ----------------------------------------------------------------

def test_default_catalog_loads_and_is_consistent():
    cat = load_catalog()  # built-in config/controls.json
    assert "privacy" in cat.mapped_categories()
    for category in cat.category_controls:
        for cid in cat.control_ids_for(category):
            assert cid in cat.controls          # referential integrity


def test_catalog_rejects_dangling_control(tmp_path):
    bad = {"controls": {}, "category_controls": {"privacy": ["MISSING"]}}
    with pytest.raises(ControlCatalogError):
        load_catalog(write_catalog(tmp_path, bad))


def test_catalog_missing_file(tmp_path):
    with pytest.raises(ControlCatalogError):
        load_catalog(tmp_path / "nope.json")


def test_catalog_bad_json(tmp_path):
    p = tmp_path / "controls.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ControlCatalogError):
        load_catalog(p)


# --- mapper -----------------------------------------------------------------

def test_map_stamps_control_ids_and_run_controls(tmp_path):
    cat = load_catalog(write_catalog(tmp_path, SMALL_CATALOG))
    run = run_of([("c1", "privacy", STATUS_FAILED, SEVERITY_HIGH),
                  ("c2", "safety", STATUS_PASSED, SEVERITY_LOW)])
    map_controls(run, cat)
    by_case = {f.case_id: f.control_ids for f in run.findings}
    assert by_case["c1"] == ["OWASP-LLM-02"]
    assert by_case["c2"] == ["NIST-AI-RMF-SAFE"]
    assert {c.control_id for c in run.controls} == {"OWASP-LLM-02", "NIST-AI-RMF-SAFE"}


def test_unmapped_category_gets_no_controls(tmp_path):
    cat = load_catalog(write_catalog(tmp_path, SMALL_CATALOG))
    run = run_of([("c1", "weather", STATUS_PASSED, SEVERITY_LOW)])
    map_controls(run, cat)
    assert run.findings[0].control_ids == []
    assert run.controls == []


def test_run_controls_deduped_and_ordered(tmp_path):
    cat = load_catalog(write_catalog(tmp_path, SMALL_CATALOG))
    run = run_of([("c1", "privacy", STATUS_PASSED, SEVERITY_LOW),
                  ("c2", "privacy", STATUS_FAILED, SEVERITY_HIGH)])
    map_controls(run, cat)
    assert [c.control_id for c in run.controls] == ["OWASP-LLM-02"]


# --- coverage ---------------------------------------------------------------

def test_coverage_failed_when_any_finding_fails(tmp_path):
    cat = load_catalog(write_catalog(tmp_path, SMALL_CATALOG))
    run = run_of([("c1", "privacy", STATUS_PASSED, SEVERITY_LOW),
                  ("c2", "privacy", STATUS_FAILED, SEVERITY_HIGH)])
    map_controls(run, cat)
    cov = {c.control_id: c for c in coverage(run)}
    assert cov["OWASP-LLM-02"].status == COVERAGE_FAILED
    assert cov["OWASP-LLM-02"].total == 2
    assert cov["OWASP-LLM-02"].passed == 1
    assert cov["OWASP-LLM-02"].failed == 1


def test_coverage_passed_when_all_pass(tmp_path):
    cat = load_catalog(write_catalog(tmp_path, SMALL_CATALOG))
    run = run_of([("c1", "privacy", STATUS_PASSED, SEVERITY_LOW)])
    map_controls(run, cat)
    cov = {c.control_id: c for c in coverage(run)}
    assert cov["OWASP-LLM-02"].status == COVERAGE_PASSED


def test_coverage_needs_review(tmp_path):
    cat = load_catalog(write_catalog(tmp_path, SMALL_CATALOG))
    run = run_of([("c1", "privacy", STATUS_NEEDS_REVIEW, SEVERITY_LOW)])
    map_controls(run, cat)
    cov = {c.control_id: c for c in coverage(run)}
    assert cov["OWASP-LLM-02"].status == COVERAGE_NEEDS_REVIEW


# --- CLI --------------------------------------------------------------------

def test_cli_map_prints_coverage_and_writes(tmp_path, capsys):
    from qval.cli import main
    catalog = write_catalog(tmp_path, SMALL_CATALOG)
    src = tmp_path / "run.json"
    save_canonical(run_of([("c1", "privacy", STATUS_FAILED, SEVERITY_CRITICAL)]), src)
    out = tmp_path / "mapped.json"
    rc = main(["map", str(src), "--catalog", str(catalog), "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "OWASP-LLM-02" in printed and "FAIL" in printed
    mapped = load_canonical(out)
    assert mapped.findings[0].control_ids == ["OWASP-LLM-02"]
    assert {c.control_id for c in mapped.controls} == {"OWASP-LLM-02"}


def test_cli_map_bad_catalog_exit_2(tmp_path):
    from qval.cli import main
    src = tmp_path / "run.json"
    save_canonical(run_of([("c1", "privacy", STATUS_PASSED, SEVERITY_LOW)]), src)
    rc = main(["map", str(src), "--catalog", str(tmp_path / "missing.json")])
    assert rc == 2


def test_cli_map_bad_run_exit_2(tmp_path):
    from qval.cli import main
    catalog = write_catalog(tmp_path, SMALL_CATALOG)
    rc = main(["map", str(tmp_path / "missing.json"), "--catalog", str(catalog)])
    assert rc == 2


# --- report integration -----------------------------------------------------

def test_report_renders_control_coverage(tmp_path):
    from qval.reports.canonical_report import render_markdown, render_html
    cat = load_catalog(write_catalog(tmp_path, SMALL_CATALOG))
    run = run_of([("c1", "privacy", STATUS_FAILED, SEVERITY_HIGH)])
    map_controls(run, cat)
    md = render_markdown(run, None, None)
    assert "Control Coverage" in md and "OWASP-LLM-02" in md
    html = render_html(run, None, None)
    assert "Control Coverage" in html and "OWASP-LLM-02" in html
