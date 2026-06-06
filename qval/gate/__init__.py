"""Release gate engine (F-04).

Two pure modules — ``diff`` (compare two canonical runs) and ``decision``
(turn the diff into a GO / CONDITIONAL-GO / NO-GO verdict) — shared by the
``qval gate`` command and the F-05 report so the logic lives in one place.

    from qval.gate import diff_runs, evaluate, GateThresholds
"""

from .diff import diff_runs, RunDiff, Regression, CategoryDelta
from .decision import evaluate, GateThresholds, POLICY_VERSION

__all__ = [
    "diff_runs", "RunDiff", "Regression", "CategoryDelta",
    "evaluate", "GateThresholds", "POLICY_VERSION",
]
