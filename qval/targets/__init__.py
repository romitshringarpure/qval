"""Evaluation targets (F-11).

Beyond direct model-provider SDKs, Qval can evaluate any HTTP/API target from
config — internal chatbots, API wrappers, agentic services.

    from qval.targets import HttpTarget, HttpClient
"""

from .http_target import (
    HttpTarget, HttpClient, TargetConfigError, extract_path,
)

__all__ = ["HttpTarget", "HttpClient", "TargetConfigError", "extract_path"]
