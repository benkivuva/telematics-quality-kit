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


def test_shell_intro_tells_new_users_what_to_try_first() -> None:
    assert "Start with `fleet`" in Shell.intro
    assert "type `help`" in Shell.intro


@pytest.mark.parametrize(
    "command",
    ["get FAKE-9999", "call unknown_tool {}", "call list_vehicles nope"],
)
def test_c_command_returns_failure_for_command_errors(command: str) -> None:
    output = StringIO()

    result = execute_command(
        create_embedded_session(vehicles=1, seed=3, start=_START), command, stdout=output
    )

    assert result == 1
    assert "error:" in output.getvalue().lower() or "invalid json" in output.getvalue().lower()


def test_report_rejects_unknown_shell_options() -> None:
    output = StringIO()

    result = execute_command(
        create_embedded_session(vehicles=1, seed=3, start=_START),
        "report TRK-0001 --typo",
        stdout=output,
    )

    assert result == 1
    assert "unknown option: --typo" in output.getvalue()


def test_attached_tools_connection_failure_is_concise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from telematics.cli import session as session_module
    from telematics.cli.session import AttachedSession

    session = AttachedSession("http://127.0.0.1:8000/mcp")

    async def unavailable(_url: str) -> list[dict[str, str]]:
        raise ExceptionGroup("transport failed", [ConnectionError("refused")])

    monkeypatch.setattr(session_module, "_list_http_tools", unavailable)
    output = StringIO()

    result = execute_command(session, "tools", stdout=output)

    assert result == 1
    assert "cannot connect to MCP server" in output.getvalue()
    assert "refused" in output.getvalue()
    assert "Traceback" not in output.getvalue()


def test_advancing_one_hour_replays_cadence_without_fleet_wide_drift() -> None:
    session = create_embedded_session(vehicles=3, seed=42, start=_START)

    session.advance(timedelta(hours=1))
    report = session.call_tool("get_quality_report", {"verbose": False})

    assert all(vehicle["data_quality"]["verdict"] == "PASS" for vehicle in report["vehicles"])
    assert all(
        len(session.backend.get_points(vehicle["vehicle_id"])) > 1 for vehicle in report["vehicles"]
    )


def test_embedded_clock_control_commands_update_driver_state() -> None:
    output = StringIO()
    session = create_embedded_session(vehicles=1, seed=3, start=_START)
    shell = Shell(session, stdout=output)

    shell.onecmd("pause")
    assert session.clock_driver.paused
    shell.onecmd("speed 100x")
    assert session.clock_driver.speed == 100
    shell.onecmd("resume")
    assert not session.clock_driver.paused
    assert "paused" in output.getvalue().lower()
    assert "100x" in output.getvalue()


def test_reset_clears_faults_and_seed_rebuilds_embedded_fleet() -> None:
    output = StringIO()
    session = create_embedded_session(vehicles=1, seed=3, start=_START)
    shell = Shell(session, stdout=output)
    shell.onecmd("inject stale_device TRK-0001 --severity high")

    shell.onecmd("reset")
    assert not session.backend._active_faults

    shell.onecmd("seed 99")
    assert session.seed == 99
    assert "seed 99" in output.getvalue().lower()


def test_main_dispatches_shell_c_command(capsys: pytest.CaptureFixture[str]) -> None:
    result = cli_main.main(["shell", "--vehicles", "1", "-c", "get TRK-0001"])

    assert result == 0
    assert "TRK-0001" in capsys.readouterr().out


def test_ctrl_c_exits_interactive_shell_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def interrupt(_shell: Shell) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_main.Shell, "cmdloop", interrupt)

    assert cli_main.main(["shell", "--vehicles", "1"]) == 0
    output = capsys.readouterr().out
    assert "Interrupted; exiting shell." in output
    assert "Traceback" not in output


def test_interactive_shell_generates_ten_minutes_of_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    real_create = cli_main.create_embedded_session

    def fake_create(**kwargs: object):
        session = real_create(**kwargs)  # type: ignore[arg-type]
        captured["session"] = session
        return session

    monkeypatch.setattr(cli_main, "create_embedded_session", fake_create)
    monkeypatch.setattr(
        cli_main.Shell,
        "cmdloop",
        lambda self: captured.setdefault("at", self.session.clock.now()),
    )

    status = cli_main.main(["shell", "--vehicles", "1"])

    assert status == 0
    assert captured["at"] == datetime(2024, 4, 5, 6, 17, 8, tzinfo=UTC)


def test_c_command_does_not_add_cold_start_history() -> None:
    session = create_embedded_session(vehicles=1, seed=3, start=_START)
    before = session.clock.now()

    execute_command(session, "fleet")

    assert session.clock.now() == before


