"""Judge assist for borderline cases (F-12).

An LLM judge pre-triages `needs_review` findings (never `critical`), surfacing a
suggestion + confidence + rationale, with results cached and the human override
always winning.

    from qval.judge import JudgeConfig, run_judge, make_llm_judge
"""

from .config import JudgeConfig, JudgeConfigError
from .cache import JudgeCache
from .assist import (
    run_judge, eligible_findings, JudgeVerdict, JudgeResult,
    JUDGE_PROMPT_VERSION, SUGGEST_APPROVE, SUGGEST_REJECT, SUGGEST_ABSTAIN,
)
from .llm_judge import make_llm_judge, build_prompt, parse_verdict

__all__ = [
    "JudgeConfig", "JudgeConfigError", "JudgeCache",
    "run_judge", "eligible_findings", "JudgeVerdict", "JudgeResult",
    "JUDGE_PROMPT_VERSION", "SUGGEST_APPROVE", "SUGGEST_REJECT", "SUGGEST_ABSTAIN",
    "make_llm_judge", "build_prompt", "parse_verdict",
]
