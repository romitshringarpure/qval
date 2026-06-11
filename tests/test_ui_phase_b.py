from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

import pytest

from qval.canonical import (
    CanonicalRun,
    Case,
    Finding,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    STATUS_FAILED,
    STATUS_NEEDS_REVIEW,
    STATUS_PASSED,
)
from qval.canonical.io import save_canonical
from qval.engine.run_service import canonical_run_path, load_run


def _ui_client():
    pytest.importorskip("flask")
    from qval.ui.server import create_app

    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _rid(prefix: str) -> str:
    return f"aaa_{prefix}_{uuid4().hex[:10]}"


def _run(run_id: str, specs, *, suite: str = "bias") -> CanonicalRun:
    cases = []
    findings = []
    for case_id, status, severity in specs:
        cases.append(Case(
            case_id=case_id,
            name=f"name-{case_id}",
            category=suite,
            prompt=f"prompt-{case_id}",
            expected_behavior=f"expected-{case_id}",
            extra={"conversation": [
                {"role": "user", "content": f"prompt-{case_id}"},
                {"role": "assistant", "content": f"response-{case_id}"},
            ]},
        ))
        findings.append(Finding(
            finding_id=case_id,
            case_id=case_id,
            status=status,
            severity=severity,
            score=1.0 if status == STATUS_NEEDS_REVIEW else 0.0,
            reason=f"reason-{case_id}",
            response=f"response-{case_id}",
            extra={
                "detectors": [
                    {"name": "detector", "triggered": True, "matches": ["x"],
                     "notes": f"notes-{case_id}"}
                ],
                "judge": {
                    "suggestion": "approve",
                    "confidence": 0.82,
                    "rationale": f"judge-{case_id}",
                    "applied": False,
                },
            },
        ))
    return CanonicalRun(
        run_id=run_id,
        source_tool="qval",
        model="mock",
        provider="mock",
        suite=suite,
        cases=cases,
        findings=findings,
    )


def _save(run: CanonicalRun) -> Path:
    return save_canonical(run, canonical_run_path(run.run_id))


def test_review_queue_returns_only_needs_review_sorted_with_detail():
    client = _ui_client()
    run = _run(_rid("review"), [
        ("low", STATUS_NEEDS_REVIEW, SEVERITY_LOW),
        ("failed", STATUS_FAILED, SEVERITY_CRITICAL),
        ("high", STATUS_NEEDS_REVIEW, SEVERITY_HIGH),
        ("medium", STATUS_NEEDS_REVIEW, SEVERITY_MEDIUM),
        ("passed", STATUS_PASSED, SEVERITY_LOW),
    ])
    _save(run)

    resp = client.get(f"/api/review/{run.run_id}")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert [item["finding_id"] for item in payload["items"]] == ["high", "medium", "low"]
    first = payload["items"][0]
    assert first["case"]["prompt"] == "prompt-high"
    assert first["finding"]["response"] == "response-high"
    assert first["judge"]["confidence"] == 0.82
    assert "detector" in first["detector_rationale"]


def test_review_decision_persists_audit_trail_and_affects_gate():
    client = _ui_client()
    run = _run(_rid("decision"), [("needs", STATUS_NEEDS_REVIEW, SEVERITY_HIGH)])
    _save(run)

    resp = client.post(
        f"/api/review/{run.run_id}/needs/decision",
        json={"decision": "approve", "reviewer": "Ada QA", "notes": "acceptable"},
    )

    assert resp.status_code == 200
    reloaded = load_run(run.run_id)
    finding = reloaded.findings[0]
    assert finding.status == "approved"
    assert finding.reviewers[-1].reviewer_id == "Ada QA"
    assert finding.reviewers[-1].notes == "acceptable"

    gate = client.get(f"/api/gate/{run.run_id}").get_json()
    assert gate["unresolved_review_count"] == 0
    assert gate["decision"]["verdict"] == "GO"


def test_waive_requires_notes_validation():
    client = _ui_client()
    run = _run(_rid("waive"), [("needs", STATUS_NEEDS_REVIEW, SEVERITY_HIGH)])
    _save(run)

    resp = client.post(
        f"/api/review/{run.run_id}/needs/decision",
        json={"decision": "waive", "reviewer": "Ada QA", "notes": ""},
    )

    assert resp.status_code == 400
    assert "notes" in resp.get_json()["error"]


