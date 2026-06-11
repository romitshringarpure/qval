"""Flask app factory and REST routes for the local Qval console."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

try:
    from flask import Flask, jsonify, render_template, request
except ModuleNotFoundError as exc:  # pragma: no cover - exercised via command tests
    if exc.name == "flask":
        raise RuntimeError("pip install qval[ui]") from exc
    raise

from qval.engine.run_service import execute_run, list_run_history, load_run
from qval.engine.suite_service import list_suite_library
from qval.gate.service import gate_payload
from qval.project import get_active_project
from qval.reports.export_service import export_run
from qval.review.service import record_decision, review_queue_payload
from qval.review.workflow import ReviewError
from qval.utils.file_loader import ALL_SUITES
from qval.utils.time_utils import generate_run_id


@dataclass
class RunJob:
    run_id: str
    status: str = "queued"
    completed: int = 0
    total: int = 0
    current_case_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "completed": self.completed,
            "total": self.total,
            "current_case_id": self.current_case_id,
            "error": self.error,
        }


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    jobs: dict[str, RunJob] = {}
    jobs_lock = threading.Lock()

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/project")
    def project():
        proj = get_active_project()
        return jsonify({
            "root": str(proj.root),
            "paths": {
                "config": str(proj.config_dir),
                "suites": str(proj.test_cases_dir),
                "outputs": str(proj.outputs_dir),
            },
        })

    @app.get("/api/suites")
    def suites():
        return jsonify({"suites": list_suite_library()})

    @app.get("/api/runs")
    def runs():
        return jsonify({"runs": list_run_history()})

    @app.get("/api/runs/<run_id>")
    def run_detail(run_id: str):
        try:
            run = load_run(run_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify(run.to_dict())

    @app.post("/api/runs")
    def start_run():
        payload = request.get_json(silent=True) or {}
        if _contains_api_key(payload):
            return jsonify({"error": "api_key fields are not accepted; use environment variables"}), 400

        try:
            suites = _parse_suites(payload.get("suites"))
            target = _parse_target(payload)
            limit = _optional_int(payload.get("limit"), "limit")
            per_suite_limit = _optional_int(payload.get("per_suite_limit"), "per_suite_limit")
            seed = _optional_int(payload.get("seed"), "seed") or 42
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        run_id = generate_run_id()
        job = RunJob(run_id=run_id)
        with jobs_lock:
            jobs[run_id] = job

        thread = threading.Thread(
            target=_run_in_background,
            args=(job, jobs_lock, suites, target, limit, per_suite_limit, seed),
            daemon=True,
        )
        thread.start()
        return jsonify({"run_id": run_id}), 202

    @app.get("/api/runs/<run_id>/progress")
    def run_progress(run_id: str):
        with jobs_lock:
            job = jobs.get(run_id)
            if job is not None:
                return jsonify(job.to_dict())

        try:
            run = load_run(run_id)
        except ValueError:
            return jsonify({"error": f"run not found: {run_id}"}), 404
        total = len(run.cases)
        return jsonify({
            "run_id": run_id,
            "status": "completed",
            "completed": total,
            "total": total,
            "current_case_id": None,
            "error": None,
        })

    @app.get("/api/review/<run_id>")
    def review_queue_endpoint(run_id: str):
        baseline_id = request.args.get("baseline") or None
        try:
            return jsonify(review_queue_payload(run_id, baseline_id))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.post("/api/review/<run_id>/<finding_id>/decision")
    def review_decision_endpoint(run_id: str, finding_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(record_decision(run_id, finding_id, payload))
        except ReviewError as exc:
            return jsonify({"error": str(exc)}), 400
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.get("/api/gate/<run_id>")
    def gate_endpoint(run_id: str):
        baseline_id = request.args.get("baseline") or None
        try:
            return jsonify(gate_payload(run_id, baseline_id))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.post("/api/export/<run_id>")
    def export_endpoint(run_id: str):
        payload = request.get_json(silent=True) or {}
        fmt = str(payload.get("format", "")).strip()
        try:
            path = export_run(run_id, fmt)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"run_id": run_id, "format": fmt, "file_path": str(path)})

    return app


def _run_in_background(job: RunJob, lock: threading.Lock, suites: list[str],
                       target: dict[str, Any], limit: int | None,
                       per_suite_limit: int | None, seed: int) -> None:
    def update(completed: int, total: int, current_case_id: str | None) -> None:
        with lock:
            job.completed = completed
            job.total = total
            job.current_case_id = current_case_id

    with lock:
        job.status = "running"
    try:
        execute_run(
            suites=suites,
            target_config=target,
            limit=limit,
            per_suite_limit=per_suite_limit,
            seed=seed,
            run_id=job.run_id,
            progress_fn=update,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the local UI
        with lock:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
        return
    with lock:
        job.status = "completed"
        job.current_case_id = None


def _parse_suites(raw: Any) -> list[str]:
    if isinstance(raw, str):
        suites = [raw]
    elif isinstance(raw, list):
        suites = [str(item) for item in raw]
    else:
        suites = []
    if not suites:
        raise ValueError("suites must include at least one suite name")
    invalid = [suite for suite in suites if suite != "all" and suite not in ALL_SUITES]
    if invalid:
        raise ValueError(f"unknown suite(s): {', '.join(invalid)}")
    return suites


def _parse_target(payload: dict[str, Any]) -> dict[str, Any]:
    target = payload.get("target_config") or payload.get("target") or {"type": "mock"}
    if not isinstance(target, dict):
        raise ValueError("target must be an object")
    return dict(target)


def _optional_int(value: Any, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if number < 1:
        raise ValueError(f"{name} must be at least 1")
    return number


def _contains_api_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() == "api_key":
                return True
            if _contains_api_key(nested):
                return True
    if isinstance(value, list):
        return any(_contains_api_key(item) for item in value)
    return False
