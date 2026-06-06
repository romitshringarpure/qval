"""F-09 · DeepEval importer tests.

Covers the parser (layout variants, snake/camel aliases, metric-driven status /
score / reason), severity defaulting + override, registry registration, and the
`qval import deepeval` CLI.
"""
from __future__ import annotations

import json

from qval.canonical import STATUS_PASSED, STATUS_FAILED, SEVERITY_INFO, SEVERITY_HIGH
from qval.canonical.io import load_canonical
from qval.importers import available_tools, get_importer
from qval.importers.deepeval import DeepEvalImporter


def imp(data, **kw):
    return DeepEvalImporter().to_canonical(
        data, default_severity=kw.get("default_severity", SEVERITY_INFO),
        source=kw.get("source", "deepeval.json"))


def case(**kw):
    base = {"name": "t1", "input": "q", "actualOutput": "a", "success": True,
            "metricsData": []}
    base.update(kw)
    return base


# --- registry ---------------------------------------------------------------

def test_deepeval_registered():
    assert "deepeval" in available_tools()
    assert get_importer("deepeval").tool_name == "deepeval"


# --- locating records -------------------------------------------------------

def test_locate_top_level_list():
    run = imp([case(name="a"), case(name="b")])
    assert [c.case_id for c in run.cases] == ["a", "b"]


def test_locate_testcases_key():
    run = imp({"testCases": [case(name="a")]})
    assert [c.case_id for c in run.cases] == ["a"]


def test_locate_snake_test_results_key():
    run = imp({"test_results": [case(name="a")]})
    assert len(run.findings) == 1


# --- field mapping ----------------------------------------------------------

def test_case_field_mapping():
    run = imp({"testCases": [case(name="t1", input="the prompt",
                                  actualOutput="the answer",
                                  expectedOutput="the ideal")]})
    c = run.cases[0]
    assert c.prompt == "the prompt"
    assert c.expected_behavior == "the ideal"
    assert c.source_tool == "deepeval"
    assert run.findings[0].response == "the answer"


def test_snake_case_aliases():
    run = imp([{"name": "t", "input": "q", "actual_output": "a",
                "expected_output": "e", "success": True}])
    assert run.cases[0].expected_behavior == "e"
    assert run.findings[0].response == "a"


# --- status -----------------------------------------------------------------

def test_explicit_success_false_is_failed():
    run = imp([case(success=False)])
    assert run.findings[0].status == STATUS_FAILED


def test_status_derived_from_metrics_when_success_absent():
    rec = {"name": "t", "input": "q",
           "metricsData": [{"name": "Bias", "score": 0.2, "success": True},
                           {"name": "Toxicity", "score": 0.9, "success": False}]}
    run = imp([rec])
    assert run.findings[0].status == STATUS_FAILED  # one metric failed


def test_status_passed_when_all_metrics_pass_and_no_success():
    rec = {"name": "t", "input": "q",
           "metricsData": [{"name": "Faithfulness", "score": 0.9, "success": True}]}
    run = imp([rec])
    assert run.findings[0].status == STATUS_PASSED


def test_empty_metrics_no_success_defaults_passed():
    run = imp([{"name": "t", "input": "q"}])
    assert run.findings[0].status == STATUS_PASSED


# --- score / reason / extra -------------------------------------------------

def test_driving_metric_score_and_reason():
    rec = {"name": "t", "input": "q", "success": False,
           "metricsData": [
               {"name": "Relevancy", "score": 0.9, "success": True, "reason": "ok"},
               {"name": "Hallucination", "score": 0.8, "success": False,
                "reason": "made up a fact"},
           ]}
    f = imp([rec]).findings[0]
    assert f.score == 0.8                      # the failing metric drives score
    assert "Hallucination: made up a fact" in f.reason
    assert "Relevancy" not in f.reason          # only failing metric reasons
    assert f.extra["metrics"]                    # full metric data preserved


# --- severity ---------------------------------------------------------------

def test_default_severity_info():
    assert imp([case()]).findings[0].severity == SEVERITY_INFO


def test_default_severity_override():
    assert imp([case()], default_severity=SEVERITY_HIGH).findings[0].severity == SEVERITY_HIGH


def test_metadata_severity_wins():
    rec = case(metadata={"severity": "high"})
    assert imp([rec]).findings[0].severity == SEVERITY_HIGH


# --- run metadata -----------------------------------------------------------

def test_model_and_suite_from_data():
    run = imp({"model": "gpt-4o", "testRunName": "nightly", "testCases": [case()]})
    assert run.model == "gpt-4o"
    assert run.suite == "nightly"


def test_suite_falls_back_to_source_stem():
    run = imp([case()], source="/tmp/my_run.json")
    assert run.suite == "my_run"


# --- CLI --------------------------------------------------------------------

def test_cli_import_deepeval(tmp_path, capsys):
    from qval.cli import main
    src = tmp_path / "results.json"
    src.write_text(json.dumps({"testCases": [
        case(name="ok", success=True),
        case(name="bad", success=False),
    ]}), encoding="utf-8")
    out = tmp_path / "run.json"
    rc = main(["import", "deepeval", str(src), "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "deepeval" in printed and "1 passed, 1 failed" in printed
    run = load_canonical(out)
    assert run.source_tool == "deepeval"
    assert {f.status for f in run.findings} == {STATUS_PASSED, STATUS_FAILED}


def test_cli_import_deepeval_dir(tmp_path):
    from qval.cli import main
    (tmp_path / "results.json").write_text(
        json.dumps({"testCases": [case()]}), encoding="utf-8")
    out = tmp_path / "run.json"
    rc = main(["import", "deepeval", str(tmp_path), "--out", str(out)])
    assert rc == 0
    assert load_canonical(out).source_tool == "deepeval"


def test_cli_import_deepeval_bad_path_exit_1(tmp_path):
    from qval.cli import main
    rc = main(["import", "deepeval", str(tmp_path / "missing.json")])
    assert rc == 1
