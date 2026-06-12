"""Promptfoo exporter (F-17).

Renders a qval suite into a ``promptfooconfig.yaml`` the user can run with
``promptfoo eval``. Each qval case becomes a promptfoo *test*: the prompt goes
to ``vars.input`` and the suite-level prompt template is ``{{input}}``.

Mapping (best-effort, fidelity-honest):
* ``expected_behavior`` -> an ``llm-rubric`` assert (the faithful general check;
  needs an LLM grader configured in promptfoo).
* Detectors with a crisp deterministic equivalent -> an extra assert
  (``refusal_detector`` -> ``icontains-any`` of refusal markers). Detectors with
  no equivalent are listed as commented placeholders in the file header rather
  than silently dropped.
* ``paired_prompt`` -> two tests sharing a ``metadata.paired_group`` tag.
* ``risk_level`` / ``manual_review_required`` / ``scoring_type`` / ``tags`` ->
  ``tests[].metadata`` (preserved for filtering, not enforced by promptfoo).

promptfoo schema researched before writing this mapping:
* config structure: https://www.promptfoo.dev/docs/configuration/reference/
* assertion types:  https://www.promptfoo.dev/docs/configuration/expected-outputs/
"""
from __future__ import annotations

import yaml

from qval.engine.schemas import TestCase
from .base import BaseExporter, ExportResult
from .fidelity import FidelityReport, CLEAN, APPROXIMATED, DEGRADED
from .registry import register

# Cited in the generated file header so a reader can verify the mapping.
DOC_REFERENCE = "https://www.promptfoo.dev/docs/configuration/reference/"
DOC_ASSERTIONS = "https://www.promptfoo.dev/docs/configuration/expected-outputs/"

#: A runnable default — the user swaps this for their target in the config.
PROVIDER_PLACEHOLDER = "openai:gpt-4o"

#: Common refusal markers for the deterministic refusal check.
REFUSAL_MARKERS = [
    "I can't", "I cannot", "I'm unable", "I am unable",
    "I won't", "I will not", "I am not able", "I'm not able",
]


def _refusal_assert() -> dict:
    return {"type": "icontains-any", "value": list(REFUSAL_MARKERS),
            "metric": "refusal_detector"}


#: qval detector -> a factory for its deterministic promptfoo assert. Detectors
#: absent here have no crisp equivalent and become commented placeholders.
DETECTOR_ASSERTS = {
    "refusal_detector": _refusal_assert,
}


class PromptfooExporter(BaseExporter):
    """Exporter for promptfoo (``promptfooconfig.yaml``)."""

    tool_name = "promptfoo"
    default_extension = ".yaml"

    def export_suite(self, cases: list[TestCase], suite_name: str) -> ExportResult:
        tests: list[dict] = []
        for case in cases:
            if case.paired_prompt:
                tests.append(_test(case, case.prompt, case.id, paired_group=case.id))
                tests.append(_test(case, case.paired_prompt, f"{case.id}-paired",
                                   paired_group=case.id))
            else:
                tests.append(_test(case, case.prompt, case.id))

        config = {
            "description": f"qval suite '{suite_name}' exported to promptfoo",
            "providers": [PROVIDER_PLACEHOLDER],
            "prompts": ["{{input}}"],
            "tests": tests,
        }
        body = yaml.safe_dump(config, sort_keys=False, allow_unicode=True,
                              default_flow_style=False)
        text = _header(cases, suite_name, len(tests)) + body

        return ExportResult(text=text,
                            fidelity=_fidelity(cases, suite_name, len(tests)))


