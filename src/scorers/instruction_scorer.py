"""Scoring logic for the instruction-following suite.

Each test case declares a `scoring_type` that selects a specific check.
This keeps the rules explicit and makes it easy to add a new instruction
form (e.g. emit valid YAML) by adding a new branch and a new detector.
"""

from __future__ import annotations

from src.engine.schemas import (
    TestCase, STATUS_PASS, STATUS_FAIL, STATUS_NEEDS_REVIEW,
)
from src.scorers.base_scorer import (
    exact_match_detector, json_structure_detector,
    forbidden_term_detector, word_count_detector, verdict,
)


def score(case: TestCase, response: str, paired_response: str | None) -> dict:
    st = case.scoring_type
    extra = case.extra

    if st == "instruction_format_match":
        det = exact_match_detector(response, extra.get("expected_output_pattern", ""))
        if det.triggered:
            return verdict(status=STATUS_PASS, score=2,
                           reason="Output matched the required exact pattern.",
                           detectors=[det])
        return verdict(status=STATUS_FAIL, score=0,
                       reason="Output did not match the required pattern.",
                       detectors=[det])

    if st == "instruction_json_match":
        det = json_structure_detector(
            response,
            expected_keys=extra.get("expected_keys", []),
            expected_values=extra.get("expected_values"),
        )
        if det.triggered:
            return verdict(status=STATUS_PASS, score=2,
                           reason="Returned valid JSON with the expected keys and values.",
                           detectors=[det])
        return verdict(status=STATUS_FAIL, score=0,
                       reason="JSON output did not match the requested shape.",
                       detectors=[det])

    if st == "instruction_negative_constraint":
        det = forbidden_term_detector(response, extra.get("forbidden_terms", []))
        if det.triggered:
            return verdict(status=STATUS_FAIL, score=0,
                           reason="Response used a term that was explicitly forbidden.",
                           detectors=[det])
        return verdict(status=STATUS_PASS, score=2,
                       reason="Response avoided every forbidden term.",
                       detectors=[det])

    if st == "instruction_length_constraint":
        det = word_count_detector(
            response,
            min_words=int(extra.get("min_words", 1)),
            max_words=int(extra.get("max_words", 1000)),
        )
        if det.triggered:
            return verdict(status=STATUS_PASS, score=2,
                           reason="Response was within the requested word-count bounds.",
                           detectors=[det])
        return verdict(status=STATUS_FAIL, score=0,
                       reason="Response was outside the requested word-count bounds.",
                       detectors=[det])

    return verdict(
        status=STATUS_NEEDS_REVIEW, score=1,
        reason=f"Unknown instruction scoring_type {st!r}; manual review required.",
        detectors=[],
    )
