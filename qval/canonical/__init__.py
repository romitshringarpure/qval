"""Qval canonical evidence schema (F-01).

The canonical schema is the tool-agnostic data model that sits *above* the
native Qval run schema (``src/engine/schemas.py``). Native runs, Promptfoo
imports, and DeepEval imports all normalize INTO this shape, which lets every
downstream governance feature -- baseline diff, release gate, reports, evidence
packs -- operate on a single stable contract regardless of which eval tool
produced the results.

Public API:
    from qval.canonical import (
        CanonicalRun, Case, Finding, Control, Artifact,
        Decision, Waiver, Reviewer, EvidencePack,
        SCHEMA_VERSION,
    )
    from qval.canonical.adapter import run_summary_to_canonical
"""

from .schema import (
    SCHEMA_VERSION,
    # severity vocabulary
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO,
    ALL_SEVERITIES,
    # status vocabulary
    STATUS_PASSED, STATUS_FAILED, STATUS_NEEDS_REVIEW,
    STATUS_WAIVED, STATUS_APPROVED, STATUS_BLOCKED,
    ALL_STATUSES,
    # decision vocabulary
    DECISION_GO, DECISION_CONDITIONAL_GO, DECISION_NO_GO,
    ALL_DECISIONS,
    # objects
    CanonicalRun, Case, Finding, Control, Artifact,
    Decision, Waiver, Reviewer, EvidencePack,
    # mappers
    map_native_status, map_native_severity,
)

__all__ = [
    "SCHEMA_VERSION",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "SEVERITY_INFO", "ALL_SEVERITIES",
    "STATUS_PASSED", "STATUS_FAILED", "STATUS_NEEDS_REVIEW",
    "STATUS_WAIVED", "STATUS_APPROVED", "STATUS_BLOCKED", "ALL_STATUSES",
    "DECISION_GO", "DECISION_CONDITIONAL_GO", "DECISION_NO_GO", "ALL_DECISIONS",
    "CanonicalRun", "Case", "Finding", "Control", "Artifact",
    "Decision", "Waiver", "Reviewer", "EvidencePack",
    "map_native_status", "map_native_severity",
]
