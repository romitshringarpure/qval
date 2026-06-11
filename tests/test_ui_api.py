from __future__ import annotations

import time
from types import SimpleNamespace

import pytest


def _ui_client():
    pytest.importorskip("flask")
    from qval.ui.server import create_app

    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_suites_endpoint_returns_cases_and_control_mappings():
    client = _ui_client()

    resp = client.get("/api/suites")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert "suites" in payload
    assert payload["suites"]
    safety = next(s for s in payload["suites"] if s["name"] == "safety")
    assert safety["case_count"] == len(safety["cases"])
    assert "safety" in safety["categories"]
    assert "critical" in safety["severities"]
    assert safety["control_mappings"]
    first_case = safety["cases"][0]
    assert {
        "id", "name", "category", "severity", "controls", "prompt",
        "expected_behavior",
    }.issubset(first_case)
    assert first_case["controls"]


@pytest.mark.slow
def test_run_lifecycle_against_mock_provider():
    client = _ui_client()

    start = client.post(
        "/api/runs",
        json={
            "suites": ["instruction_following"],
            "target": {"type": "mock"},
            "limit": 1,
        },
    )

    assert start.status_code == 202
    run_id = start.get_json()["run_id"]

    progress = {}
    for _ in range(100):
        progress_resp = client.get(f"/api/runs/{run_id}/progress")
        assert progress_resp.status_code == 200
        progress = progress_resp.get_json()
        if progress["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)

    assert progress["status"] == "completed"
    assert progress["completed"] == progress["total"] == 1

    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200
    run = detail.get_json()
    assert run["run_id"] == run_id
    assert run["provider"] == "mock"
    assert len(run["cases"]) == 1
    assert len(run["findings"]) == 1
    assert run["findings"][0]["case_id"] == run["cases"][0]["case_id"]

    history = client.get("/api/runs").get_json()["runs"]
    assert any(item["run_id"] == run_id for item in history)


def test_post_run_rejects_api_key_anywhere():
    client = _ui_client()

    resp = client.post(
        "/api/runs",
        json={
            "suites": ["safety"],
            "target": {
                "type": "http",
                "url": "https://example.invalid/chat",
                "headers": {"Authorization": "Bearer ${TOKEN}"},
                "api_key": "secret",
            },
        },
    )

    assert resp.status_code == 400
    assert "api_key" in resp.get_json()["error"]


def test_ui_command_binds_to_localhost_only(monkeypatch):
    from qval.commands import ui

    captured = {}

    class FakeApp:
        def run(self, *, host, port, debug):
            captured.update(host=host, port=port, debug=debug)

    monkeypatch.setattr(ui, "_load_create_app", lambda: lambda: FakeApp())

    rc = ui.run(SimpleNamespace(port=9999))

    assert rc == 0
    assert captured == {"host": "127.0.0.1", "port": 9999, "debug": False}


def test_ui_command_missing_flask_prints_optional_extra_hint(monkeypatch, capsys):
    from qval.commands import ui

    def missing():
        raise RuntimeError("pip install qval[ui]")

    monkeypatch.setattr(ui, "_load_create_app", missing)

    rc = ui.run(SimpleNamespace(port=8642))

    assert rc == 1
    assert "pip install qval[ui]" in capsys.readouterr().out