def test_advance_displays_east_africa_time() -> None:
    output = StringIO()
    start = datetime(2025, 1, 1, 6, 7, 8, tzinfo=UTC)
    shell = Shell(create_embedded_session(vehicles=1, seed=3, start=start), stdout=output)

    shell.onecmd("advance 6m")

    assert "09:13:08 EAT" in output.getvalue()


def test_get_separates_freshness_from_validity() -> None:
    output = StringIO()
    shell = Shell(create_embedded_session(vehicles=1, seed=3, start=_START), stdout=output)

    shell.onecmd("get TRK-0001")

    text = output.getvalue()
    assert "age 0s (Fresh)" in text
    assert "✓ PASS — trust it (freshness)" in text


def test_get_shows_the_responsible_check_for_block() -> None:
    output = StringIO()
    shell = Shell(create_embedded_session(vehicles=1, seed=3, start=_START), stdout=output)
    shell.onecmd("inject gps_drift TRK-0001 --severity high")
    shell.onecmd("advance 1m")
    output.truncate(0)
    output.seek(0)

    shell.onecmd("get TRK-0001")

    text = output.getvalue()
    assert "age 0s (Fresh)" in text
    assert "⛔ BLOCK — don't trust it (drift)" in text


def test_inject_prints_the_fleet_summary() -> None:
    output = StringIO()
    shell = Shell(create_embedded_session(vehicles=2, seed=3, start=_START), stdout=output)

    shell.onecmd("inject gps_drift TRK-0001 --severity high")

    text = output.getvalue()
    assert "expected:" in text
    assert "drift BLOCK within 2m at high severity" in text
    assert "2 vehicles · fleet trust" in text


def test_faults_lists_severity() -> None:
    output = StringIO()
    shell = Shell(create_embedded_session(vehicles=1, seed=3, start=_START), stdout=output)
    shell.onecmd("inject duplicate_heartbeats TRK-0001 --severity high")
    output.truncate(0)
    output.seek(0)

    shell.onecmd("faults")

    assert "duplicate_heartbeats TRK-0001 (high)" in output.getvalue()


def test_clear_lists_the_faults_it_cleared() -> None:
    output = StringIO()
    shell = Shell(create_embedded_session(vehicles=2, seed=3, start=_START), stdout=output)
    shell.onecmd("inject gps_drift TRK-0001 --severity high")
    shell.onecmd("inject duplicate_heartbeats LRY-0001 --severity low")
    output.truncate(0)
    output.seek(0)

    shell.onecmd("clear all")

    text = output.getvalue()
    assert "gps_drift TRK-0001 (high)" in text
    assert "duplicate_heartbeats LRY-0001 (low)" in text


def test_clear_can_target_one_fault_without_clearing_others() -> None:
    output = StringIO()
    shell = Shell(create_embedded_session(vehicles=2, seed=3, start=_START), stdout=output)
    shell.onecmd("inject gps_drift TRK-0001 --severity high")
    shell.onecmd("inject stale_device LRY-0001 --severity high")
    output.truncate(0)
    output.seek(0)

    shell.onecmd("clear drift TRK-0001")

    text = output.getvalue()
    assert "cleared 1 simulator faults" in text
    assert "gps_drift TRK-0001 (high)" in text
    assert next(iter(shell.session.backend._active_faults.values())).name == "stale_device"


def test_fleet_warns_when_the_whole_fleet_flips_to_block() -> None:
    output = StringIO()
    shell = Shell(create_embedded_session(vehicles=2, seed=3, start=_START), stdout=output)
    shell.onecmd("fleet")
    assert "Warning: entire fleet changed verdict together" not in output.getvalue()

    shell.onecmd("inject gps_drift TRK-0001 --severity high")
    shell.onecmd("inject gps_drift LRY-0001 --severity high")
    shell.onecmd("advance 1m")
    output.truncate(0)
    output.seek(0)

    shell.onecmd("fleet")

    assert (
        "Warning: entire fleet changed verdict together — check the simulator." in output.getvalue()
    )


def test_ls_warns_when_the_whole_fleet_flips_to_block() -> None:
    output = StringIO()
    shell = Shell(create_embedded_session(vehicles=2, seed=3, start=_START), stdout=output)
    shell.onecmd("ls")
    assert "Warning: entire fleet changed verdict together" not in output.getvalue()

    shell.onecmd("inject gps_drift TRK-0001 --severity high")
    shell.onecmd("inject gps_drift LRY-0001 --severity high")
    shell.onecmd("advance 1m")
    output.truncate(0)
    output.seek(0)

    shell.onecmd("ls")

    assert (
        "Warning: entire fleet changed verdict together — check the simulator." in output.getvalue()
    )
