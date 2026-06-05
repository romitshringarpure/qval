"""Canonical evidence schema objects and vocabularies (F-01).

Design notes
------------
* **Tool-agnostic.** Nothing here assumes Qval ran the test. Promptfoo and
  DeepEval results map into the same objects as native runs.
* **Versioned.** Every serialized ``CanonicalRun`` carries ``schema_version``
  so importers and consumers can detect mismatches instead of failing silently.
* **Stable contract.** Most objects (Control, Artifact, Decision, Waiver,
  Reviewer, EvidencePack) are lightly used today and filled in by later
  features (F-04, F-07, F-08, F-10). They are defined now so those features
  snap in without reshaping data already written to disk.
* **stdlib only.** Dataclasses + manual ``to_dict``/``from_dict`` to match the
  existing ``qval/engine/schemas.py`` style and keep zero install weight.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# --- Schema version ---------------------------------------------------------
# Bump on any breaking change to the serialized shape. Consumers compare the
# major component and refuse to load an incompatible major version.
SCHEMA_VERSION = "1.0"


# --- Severity vocabulary ----------------------------------------------------
# Canonical adds `info` on top of the native risk levels so that importers
# from tools with non-risk-graded results (e.g. a pure metric pass) have a
# non-alarming bucket to land in.
SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"
ALL_SEVERITIES = (
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO,
)
# Ordered worst -> best, for diffing severity regressions later (F-04).
SEVERITY_RANK = {
    SEVERITY_CRITICAL: 4,
    SEVERITY_HIGH: 3,
    SEVERITY_MEDIUM: 2,
    SEVERITY_LOW: 1,
    SEVERITY_INFO: 0,
}


# --- Status vocabulary ------------------------------------------------------
# Superset of the native PASS/FAIL/NEEDS_REVIEW, adding the governance states
# that the review workflow (F-10) and gate (F-04) introduce.
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_WAIVED = "waived"
STATUS_APPROVED = "approved"
STATUS_BLOCKED = "blocked"
ALL_STATUSES = (
    STATUS_PASSED, STATUS_FAILED, STATUS_NEEDS_REVIEW,
    STATUS_WAIVED, STATUS_APPROVED, STATUS_BLOCKED,
)


# --- Decision vocabulary ----------------------------------------------------
DECISION_GO = "GO"
DECISION_CONDITIONAL_GO = "CONDITIONAL-GO"
DECISION_NO_GO = "NO-GO"
ALL_DECISIONS = (DECISION_GO, DECISION_CONDITIONAL_GO, DECISION_NO_GO)


# --- Native -> canonical mappers --------------------------------------------
# Native run schema uses uppercase PASS/FAIL/NEEDS_REVIEW and risk levels
# without `info`. These translate native vocab into canonical vocab so the
# adapter (and any importer) has one place to reconcile naming.

_NATIVE_STATUS_MAP = {
    "PASS": STATUS_PASSED,
    "FAIL": STATUS_FAILED,
    "NEEDS_REVIEW": STATUS_NEEDS_REVIEW,
}

_NATIVE_SEVERITY_MAP = {
    "critical": SEVERITY_CRITICAL,
    "high": SEVERITY_HIGH,
    "medium": SEVERITY_MEDIUM,
    "low": SEVERITY_LOW,
}


def map_native_status(native_status: str) -> str:
    """Translate a native status (PASS/FAIL/NEEDS_REVIEW) to canonical.

    Raises ValueError on an unknown status rather than guessing -- a silent
    mismap would corrupt every downstream gate decision.
    """
    try:
        return _NATIVE_STATUS_MAP[native_status]
    except KeyError:
        raise ValueError(
            f"unknown native status {native_status!r}; "
            f"expected one of {tuple(_NATIVE_STATUS_MAP)}"
        )


def map_native_severity(native_risk_level: str) -> str:
    """Translate a native risk_level to canonical severity."""
    try:
        return _NATIVE_SEVERITY_MAP[native_risk_level]
    except KeyError:
        raise ValueError(
            f"unknown native risk_level {native_risk_level!r}; "
            f"expected one of {tuple(_NATIVE_SEVERITY_MAP)}"
        )


# --- Objects ----------------------------------------------------------------
# Each object defines from_dict for deserialization. CanonicalRun.to_dict /
# from_dict handle the full nested round-trip including schema_version.


@dataclass
class Control:
    """A governance control a finding maps to (e.g. OWASP-LLM-01).

    Populated by F-07 (control & compliance mapping). Defined now so findings
    can carry control_ids from day one without a schema migration later.
    """

    control_id: str
    framework: str = ""          # e.g. "OWASP-LLM", "NIST-AI-RMF"
    title: str = ""
    owner: str = ""
    evidence_required: bool = False
    waiver_allowed: bool = True

    @classmethod
    def from_dict(cls, raw: dict) -> "Control":
        return cls(
            control_id=raw["control_id"],
            framework=raw.get("framework", ""),
            title=raw.get("title", ""),
            owner=raw.get("owner", ""),
            evidence_required=bool(raw.get("evidence_required", False)),
            waiver_allowed=bool(raw.get("waiver_allowed", True)),
        )


@dataclass
class Artifact:
    """A stored evidence file (prompt dump, response, screenshot, scored JSON).

    Used by the evidence pack (F-08). ``sha256`` enables tamper-evident
    manifests; ``path`` is relative to the evidence pack root.
    """

    artifact_id: str
    kind: str                    # e.g. "prompt", "response", "scored_results"
    path: str
    sha256: str = ""
    media_type: str = "text/plain"

    @classmethod
    def from_dict(cls, raw: dict) -> "Artifact":
        return cls(
            artifact_id=raw["artifact_id"],
            kind=raw["kind"],
            path=raw["path"],
            sha256=raw.get("sha256", ""),
            media_type=raw.get("media_type", "text/plain"),
        )


@dataclass
class Reviewer:
    """A human review decision on a finding (F-10)."""

    reviewer_id: str
    decision: str = ""           # approve / reject / waive
    notes: str = ""
    decided_at: str = ""         # ISO-8601 UTC

    @classmethod
    def from_dict(cls, raw: dict) -> "Reviewer":
        return cls(
            reviewer_id=raw["reviewer_id"],
            decision=raw.get("decision", ""),
            notes=raw.get("notes", ""),
            decided_at=raw.get("decided_at", ""),
        )


@dataclass
class Waiver:
    """An approved exception that lets a known failure ship (F-06/F-10)."""

    waiver_id: str
    reason: str
    approver: str
    approved_at: str = ""        # ISO-8601 UTC
    expires_at: str = ""         # ISO-8601 UTC; empty = no expiry

    @classmethod
    def from_dict(cls, raw: dict) -> "Waiver":
        return cls(
            waiver_id=raw["waiver_id"],
            reason=raw["reason"],
            approver=raw["approver"],
            approved_at=raw.get("approved_at", ""),
            expires_at=raw.get("expires_at", ""),
        )


@dataclass
class Case:
    """A single test that ran -- the input side, tool-agnostic.

    ``source_tool`` records who produced this case ("qval", "promptfoo",
    "deepeval") so the canonical run can mix results from multiple tools.
    """

    case_id: str
    name: str
    category: str
    prompt: str
    expected_behavior: str = ""
    source_tool: str = "qval"
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict) -> "Case":
        return cls(
            case_id=raw["case_id"],
            name=raw.get("name", ""),
            category=raw.get("category", ""),
            prompt=raw.get("prompt", ""),
            expected_behavior=raw.get("expected_behavior", ""),
            source_tool=raw.get("source_tool", "qval"),
            tags=list(raw.get("tags", [])),
            extra=dict(raw.get("extra", {})),
        )


@dataclass
class Finding:
    """A graded outcome for one case -- the result side.

    This is the unit the gate (F-04) diffs and the policy engine (F-06)
    evaluates. ``status`` and ``severity`` use canonical vocabularies.
    ``control_ids`` link to Control objects (F-07). ``reviewers`` / ``waiver``
    are attached by the review workflow (F-10).
    """

    finding_id: str
    case_id: str
    status: str                  # one of ALL_STATUSES
    severity: str                # one of ALL_SEVERITIES
    score: float | None = None
    reason: str = ""
    response: str = ""
    control_ids: list[str] = field(default_factory=list)
    manual_review_required: bool = False
    reviewers: list[Reviewer] = field(default_factory=list)
    waiver: Waiver | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in ALL_STATUSES:
            raise ValueError(
                f"finding {self.finding_id}: invalid status {self.status!r}; "
                f"must be one of {ALL_STATUSES}"
            )
        if self.severity not in ALL_SEVERITIES:
            raise ValueError(
                f"finding {self.finding_id}: invalid severity {self.severity!r}; "
                f"must be one of {ALL_SEVERITIES}"
            )

    @classmethod
    def from_dict(cls, raw: dict) -> "Finding":
        return cls(
            finding_id=raw["finding_id"],
            case_id=raw["case_id"],
            status=raw["status"],
            severity=raw["severity"],
            score=raw.get("score"),
            reason=raw.get("reason", ""),
            response=raw.get("response", ""),
            control_ids=list(raw.get("control_ids", [])),
            manual_review_required=bool(raw.get("manual_review_required", False)),
            reviewers=[Reviewer.from_dict(r) for r in raw.get("reviewers", [])],
            waiver=Waiver.from_dict(raw["waiver"]) if raw.get("waiver") else None,
            extra=dict(raw.get("extra", {})),
        )


@dataclass
class Decision:
    """The release decision produced by the gate (F-04)."""

    verdict: str                 # one of ALL_DECISIONS
    rationale: list[str] = field(default_factory=list)
    decided_at: str = ""         # ISO-8601 UTC
    policy_version: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in ALL_DECISIONS:
            raise ValueError(
                f"decision: invalid verdict {self.verdict!r}; "
                f"must be one of {ALL_DECISIONS}"
            )

    @classmethod
    def from_dict(cls, raw: dict) -> "Decision":
        return cls(
            verdict=raw["verdict"],
            rationale=list(raw.get("rationale", [])),
            decided_at=raw.get("decided_at", ""),
            policy_version=raw.get("policy_version", ""),
        )


@dataclass
class EvidencePack:
    """Metadata for a signed, exportable audit bundle (F-08)."""

    pack_id: str
    mode: str = "internal"       # regulated / internal / public-demo / hash-only
    manifest_sha256: str = ""
    signature: str = ""
    created_at: str = ""         # ISO-8601 UTC
    retention_ttl_days: int | None = None
    artifacts: list[Artifact] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> "EvidencePack":
        return cls(
            pack_id=raw["pack_id"],
            mode=raw.get("mode", "internal"),
            manifest_sha256=raw.get("manifest_sha256", ""),
            signature=raw.get("signature", ""),
            created_at=raw.get("created_at", ""),
            retention_ttl_days=raw.get("retention_ttl_days"),
            artifacts=[Artifact.from_dict(a) for a in raw.get("artifacts", [])],
        )


@dataclass
class CanonicalRun:
    """One eval execution normalized into canonical form -- the top object.

    This is the unit serialized to ``run.json``. Importers emit it; the gate,
    reports, and evidence packs consume it.
    """

    run_id: str
    source_tool: str             # "qval" / "promptfoo" / "deepeval"
    model: str
    provider: str
    started_at: str = ""         # ISO-8601 UTC
    completed_at: str = ""       # ISO-8601 UTC
    suite: str = ""
    environment: str = ""
    prompt_version: str = ""
    cases: list[Case] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    controls: list[Control] = field(default_factory=list)
    decision: Decision | None = None
    evidence_pack: EvidencePack | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        out = asdict(self)
        # asdict recurses dataclasses already; just drop None optionals to keep
        # the JSON clean.
        if self.decision is None:
            out["decision"] = None
        if self.evidence_pack is None:
            out["evidence_pack"] = None
        return out

    @classmethod
    def from_dict(cls, raw: dict) -> "CanonicalRun":
        _check_schema_version(raw.get("schema_version", "0.0"))
        return cls(
            run_id=raw["run_id"],
            source_tool=raw["source_tool"],
            model=raw["model"],
            provider=raw["provider"],
            started_at=raw.get("started_at", ""),
            completed_at=raw.get("completed_at", ""),
            suite=raw.get("suite", ""),
            environment=raw.get("environment", ""),
            prompt_version=raw.get("prompt_version", ""),
            cases=[Case.from_dict(c) for c in raw.get("cases", [])],
            findings=[Finding.from_dict(f) for f in raw.get("findings", [])],
            controls=[Control.from_dict(c) for c in raw.get("controls", [])],
            decision=Decision.from_dict(raw["decision"]) if raw.get("decision") else None,
            evidence_pack=(
                EvidencePack.from_dict(raw["evidence_pack"])
                if raw.get("evidence_pack") else None
            ),
            metadata=dict(raw.get("metadata", {})),
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
        )


def _check_schema_version(version: str) -> None:
    """Refuse to load a canonical run with an incompatible major version."""
    incoming_major = str(version).split(".", 1)[0]
    current_major = SCHEMA_VERSION.split(".", 1)[0]
    if incoming_major != current_major:
        raise ValueError(
            f"canonical run schema_version {version!r} is incompatible with "
            f"this build (expected major {current_major}.x). Re-import the run "
            f"with a matching Qval version."
        )
