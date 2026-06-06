"""F-12 · Judge assist tests.

Covers config parsing, eligibility (needs_review, never critical), the assist
engine (annotation, metadata stamp, apply gating, caching), the LLM judge_fn
parsing, and the `qval judge` CLI.
"""
from __future__ import annotations

import json

import pytest

from qval.canonical import (
    CanonicalRun, Case, Finding,
    STATUS_NEEDS_REVIEW, STATUS_FAILED, STATUS_APPROVED, STATUS_BLOCKED,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
)
from qval.canonical.io import save_canonical, load_canonical
from qval.judge import (
    JudgeConfig, JudgeConfigError, JudgeCache, run_judge, eligible_findings,
    make_llm_judge, parse_verdict, JUDGE_PROMPT_VERSION,
)


# --- helpers ----------------------------------------------------------------

def run_of(specs):
    """specs: list of (fid, status, severity)."""
    cases, findings = [], []
    for fid, status, sev in specs:
        cases.append(Case(case_id=fid, name=fid, category="safety",
                          prompt=f"prompt-{fid}"))
        findings.append(Finding(finding_id=fid, case_id=fid, status=status,
                                severity=sev, response=f"resp-{fid}"))
    return CanonicalRun(run_id="r", source_tool="qval", model="m", provider="p",
                        cases=cases, findings=findings)


def fixed_judge(suggestion="approve", confidence=0.9, rationale="ok"):
    def fn(prompt, response):
        return {"suggestion": suggestion, "confidence": confidence,
                "rationale": rationale}
    return fn


# --- config -----------------------------------------------------------------

def test_config_defaults_when_absent():
    c = JudgeConfig.from_config({})
    assert c.enabled is False
    assert c.only_status == STATUS_NEEDS_REVIEW
    assert c.severity_not == frozenset({SEVERITY_CRITICAL})
    assert c.require_human_final_decision is True


def test_config_full_parse():
    c = JudgeConfig.from_config({"judge_assist": {
        "enabled": True,
        "only_when": {"status": "needs_review", "severity_not": ["critical", "high"]},
        "model": "claude-sonnet-4-6",
        "require_human_final_decision": False,
        "min_confidence": 0.8,
    }})
    assert c.enabled is True
    assert c.severity_not == frozenset({SEVERITY_CRITICAL, SEVERITY_HIGH})
    assert c.require_human_final_decision is False
    assert c.min_confidence == 0.8


def test_config_bad_confidence_raises():
    with pytest.raises(JudgeConfigError):
        JudgeConfig.from_config({"judge_assist": {"min_confidence": 2}})


def test_config_bad_severity_raises():
    with pytest.raises(JudgeConfigError):
        JudgeConfig.from_config({"judge_assist": {"only_when": {"severity_not": ["nope"]}}})


def test_config_non_mapping_raises():
    with pytest.raises(JudgeConfigError):
        JudgeConfig.from_config({"judge_assist": ["bad"]})


# --- eligibility ------------------------------------------------------------

def test_eligible_excludes_critical_and_non_review():
    run = run_of([("a", STATUS_NEEDS_REVIEW, SEVERITY_MEDIUM),
                  ("b", STATUS_NEEDS_REVIEW, SEVERITY_CRITICAL),  # excluded: critical
                  ("c", STATUS_FAILED, SEVERITY_MEDIUM)])         # excluded: not review
    config = JudgeConfig.from_config({"judge_assist": {"enabled": True}})
    assert [f.finding_id for f in eligible_findings(run, config)] == ["a"]


# --- engine -----------------------------------------------------------------

def test_annotates_and_stamps_metadata():
    run = run_of([("a", STATUS_NEEDS_REVIEW, SEVERITY_MEDIUM)])
    config = JudgeConfig.from_config({"judge_assist": {"enabled": True}})
    result = run_judge(run, config, fixed_judge("approve", 0.9, "looks safe"))
    assert result.evaluated == 1
    judge = run.findings[0].extra["judge"]
    assert judge["suggestion"] == "approve"
    assert judge["confidence"] == 0.9
    assert judge["rationale"] == "looks safe"
    assert judge["prompt_version"] == JUDGE_PROMPT_VERSION
    assert run.metadata["judge_assist"]["evaluated"] == 1


def test_not_applied_when_human_final_required():
    run = run_of([("a", STATUS_NEEDS_REVIEW, SEVERITY_MEDIUM)])
    config = JudgeConfig.from_config({"judge_assist":
        {"enabled": True, "require_human_final_decision": True}})
    run_judge(run, config, fixed_judge("approve", 0.99))
    assert run.findings[0].status == STATUS_NEEDS_REVIEW   # unchanged
    assert run.findings[0].extra["judge"]["applied"] is False


