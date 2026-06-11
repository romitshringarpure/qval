"""Review queue API helpers shared by the local UI."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from qval.canonical import STATUS_NEEDS_REVIEW
from qval.canonical.io import save_canonical
from qval.engine.run_service import canonical_run_path, load_run
from qval.review.workflow import (
    ALL_DECISIONS,
    DECISION_WAIVE,
    ReviewError,
    apply_decision,
    review_queue,
)


def review_queue_payload(run_id: str, baseline_id: str | None = None) -> dict[str, Any]:
    """Return unresolved NEEDS_REVIEW findings for the UI queue."""

    run = load_run(run_id)
    baseline = load_run(baseline_id) if baseline_id else None
    finding_by_id = {f.finding_id: f for f in run.findings}
    case_by_id = {c.case_id: c for c in run.cases}

    items = []
    for item in review_queue(run, baseline):
        if item.status != STATUS_NEEDS_REVIEW:
            continue
        finding = finding_by_id[item.finding_id]
        case = case_by_id.get(finding.case_id)
        items.append(_item_payload(item, finding, case, baseline_id))

    return {
        "run_id": run_id,
        "baseline_run_id": baseline_id,
        "total": len(items),
        "items": items,
    }


def record_decision(run_id: str, finding_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Validate, apply, and persist a UI review decision."""

    decision = str(body.get("decision", "")).strip()
    reviewer = str(body.get("reviewer") or body.get("reviewer_name") or "").strip()
    notes = str(body.get("notes", "")).strip()
    expires_at = str(body.get("expires_at") or body.get("expiry_date") or "").strip()

    if decision not in ALL_DECISIONS:
        raise ReviewError(f"unknown decision {decision!r}; choose from {ALL_DECISIONS}")
    if not reviewer:
        raise ReviewError("a reviewer name is required")
    if decision == DECISION_WAIVE and not notes:
        raise ReviewError("notes are required for waive decisions")

    run = load_run(run_id)
    finding = apply_decision(
        run,
        finding_id,
        reviewer_id=reviewer,
        decision=decision,
        notes=notes,
        reason=notes if decision == DECISION_WAIVE else "",
        expires_at=expires_at if decision == DECISION_WAIVE else "",
    )
    save_canonical(run, canonical_run_path(run_id))
    return {
        "run_id": run_id,
        "finding": asdict(finding),
    }


def _item_payload(item, finding, case, baseline_id: str | None) -> dict[str, Any]:
    return {
        "finding_id": item.finding_id,
        "case_id": item.case_id,
        "name": item.name,
        "category": item.category,
        "severity": item.severity,
        "status": item.status,
        "owner": item.owner,
        "last_decision": item.last_decision,
        "case": asdict(case) if case else {},
        "finding": asdict(finding),
        "baseline": {
            "run_id": baseline_id,
            "status": item.baseline_status,
            "response": item.baseline_response,
        },
        "judge": dict(finding.extra.get("judge", {})),
        "detector_rationale": _detector_rationale(finding),
    }


def _detector_rationale(finding) -> str:
    detectors = finding.extra.get("detectors") or []
    if not detectors:
        return finding.reason
    lines = []
    for detector in detectors:
        name = detector.get("name", "")
        triggered = bool(detector.get("triggered", False))
        matches = ", ".join(str(item) for item in detector.get("matches", []))
        notes = detector.get("notes", "")
        suffix = f" matches={matches}" if matches else ""
        lines.append(f"{name}: triggered={triggered}{suffix} {notes}".strip())
    return "\n".join(lines)
