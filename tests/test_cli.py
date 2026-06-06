import pytest

from qval.cli import main


def test_no_command_prints_help_and_exits_nonzero(capsys):
    rc = main([])
    captured = capsys.readouterr()
    assert rc != 0
    assert "usage" in captured.out.lower() or "usage" in captured.err.lower()


@pytest.mark.parametrize("cmd", ["report"])
def test_stub_commands_report_not_implemented(cmd, capsys):
    rc = main([cmd])
    captured = capsys.readouterr()
    assert rc == 3
    assert "not implemented" in (captured.out + captured.err).lower()


def test_init_creates_scaffold(tmp_path):
    rc = main(["init", "--path", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "qval.yaml").is_file()
    assert (tmp_path / "policy.yaml").is_file()
    assert (tmp_path / "suites" / "example.json").is_file()


def test_init_refuses_overwrite_without_force(tmp_path):
    (tmp_path / "qval.yaml").write_text("provider: mock\n", encoding="utf-8")
    rc = main(["init", "--path", str(tmp_path)])
    assert rc != 0
    assert "provider: mock" in (tmp_path / "qval.yaml").read_text(encoding="utf-8")


def test_init_force_overwrites(tmp_path):
    (tmp_path / "qval.yaml").write_text("STALE", encoding="utf-8")
    rc = main(["init", "--path", str(tmp_path), "--force"])
    assert rc == 0
    assert "provider:" in (tmp_path / "qval.yaml").read_text(encoding="utf-8")


def test_shipped_template_suites_are_schema_valid():
    """Every suite shipped by `qval init` must load via the native schema."""
    import json
    from qval.engine.schemas import TestCase
    from qval.commands.init import TEMPLATES_DIR

    suite_files = list((TEMPLATES_DIR / "suites").glob("*.json"))
    assert suite_files, "no template suites found"
    for suite_file in suite_files:
        cases = json.loads(suite_file.read_text(encoding="utf-8"))
        assert isinstance(cases, list) and cases
        for raw in cases:
            TestCase.from_dict(raw, source=str(suite_file))  # raises on invalid


def test_doctor_healthy_mock_project(tmp_path, monkeypatch):
    main(["init", "--path", str(tmp_path)])
    monkeypatch.chdir(tmp_path)
    rc = main(["doctor"])
    assert rc == 0  # mock provider needs no API key


def test_doctor_fails_when_openai_key_missing(tmp_path, monkeypatch):
    main(["init", "--path", str(tmp_path)])
    (tmp_path / "qval.yaml").write_text(
        "provider: openai\nmodel: gpt-4o-mini\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    rc = main(["doctor"])
    assert rc != 0


def test_doctor_warns_on_missing_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no qval.yaml here or above (isolated tmp)
    rc = main(["doctor"])
    assert rc == 0  # missing config is a WARN, not a failure


def test_doctor_fails_on_unparseable_config(tmp_path, monkeypatch):
    (tmp_path / "qval.yaml").write_text("provider: [unclosed\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = main(["doctor"])
    assert rc != 0  # present-but-broken config FAILs


def test_doctor_unknown_provider_warns(tmp_path, monkeypatch):
    main(["init", "--path", str(tmp_path)])
    (tmp_path / "qval.yaml").write_text("provider: anthropic\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = main(["doctor"])
    assert rc == 0  # unknown provider is WARN, not FAIL


def test_run_mock_smoke(capsys):
    rc = main(["run", "--suite", "all", "--mock", "--per-suite-limit", "1"])
    out = capsys.readouterr().out
    assert rc in (0, 1)  # 1 only if mock produced a critical failure
    assert "Run ID" in out