def test_applied_when_allowed_and_confident():
    run = run_of([("a", STATUS_NEEDS_REVIEW, SEVERITY_MEDIUM)])
    config = JudgeConfig.from_config({"judge_assist":
        {"enabled": True, "require_human_final_decision": False, "min_confidence": 0.7}})
    res = run_judge(run, config, fixed_judge("approve", 0.9))
    assert res.applied == 1
    f = run.findings[0]
    assert f.status == STATUS_APPROVED
    assert f.reviewers[-1].reviewer_id == "judge:claude-sonnet-4-6"


def test_reject_suggestion_blocks_when_applied():
    run = run_of([("a", STATUS_NEEDS_REVIEW, SEVERITY_MEDIUM)])
    config = JudgeConfig.from_config({"judge_assist":
        {"enabled": True, "require_human_final_decision": False}})
    run_judge(run, config, fixed_judge("reject", 0.95))
    assert run.findings[0].status == STATUS_BLOCKED


def test_not_applied_below_confidence_floor():
    run = run_of([("a", STATUS_NEEDS_REVIEW, SEVERITY_MEDIUM)])
    config = JudgeConfig.from_config({"judge_assist":
        {"enabled": True, "require_human_final_decision": False, "min_confidence": 0.8}})
    run_judge(run, config, fixed_judge("approve", 0.5))
    assert run.findings[0].status == STATUS_NEEDS_REVIEW


def test_abstain_never_applied():
    run = run_of([("a", STATUS_NEEDS_REVIEW, SEVERITY_MEDIUM)])
    config = JudgeConfig.from_config({"judge_assist":
        {"enabled": True, "require_human_final_decision": False}})
    run_judge(run, config, fixed_judge("abstain", 0.99))
    assert run.findings[0].status == STATUS_NEEDS_REVIEW


def test_cache_avoids_second_call(tmp_path):
    run = run_of([("a", STATUS_NEEDS_REVIEW, SEVERITY_MEDIUM)])
    config = JudgeConfig.from_config({"judge_assist": {"enabled": True}})
    calls = {"n": 0}

    def counting(prompt, response):
        calls["n"] += 1
        return {"suggestion": "approve", "confidence": 0.9, "rationale": "x"}

    cache_path = tmp_path / "jc.json"
    run_judge(run, config, counting, cache=JudgeCache(cache_path))
    # fresh run, same content -> cache hit, judge_fn not called again
    run2 = run_of([("a", STATUS_NEEDS_REVIEW, SEVERITY_MEDIUM)])
    res2 = run_judge(run2, config, counting, cache=JudgeCache(cache_path))
    assert calls["n"] == 1
    assert res2.cached == 1


# --- llm judge_fn -----------------------------------------------------------

def test_parse_verdict_clean_json():
    v = parse_verdict('{"suggestion": "reject", "confidence": 0.8, "rationale": "bad"}')
    assert v["suggestion"] == "reject" and v["confidence"] == 0.8


def test_parse_verdict_embedded_json():
    v = parse_verdict('Sure!\n{"suggestion": "approve", "confidence": 0.7}\nDone')
    assert v["suggestion"] == "approve"


def test_parse_verdict_garbage_abstains():
    assert parse_verdict("no json here")["suggestion"] == "abstain"


def test_make_llm_judge_handles_client_error():
    class ErrClient:
        def complete(self, prompt):
            class R: error = "boom"; text = ""
            return R()
    fn = make_llm_judge(ErrClient())
    assert fn("p", "r")["suggestion"] == "abstain"


# --- CLI --------------------------------------------------------------------

def test_cli_judge_mock(tmp_path, capsys):
    from qval.cli import main
    src = tmp_path / "run.json"
    save_canonical(run_of([("a", STATUS_NEEDS_REVIEW, SEVERITY_MEDIUM)]), src)
    cfg = tmp_path / "qval.yaml"
    cfg.write_text("judge_assist:\n  enabled: true\n", encoding="utf-8")
    rc = main(["judge", str(src), "--config", str(cfg), "--mock", "--no-cache"])
    assert rc == 0
    assert "Judge assist" in capsys.readouterr().out
    reloaded = load_canonical(src)
    assert "judge" in reloaded.findings[0].extra
    assert reloaded.metadata["judge_assist"]["evaluated"] == 1


def test_cli_judge_bad_path_exit_2(tmp_path):
    from qval.cli import main
    rc = main(["judge", str(tmp_path / "missing.json"), "--mock", "--no-cache"])
    assert rc == 2


def test_cli_judge_bad_config_exit_2(tmp_path):
    from qval.cli import main
    src = tmp_path / "run.json"
    save_canonical(run_of([("a", STATUS_NEEDS_REVIEW, SEVERITY_MEDIUM)]), src)
    cfg = tmp_path / "qval.yaml"
    cfg.write_text("judge_assist:\n  min_confidence: 5\n", encoding="utf-8")
    rc = main(["judge", str(src), "--config", str(cfg), "--mock", "--no-cache"])
    assert rc == 2
