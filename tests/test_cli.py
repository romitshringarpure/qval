import pytest

from qval.cli import main


def test_no_command_prints_help_and_exits_nonzero(capsys):
    rc = main([])
    captured = capsys.readouterr()
    assert rc != 0
    assert "usage" in captured.out.lower() or "usage" in captured.err.lower()


@pytest.mark.parametrize("cmd", ["gate", "report", "import"])
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
