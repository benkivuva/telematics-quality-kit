"""Interactive shell command and script tests."""

import json
from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest

from telematics.cli import main as cli_main
from telematics.cli.session import create_embedded_session
from telematics.cli.shell import Shell, execute_command, run_script

_START = datetime(2025, 1, 1, tzinfo=UTC)


@pytest.mark.integration
def test_explain_uses_service_check_metrics_and_thresholds() -> None:
    output = StringIO()
    shell = Shell(create_embedded_session(vehicles=1, seed=3, start=_START), stdout=output)

    shell.onecmd("explain TRK-0001 freshness")

    assert "freshness PASS" in output.getvalue()
    assert "expected_interval_seconds" in output.getvalue()


@pytest.mark.integration
def test_call_prints_the_same_structured_json_as_the_mcp_tool() -> None:
    session = create_embedded_session(vehicles=1, seed=3, start=_START)
    output = StringIO()
    shell = Shell(session, stdout=output)
    expected = session.call_tool("get_vehicle_location", {"vehicle_id": "TRK-0001"})

    shell.onecmd('call get_vehicle_location {"vehicle_id":"TRK-0001"}')

    assert json.loads(output.getvalue()) == expected


@pytest.mark.integration
def test_inject_advance_and_expect_drive_embedded_simulator() -> None:
    output = StringIO()
    session = create_embedded_session(vehicles=1, seed=3, start=_START)
    shell = Shell(session, stdout=output)

    shell.onecmd("inject stale_device TRK-0001 --severity high")
    shell.onecmd("advance 6m")
    shell.onecmd("expect verdict TRK-0001 BLOCK")

    assert "high" in output.getvalue()
    assert session.clock.now() == _START + timedelta(minutes=6)
    assert "expectation passed" in output.getvalue().lower()


def test_script_failure_reports_source_line_and_returns_one() -> None:
    output = StringIO()
    shell = Shell(create_embedded_session(vehicles=1, seed=3, start=_START), stdout=output)

    result = run_script(shell, "# test\nget TRK-0001\nexpect verdict TRK-0001 BLOCK\n")

    assert result == 1
    assert "line 3" in output.getvalue()


def test_c_command_runs_once_and_returns_success() -> None:
    output = StringIO()

    result = execute_command(
        create_embedded_session(vehicles=1, seed=3, start=_START), "get TRK-0001", stdout=output
    )

    assert result == 0
    assert "TRK-0001" in output.getvalue()


def test_main_dispatches_shell_c_command(capsys: pytest.CaptureFixture[str]) -> None:
    result = cli_main.main(["shell", "--vehicles", "1", "-c", "get TRK-0001"])

    assert result == 0
    assert "TRK-0001" in capsys.readouterr().out
