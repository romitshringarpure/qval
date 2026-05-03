"""Domain schemas for test cases, model responses, and run results.

Using dataclasses (not raw dicts) for in-memory work makes the runner and
scorers easier to read, and gives us a single place to validate the JSON
test-case format on load. JSON files remain the source of truth on disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# --- Status & risk levels ---------------------------------------------------

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
ALL_STATUSES = (STATUS_PASS, STATUS_FAIL, STATUS_NEEDS_REVIEW)

RISK_CRITICAL = "critical"
RISK_HIGH = "high"
RISK_MEDIUM = "medium"
RISK_LOW = "low"
ALL_RISK_LEVELS = (RISK_CRITICAL, RISK_HIGH, RISK_MEDIUM, RISK_LOW)


REQUIRED_TEST_FIELDS = (
    "id",
    "category",
    "name",
    "description",
    "risk_level",
    "prompt",
    "expected_behavior",
    "scoring_type",
    "detectors",
)


def validate_test_case_dict(raw: dict, source: str = "<unknown>") -> None:
    """Cheap, explicit schema validation. Raises ValueError on bad input.

    A QA framework should fail loud on a malformed test case rather than
    silently ignore it — the test author needs to know.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: each test case must be an object, got {type(raw).__name__}")

    for f in REQUIRED_TEST_FIELDS:
        if f not in raw:
            raise ValueError(f"{source}: test case is missing required field '{f}': {raw.get('id', '?')}")

    if raw["risk_level"] not in ALL_RISK_LEVELS:
        raise ValueError(
            f"{source}: test {raw['id']} has invalid risk_level={raw['risk_level']!r}; "
            f"must be one of {ALL_RISK_LEVELS}"
        )

    if not isinstance(raw["detectors"], list) or not raw["detectors"]:
        raise ValueError(f"{source}: test {raw['id']} must declare at least one detector")

    if raw.get("paired_prompt") is not None and not isinstance(raw["paired_prompt"], str):
        raise ValueError(f"{source}: test {raw['id']} paired_prompt must be a string if present")


# --- Dataclasses ------------------------------------------------------------

@dataclass
class TestCase:
    """In-memory representation of a single test case from the JSON suite."""

    id: str
    category: str
    name: str
    description: str
    risk_level: str
    prompt: str
    expected_behavior: str
    scoring_type: str
    detectors: list[str]
    paired_prompt: str | None = None
    manual_review_required: bool = False
    tags: list[str] = field(default_factory=list)
    # scoring_type-specific extras (kept loose so adding a new scoring type
    # does not require touching this dataclass):
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict, source: str = "<unknown>") -> "TestCase":
        validate_test_case_dict(raw, source=source)
        known = {f for f in (
            "id", "category", "name", "description", "risk_level",
            "prompt", "expected_behavior", "scoring_type", "detectors",
            "paired_prompt", "manual_review_required", "tags",
        )}
        extra = {k: v for k, v in raw.items() if k not in known}
        return cls(
            id=raw["id"],
            category=raw["category"],
            name=raw["name"],
            description=raw["description"],
            risk_level=raw["risk_level"],
            prompt=raw["prompt"],
            expected_behavior=raw["expected_behavior"],
            scoring_type=raw["scoring_type"],
            detectors=list(raw["detectors"]),
            paired_prompt=raw.get("paired_prompt"),
            manual_review_required=bool(raw.get("manual_review_required", False)),
            tags=list(raw.get("tags", [])),
            extra=extra,
        )


@dataclass
class ModelResponse:
    """Result from a single model call."""

    text: str
    latency_ms: int
    model: str
    provider: str
    error: str | None = None


@dataclass
class DetectorResult:
    """Output of one detector applied to one response."""

    name: str
    triggered: bool
    matches: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class TestResult:
    """Full record of one executed test case."""

    run_id: str
    test_id: str
    category: str
    test_name: str
    description: str
    expected_behavior: str
    risk_level: str
    prompt: str
    response: str
    paired_prompt: str | None
    paired_response: str | None
    model: str
    provider: str
    temperature: float
    timestamp: str
    latency_ms: int
    status: str
    score: int
    scoring_reason: str
    manual_review_required: bool
    detector_results: list[DetectorResult]
    error: str | None = None

    def to_dict(self) -> dict:
        out = asdict(self)
        out["detector_results"] = [asdict(d) for d in self.detector_results]
        return out


@dataclass
class RunSummary:
    """Aggregate metrics for one full run."""

    run_id: str
    started_at: str
    completed_at: str
    suite: str
    model: str
    provider: str
    temperature: float
    total_tests: int
    pass_count: int
    fail_count: int
    needs_review_count: int
    error_count: int
    pass_rate: float
    weighted_pass_rate: float
    average_score: float
    by_category: dict[str, dict[str, Any]]
    critical_failures: list[str]
    high_risk_failures: list[str]
    report_path: str
    evidence_dir: str
