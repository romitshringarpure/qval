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
