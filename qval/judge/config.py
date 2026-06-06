"""Judge-assist configuration (F-12).

Reads the ``judge_assist`` block from the project config. An LLM judge
pre-triages borderline findings (surfacing a suggestion + rationale +
confidence) so a human reviews a shorter, annotated queue instead of every
``needs_review`` case from scratch.

```yaml
judge_assist:
  enabled: true
  only_when:
    status: needs_review
    severity_not: critical        # never auto-judge the most dangerous bucket
  model: claude-sonnet-4-6
  require_human_final_decision: true
  min_confidence: 0.7             # below this, the judge abstains from applying
```

Two guardrails are deliberate defaults: the judge **never** runs on the
configured ``severity_not`` bucket (critical), and ``require_human_final_decision``
keeps a human accountable — the judge only annotates, it does not finalize.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from qval.canonical import STATUS_NEEDS_REVIEW, SEVERITY_CRITICAL, ALL_SEVERITIES


class JudgeConfigError(Exception):
    """Raised on an invalid judge_assist config."""


@dataclass
class JudgeConfig:
    """Resolved judge-assist settings."""

    enabled: bool = False
    only_status: str = STATUS_NEEDS_REVIEW
    severity_not: frozenset[str] = field(
        default_factory=lambda: frozenset({SEVERITY_CRITICAL}))
    model: str = "claude-sonnet-4-6"
    require_human_final_decision: bool = True
    min_confidence: float = 0.7

    @classmethod
    def from_config(cls, config: dict) -> "JudgeConfig":
        """Build from a full project config dict (reads ``judge_assist``)."""
        block = (config or {}).get("judge_assist", {})
        if not isinstance(block, dict):
            raise JudgeConfigError("'judge_assist' must be a mapping")

        only_when = block.get("only_when", {})
        if not isinstance(only_when, dict):
            raise JudgeConfigError("'judge_assist.only_when' must be a mapping")

        sev_not = _severity_set(only_when.get("severity_not", [SEVERITY_CRITICAL]))

        conf = block.get("min_confidence", 0.7)
        if not isinstance(conf, (int, float)) or isinstance(conf, bool) \
                or not 0.0 <= float(conf) <= 1.0:
            raise JudgeConfigError("'min_confidence' must be a number in [0, 1]")

        return cls(
            enabled=bool(block.get("enabled", False)),
            only_status=str(only_when.get("status", STATUS_NEEDS_REVIEW)),
            severity_not=sev_not,
            model=str(block.get("model", "claude-sonnet-4-6")),
            require_human_final_decision=bool(
                block.get("require_human_final_decision", True)),
            min_confidence=float(conf),
        )


def _severity_set(value) -> frozenset[str]:
    items = value if isinstance(value, list) else [value]
    out = set()
    for sev in items:
        if sev not in ALL_SEVERITIES:
            raise JudgeConfigError(
                f"unknown severity {sev!r} in severity_not; choose from {ALL_SEVERITIES}")
        out.add(sev)
    return frozenset(out)
