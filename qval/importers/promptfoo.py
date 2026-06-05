"""Promptfoo importer (F-03).

Maps a Promptfoo ``results.json`` into a ``CanonicalRun``. Promptfoo grades
pass/fail + score but never assigns a risk severity, so findings default to
``info`` (overridable; an explicit ``severity`` in a record's vars/metadata
wins). The parser is tolerant of Promptfoo's format variants — see
``_locate_results``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qval.canonical import (
    CanonicalRun, Case, Finding,
    STATUS_PASSED, STATUS_FAILED,
)
from qval.utils.time_utils import generate_run_id, now_utc_iso
from .base import BaseImporter, resolve_severity, split_provider_model
from .registry import register


class PromptfooImporter(BaseImporter):
    """Importer for Promptfoo eval output."""

    tool_name = "promptfoo"

    def to_canonical(self, data: Any, *, default_severity: str,
                     source: str) -> CanonicalRun:
        records = _locate_results(data)

        cases: list[Case] = []
        findings: list[Finding] = []
        run_provider, run_model = "", ""

        for i, rec in enumerate(records):
            cid = _record_id(rec, i)
            prov, mdl = split_provider_model(_provider_id(rec.get("provider")))
            if not run_provider and prov:
                run_provider, run_model = prov, mdl
            cases.append(_to_case(rec, cid))
            findings.append(
                _to_finding(rec, cid, default_severity, prov, mdl, run_provider)
            )

        return CanonicalRun(
            run_id=generate_run_id(),
            source_tool=self.tool_name,
            model=run_model,
            provider=run_provider,
            started_at=_timestamp(data),
            completed_at=now_utc_iso(),
            suite=_suite_name(data, source),
            cases=cases,
            findings=findings,
            metadata=_run_metadata(data, source),
        )


# --- locating the results array (tolerant) ----------------------------------

def _locate_results(data: Any) -> list:
    """Find the list of result records across Promptfoo format variants.

    Order: ``data['results']['results']`` (modern nested) -> ``data['results']``
    if a list -> ``data`` if a list. Raises ValueError if none match.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        results = data.get("results")
        if isinstance(results, dict) and isinstance(results.get("results"), list):
            return results["results"]
        if isinstance(results, list):
            return results
    raise ValueError(
        "could not locate a Promptfoo results array; expected "
        "data['results']['results'], data['results'] (list), or a top-level list"
    )


# --- per-record field extraction --------------------------------------------

def _record_id(rec: dict, i: int) -> str:
    p, t = rec.get("promptIdx"), rec.get("testIdx")
    if p is not None and t is not None:
        return f"{p}-{t}"
    return str(i)


def _provider_id(provider: Any) -> str:
    if isinstance(provider, dict):
        return provider.get("id") or provider.get("label") or ""
    if isinstance(provider, str):
        return provider
    return ""


def _prompt_text(rec: dict) -> str:
    prompt = rec.get("prompt")
    if isinstance(prompt, dict):
        return prompt.get("raw") or prompt.get("label") or ""
    if isinstance(prompt, str):
        return prompt
    return ""


def _case_name(rec: dict, cid: str) -> str:
    prompt = rec.get("prompt")
    if isinstance(prompt, dict) and prompt.get("label"):
        return prompt["label"]
    return f"case-{cid}"


def _response_text(rec: dict) -> str:
    resp = rec.get("response")
    if isinstance(resp, dict):
        out = resp.get("output", "")
        return out if isinstance(out, str) else json.dumps(out)
    if isinstance(resp, str):
        return resp
    return ""


def _record_severity(rec: dict):
    for container in (rec.get("vars"), rec.get("metadata")):
        if isinstance(container, dict) and container.get("severity"):
            return container["severity"]
    return None


def _to_case(rec: dict, cid: str) -> Case:
    extra: dict[str, Any] = {}
    vars_ = rec.get("vars")
    if isinstance(vars_, dict) and vars_:
        extra["vars"] = vars_
    return Case(
        case_id=cid,
        name=_case_name(rec, cid),
        category="imported",
        prompt=_prompt_text(rec),
        source_tool="promptfoo",
        extra=extra,
    )


def _to_finding(rec: dict, cid: str, default_severity: str,
                prov: str, mdl: str, run_provider: str) -> Finding:
    grading = rec.get("gradingResult") or {}

    passed = grading.get("pass")
    if passed is None:
        passed = rec.get("success")
    status = STATUS_PASSED if passed else STATUS_FAILED

    score = rec.get("score")
    if score is None:
        score = grading.get("score")

    return Finding(
        finding_id=cid,
        case_id=cid,
        status=status,
        severity=resolve_severity(_record_severity(rec), default_severity),
        score=float(score) if score is not None else None,
        reason=grading.get("reason", ""),
        response=_response_text(rec),
        extra=_finding_extra(rec, prov, mdl, run_provider),
    )


def _finding_extra(rec: dict, prov: str, mdl: str, run_provider: str) -> dict:
    """Carry Promptfoo per-result detail that has no first-class canonical home."""
    extra: dict[str, Any] = {}
    grading = rec.get("gradingResult") or {}
    if grading.get("componentResults"):
        extra["assertions"] = grading["componentResults"]
    if rec.get("latencyMs") is not None:
        extra["latency_ms"] = rec["latencyMs"]
    resp = rec.get("response")
    if isinstance(resp, dict):
        if resp.get("tokenUsage") is not None:
            extra["token_usage"] = resp["tokenUsage"]
        if resp.get("cost") is not None:
            extra["cost_usd"] = resp["cost"]
    # Record a per-finding provider only when it differs from the run-level one,
    # so a multi-provider eval stays faithful without bloating every finding.
    if prov and prov != run_provider:
        extra["provider"] = prov
        if mdl:
            extra["model"] = mdl
    return extra


# --- run-level metadata -----------------------------------------------------

def _timestamp(data: Any) -> str:
    if isinstance(data, dict):
        results = data.get("results")
        if isinstance(results, dict) and results.get("timestamp"):
            return results["timestamp"]
    return now_utc_iso()


def _suite_name(data: Any, source: str) -> str:
    if isinstance(data, dict):
        config = data.get("config")
        if isinstance(config, dict) and config.get("description"):
            return config["description"]
    return Path(source).stem if source else ""


def _run_metadata(data: Any, source: str) -> dict:
    meta: dict[str, Any] = {"source_path": source}
    if isinstance(data, dict):
        if data.get("evalId"):
            meta["promptfoo_eval_id"] = data["evalId"]
        results = data.get("results")
        if isinstance(results, dict) and results.get("stats"):
            meta["promptfoo_stats"] = results["stats"]
    return meta


# Self-register on import so the registry / CLI discover this tool.
register(PromptfooImporter())