def _test(case: TestCase, prompt: str, qid: str,
          paired_group: str | None = None) -> dict:
    """Build one promptfoo test dict from a qval case + a concrete prompt."""
    asserts: list[dict] = [
        {"type": "llm-rubric", "value": case.expected_behavior,
         "metric": "expected_behavior"},
    ]
    for det in case.detectors:
        factory = DETECTOR_ASSERTS.get(det)
        if factory is not None:
            asserts.append(factory())

    metadata = {
        "qval_id": qid,
        "category": case.category,
        "risk_level": case.risk_level,
        "manual_review_required": case.manual_review_required,
        "scoring_type": case.scoring_type,
        "tags": list(case.tags),
    }
    if paired_group is not None:
        metadata["paired_group"] = paired_group

    return {
        "description": f"{qid} · {case.name}",
        "vars": {"input": prompt},
        "assert": asserts,
        "metadata": metadata,
    }


def _unsupported_by_case(cases: list[TestCase]) -> list[tuple[str, list[str]]]:
    """(case_id, [detectors with no promptfoo equivalent]) for non-empty cases."""
    rows = []
    for case in cases:
        missing = [d for d in case.detectors if d not in DETECTOR_ASSERTS]
        if missing:
            rows.append((case.id, missing))
    return rows


def _header(cases: list[TestCase], suite_name: str, n_tests: int) -> str:
    """A leading ``#`` comment block (PyYAML can't carry inline comments).

    Holds the cited schema URLs, the provider note, and the per-case
    'commented placeholder' for detectors promptfoo can't express.
    """
    lines = [
        "# promptfoo config — generated by `qval export promptfoo` (F-17)",
        f"# suite: {suite_name}   |   {len(cases)} qval cases -> {n_tests} promptfoo tests",
        "#",
        f"# config schema:   {DOC_REFERENCE}",
        f"# assertion types: {DOC_ASSERTIONS}",
        "#",
        f"# `providers` defaults to {PROVIDER_PLACEHOLDER} — change it to your target.",
        "# Each qval `expected_behavior` became an `llm-rubric` assert (needs an LLM grader).",
    ]
    unsupported = _unsupported_by_case(cases)
    if unsupported:
        lines += [
            "#",
            "# Detectors with no promptfoo equivalent were NOT asserted. Add your own",
            "# `llm-rubric` / `javascript` asserts for these where you need them:",
        ]
        for case_id, missing in unsupported:
            lines.append(f"#   {case_id}: {', '.join(missing)}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _fidelity(cases: list[TestCase], suite_name: str, n_tests: int) -> FidelityReport:
    report = FidelityReport(
        tool="promptfoo", suite=suite_name,
        summary=f"{len(cases)} qval cases -> {n_tests} promptfoo tests.",
    )
    paired_ids = [c.id for c in cases if c.paired_prompt]
    approximated = sorted({d for c in cases for d in c.detectors
                           if d in DETECTOR_ASSERTS})
    unsupported = sorted({d for c in cases for d in c.detectors
                          if d not in DETECTOR_ASSERTS})

    report.add("prompt", CLEAN, "-> vars.input")
    report.add("expected_behavior", CLEAN, "-> llm-rubric assert")
    report.add("name / description", CLEAN, "-> test description")
    report.add(
        "paired_bias_prompts",
        CLEAN if paired_ids else DEGRADED,
        f"{len(paired_ids)} case(s) expanded to two tests sharing metadata.paired_group"
        if paired_ids else "no paired cases in this suite",
        case_ids=paired_ids,
    )
    det_note = []
    if approximated:
        det_note.append(f"approximated -> deterministic assert: {', '.join(approximated)}")
    if unsupported:
        det_note.append(f"no equivalent (commented placeholder only): {', '.join(unsupported)}")
    report.add("detectors", APPROXIMATED if not unsupported else DEGRADED,
               "; ".join(det_note) or "none")
    report.add("risk_level", DEGRADED, "-> tests[].metadata.risk_level (not enforced)")
    report.add("manual_review_required", DEGRADED,
               "-> tests[].metadata.manual_review_required (not enforced)")
    report.add("scoring_type", DEGRADED, "-> tests[].metadata.scoring_type (informational)")
    report.add("tags", DEGRADED, "-> tests[].metadata.tags")
    return report


# Self-register on import so the registry / CLI discover this tool.
register(PromptfooExporter())
