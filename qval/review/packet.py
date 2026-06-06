"""Decision packet export (F-10).

Turns a reviewed run into a portable record of *who decided what, when, and why*
— the artifact a compliance team files. JSON keeps the full audit trail (every
reviewer entry per finding); CSV is one row per finding (latest decision) for a
spreadsheet or ticket.
"""
from __future__ import annotations

import csv
import io
import json

from qval.canonical import CanonicalRun
from qval.utils.time_utils import now_utc_iso
from .workflow import owner_of

# CSV columns — one row per finding, latest decision summarized.
CSV_FIELDS = [
    "finding_id", "case_id", "category", "severity", "status", "owner",
    "decisions", "last_decision", "last_reviewer", "last_decided_at",
    "last_notes", "waiver_reason", "waiver_expires",
]


def _row(finding) -> dict:
    last = finding.reviewers[-1] if finding.reviewers else None
    waiver = finding.waiver
    return {
        "finding_id": finding.finding_id,
        "case_id": finding.case_id,
        "category": "",  # filled by caller (needs run.cases)
        "severity": finding.severity,
        "status": finding.status,
        "owner": owner_of(finding),
        "decisions": len(finding.reviewers),
        "last_decision": last.decision if last else "",
        "last_reviewer": last.reviewer_id if last else "",
        "last_decided_at": last.decided_at if last else "",
        "last_notes": last.notes if last else "",
        "waiver_reason": waiver.reason if waiver else "",
        "waiver_expires": waiver.expires_at if waiver else "",
    }


def decision_rows(run: CanonicalRun) -> list[dict]:
    """One summary row per finding (latest decision), category resolved."""
    cat_by_case = {c.case_id: c.category for c in run.cases}
    rows = []
    for f in run.findings:
        row = _row(f)
        row["category"] = cat_by_case.get(f.case_id, "")
        rows.append(row)
    return rows


def to_csv(run: CanonicalRun) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for row in decision_rows(run):
        writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})
    return buf.getvalue()


def to_json(run: CanonicalRun) -> str:
    """Full packet: every finding with its complete reviewer audit trail."""
    cat_by_case = {c.case_id: c.category for c in run.cases}
    packet = {
        "run_id": run.run_id,
        "generated_at": now_utc_iso(),
        "findings": [
            {
                "finding_id": f.finding_id,
                "case_id": f.case_id,
                "category": cat_by_case.get(f.case_id, ""),
                "severity": f.severity,
                "status": f.status,
                "owner": owner_of(f),
                "reviewers": [
                    {
                        "reviewer_id": r.reviewer_id, "decision": r.decision,
                        "notes": r.notes, "decided_at": r.decided_at,
                    }
                    for r in f.reviewers
                ],
                "waiver": (
                    {
                        "waiver_id": f.waiver.waiver_id, "reason": f.waiver.reason,
                        "approver": f.waiver.approver,
                        "approved_at": f.waiver.approved_at,
                        "expires_at": f.waiver.expires_at,
                    }
                    if f.waiver else None
                ),
            }
            for f in run.findings
        ],
    }
    return json.dumps(packet, indent=2, ensure_ascii=False) + "\n"