def test_review_queue_includes_baseline_side_by_side():
    client = _ui_client()
    baseline = _run(_rid("base"), [("needs", STATUS_PASSED, SEVERITY_LOW)])
    current = _run(_rid("cur"), [("needs", STATUS_NEEDS_REVIEW, SEVERITY_HIGH)])
    baseline.findings[0].response = "baseline response"
    _save(baseline)
    _save(current)

    resp = client.get(f"/api/review/{current.run_id}?baseline={baseline.run_id}")

    assert resp.status_code == 200
    item = resp.get_json()["items"][0]
    assert item["baseline"]["run_id"] == baseline.run_id
    assert item["baseline"]["response"] == "baseline response"
    assert item["baseline"]["status"] == STATUS_PASSED


def test_gate_endpoint_matches_cli_gate_output(capsys):
    from qval.cli import main

    client = _ui_client()
    baseline = _run(_rid("gate_base"), [("crit", STATUS_PASSED, SEVERITY_LOW)])
    current = _run(_rid("gate_cur"), [("crit", STATUS_FAILED, SEVERITY_CRITICAL)])
    baseline_path = _save(baseline)
    current_path = _save(current)

    rc = main(["gate", "--current", str(current_path), "--baseline", str(baseline_path)])
    out = capsys.readouterr().out
    cli_reasons = [line.strip()[2:] for line in out.splitlines() if line.strip().startswith("- ")]

    resp = client.get(f"/api/gate/{current.run_id}?baseline={baseline.run_id}")

    assert rc == 1
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["decision"]["verdict"] == "NO-GO"
    assert payload["decision"]["rationale"] == cli_reasons
    assert payload["regressions"]
    assert "triggering_policy_rules" in payload


def test_export_round_trip_writes_markdown_html_and_evidence_pack():
    client = _ui_client()
    run = _run(_rid("export"), [("pass", STATUS_PASSED, SEVERITY_LOW)])
    _save(run)

    for fmt, suffix in (("markdown", ".md"), ("html", ".html")):
        resp = client.post(f"/api/export/{run.run_id}", json={"format": fmt})
        assert resp.status_code == 200
        path = Path(resp.get_json()["file_path"])
        assert path.is_file()
        assert path.suffix == suffix

    resp = client.post(f"/api/export/{run.run_id}", json={"format": "evidence-pack"})
    assert resp.status_code == 200
    pack_dir = Path(resp.get_json()["file_path"])
    assert pack_dir.is_dir()
    assert (pack_dir / "manifest.json").is_file()


@pytest.mark.slow
def test_ui_smoke_mock_run_review_gate_export_flow():
    client = _ui_client()

    start = client.post(
        "/api/runs",
        json={"suites": ["bias"], "target": {"type": "mock"}, "limit": 2},
    )
    assert start.status_code == 202
    run_id = start.get_json()["run_id"]

    progress = {}
    for _ in range(100):
        progress = client.get(f"/api/runs/{run_id}/progress").get_json()
        if progress["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)
    assert progress["status"] == "completed"

    queue = client.get(f"/api/review/{run_id}").get_json()["items"]
    assert len(queue) == 2

    first, second = queue
    approve = client.post(
        f"/api/review/{run_id}/{first['finding_id']}/decision",
        json={"decision": "approve", "reviewer": "QA Tester", "notes": "acceptable"},
    )
    waive = client.post(
        f"/api/review/{run_id}/{second['finding_id']}/decision",
        json={"decision": "waive", "reviewer": "QA Tester",
              "notes": "accepted for this release", "expires_at": "2026-12-31"},
    )
    assert approve.status_code == 200
    assert waive.status_code == 200

    gate = client.get(f"/api/gate/{run_id}").get_json()
    assert gate["unresolved_review_count"] == 0
    assert gate["blocked_by_reviews"] is False

    exported = client.post(f"/api/export/{run_id}", json={"format": "markdown"})
    assert exported.status_code == 200
    assert Path(exported.get_json()["file_path"]).is_file()
