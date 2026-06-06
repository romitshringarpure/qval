"""Judge-assist engine (F-12).

Pre-triages borderline findings with an LLM judge, keeping a human accountable.
For each eligible finding it records a ``JudgeVerdict`` (suggestion + confidence
+ rationale) onto ``finding.extra["judge"]`` and stamps the pinned judge model
+ prompt version into ``run.metadata["judge_assist"]``. It only *applies* a
decision (via the F-10 review workflow) when the config explicitly allows it
(``require_human_final_decision: false``) and confidence clears the floor — the
human override always wins.

The judge call is injected (``judge_fn``), so the eligibility, caching,
annotation, and apply logic are all testable offline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from qval.canonical import CanonicalRun, Finding
from qval.review import apply_decision, DECISION_APPROVE, DECISION_REJECT
from .config import JudgeConfig
from .cache import JudgeCache

# Bump when the judge prompt/contract changes, so cached/old verdicts are
# distinguishable and the run records which contract produced them.
JUDGE_PROMPT_VERSION = "judge-v1"

# Judge suggestions. `abstain` = the judge declines (low confidence / unparseable).
SUGGEST_APPROVE = "approve"
SUGGEST_REJECT = "reject"
SUGGEST_ABSTAIN = "abstain"
_SUGGESTIONS = (SUGGEST_APPROVE, SUGGEST_REJECT, SUGGEST_ABSTAIN)

# Judge suggestion -> review decision (only approve/reject are auto-appliable).
_APPLY_DECISION = {SUGGEST_APPROVE: DECISION_APPROVE, SUGGEST_REJECT: DECISION_REJECT}

# judge_fn(prompt, response) -> {"suggestion": str, "confidence": float, "rationale": str}
JudgeFn = Callable[[str, str], dict]


@dataclass
class JudgeVerdict:
    finding_id: str
    suggestion: str
    confidence: float
    rationale: str
    cached: bool = False
    applied: bool = False


@dataclass
class JudgeResult:
    verdicts: list[JudgeVerdict]
    evaluated: int
    cached: int
    applied: int


def eligible_findings(run: CanonicalRun, config: JudgeConfig) -> list[Finding]:
    """Findings the judge may run on: matching status, not an excluded severity."""
    return [
        f for f in run.findings
        if f.status == config.only_status and f.severity not in config.severity_not
    ]


def run_judge(run: CanonicalRun, config: JudgeConfig, judge_fn: JudgeFn, *,
              cache: JudgeCache | None = None) -> JudgeResult:
    """Annotate eligible findings with judge verdicts; optionally apply them."""
    prompt_by_case = {c.case_id: c.prompt for c in run.cases}
    verdicts: list[JudgeVerdict] = []
    cached_n = applied_n = 0

    for f in eligible_findings(run, config):
        prompt = prompt_by_case.get(f.case_id, "")
        response = f.response
        raw, was_cached = _verdict_for(config.model, prompt, response, judge_fn, cache)
        if was_cached:
            cached_n += 1

        verdict = JudgeVerdict(
            finding_id=f.finding_id,
            suggestion=_norm_suggestion(raw.get("suggestion")),
            confidence=_norm_confidence(raw.get("confidence")),
            rationale=str(raw.get("rationale", "")),
            cached=was_cached,
        )

        applied = _maybe_apply(run, f, verdict, config)
        verdict.applied = applied
        if applied:
            applied_n += 1

        f.extra["judge"] = {
            "model": config.model,
            "prompt_version": JUDGE_PROMPT_VERSION,
            "suggestion": verdict.suggestion,
            "confidence": verdict.confidence,
            "rationale": verdict.rationale,
            "applied": applied,
        }
        verdicts.append(verdict)

    if cache is not None:
        cache.save()

    run.metadata["judge_assist"] = {
        "model": config.model,
        "prompt_version": JUDGE_PROMPT_VERSION,
        "require_human_final_decision": config.require_human_final_decision,
        "min_confidence": config.min_confidence,
        "evaluated": len(verdicts),
        "cached": cached_n,
        "applied": applied_n,
    }
    return JudgeResult(verdicts=verdicts, evaluated=len(verdicts),
                       cached=cached_n, applied=applied_n)


# --- internals --------------------------------------------------------------

def _verdict_for(model, prompt, response, judge_fn, cache) -> tuple[dict, bool]:
    if cache is not None:
        key = JudgeCache.key(model, prompt, response)
        hit = cache.get(key)
        if hit is not None:
            return hit, True
    raw = judge_fn(prompt, response)
    if not isinstance(raw, dict):
        raw = {}
    if cache is not None:
        cache.set(JudgeCache.key(model, prompt, response), raw)
    return raw, False


def _maybe_apply(run: CanonicalRun, finding: Finding, verdict: JudgeVerdict,
                 config: JudgeConfig) -> bool:
    """Apply the judge's suggestion only when policy + confidence permit."""
    if config.require_human_final_decision:
        return False
    if verdict.suggestion not in _APPLY_DECISION:
        return False
    if verdict.confidence < config.min_confidence:
        return False
    apply_decision(
        run, finding.finding_id,
        reviewer_id=f"judge:{config.model}",
        decision=_APPLY_DECISION[verdict.suggestion],
        notes=f"[auto, conf={verdict.confidence:.2f}] {verdict.rationale}",
        reason=verdict.rationale or "judge auto-decision",
    )
    return True


def _norm_suggestion(value) -> str:
    s = str(value or "").strip().lower()
    return s if s in _SUGGESTIONS else SUGGEST_ABSTAIN


def _norm_confidence(value) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, c))
