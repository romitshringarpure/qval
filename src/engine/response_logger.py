"""Per-run evidence logging.

Every run gets a sealed evidence pack at outputs/evidence/<run_id>/, which
mirrors how a QA team would archive release-candidate test runs. The pack
is what an auditor or compliance reviewer would ask for after the fact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from src.engine.schemas import TestResult, RunSummary, STATUS_NEEDS_REVIEW
from src.utils.file_loader import OUTPUTS_DIR, write_csv, write_json, write_text


MANUAL_REVIEW_FIELDS = [
    "run_id", "test_id", "category", "prompt", "response",
    "risk_level", "reason_for_review",
    "reviewer_decision", "reviewer_notes",
]


class ResponseLogger:
    """Writes evidence files for one run."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.evidence_dir = OUTPUTS_DIR / "evidence" / run_id
        self.results_dir = OUTPUTS_DIR / "results"
        self.raw_dir = OUTPUTS_DIR / "raw_responses"
        self.logs_dir = OUTPUTS_DIR / "logs"
        for d in (self.evidence_dir, self.results_dir, self.raw_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)

    def write_raw_prompts(self, results: Iterable[TestResult]) -> None:
        payload = [
            {
                "test_id": r.test_id,
                "category": r.category,
                "prompt": r.prompt,
                "paired_prompt": r.paired_prompt,
            }
            for r in results
        ]
        write_json(self.evidence_dir / "raw_prompts.json", payload)

    def write_raw_responses(self, results: Iterable[TestResult]) -> None:
        payload = [
            {
                "test_id": r.test_id,
                "category": r.category,
                "model": r.model,
                "provider": r.provider,
                "temperature": r.temperature,
                "timestamp": r.timestamp,
                "latency_ms": r.latency_ms,
                "response": r.response,
                "paired_response": r.paired_response,
                "error": r.error,
            }
            for r in results
        ]
        write_json(self.evidence_dir / "raw_responses.json", payload)
        write_json(self.raw_dir / f"{self.run_id}.json", payload)

    def write_scored_results(self, results: Iterable[TestResult]) -> None:
        payload = [r.to_dict() for r in results]
        write_json(self.evidence_dir / "scored_results.json", payload)
        write_json(self.results_dir / f"{self.run_id}.json", payload)

    def write_manual_review(self, results: Iterable[TestResult]) -> None:
        rows = []
        for r in results:
            if r.status != STATUS_NEEDS_REVIEW and not r.manual_review_required:
                continue
            rows.append({
                "run_id": r.run_id,
                "test_id": r.test_id,
                "category": r.category,
                "prompt": r.prompt,
                "response": r.response,
                "risk_level": r.risk_level,
                "reason_for_review": r.scoring_reason,
                "reviewer_decision": "",
                "reviewer_notes": "",
            })
        write_csv(self.evidence_dir / "manual_review_items.csv", rows, MANUAL_REVIEW_FIELDS)

    def write_summary(self, summary: RunSummary) -> None:
        write_json(self.evidence_dir / "summary.json", summary.__dict__)

    def write_run_log(self, log_lines: list[str]) -> None:
        write_text(self.logs_dir / f"{self.run_id}.log", "\n".join(log_lines) + "\n")
