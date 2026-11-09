"""Attached fault injection and verdict polling tests."""

from typing import Any

import pytest

from telematics.cli import main as cli_main
from telematics.cli.inject import inject_and_wait, poll_for_verdict


class FakeClient:
    def __init__(self, verdicts: list[str] | Exception) -> None:
        self.verdicts = verdicts
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.url = "http://127.0.0.1:8000/mcp"

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if isinstance(self.verdicts, Exception):
            raise self.verdicts
        if name == "inject_fault":
            return {
                "fault_id": "fault-1",
                "fault": "stale_device",
                "expected_quality_impact": "freshness BLOCK",
            }
        verdict = self.verdicts.pop(0) if len(self.verdicts) > 1 else self.verdicts[0]
        return {"vehicles": [{"data_quality": {"verdict": verdict}}]}


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_poll_returns_success_when_expected_verdict_arrives() -> None:
    clock = FakeTime()
    client = FakeClient(["PASS", "BLOCK"])

    result = poll_for_verdict(
        client.call_tool,
        vehicle_id="TRK-0001",
        expected="BLOCK",
        timeout_seconds=5,
        interval_seconds=1,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    assert result == 0
    assert clock.now == 1


def test_poll_returns_timeout_status_when_verdict_does_not_arrive() -> None:
    clock = FakeTime()
    client = FakeClient(["PASS"])

    result = poll_for_verdict(
        client.call_tool,
        vehicle_id="TRK-0001",
        expected="BLOCK",
        timeout_seconds=2,
        interval_seconds=1,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    assert result == 1
    assert clock.now == 2


def test_inject_returns_unreachable_status_with_actionable_fix(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeClient(ConnectionError("refused"))

    status = inject_and_wait(
        client,
        fault="stale_device",
        vehicle_id="TRK-0001",
        severity="high",
        duration="15m",
        expected="BLOCK",
        timeout_seconds=2,
        interval_seconds=1,
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
    )

    assert status == 3
    assert "uv run telematics serve" in capsys.readouterr().out
    assert client.calls[0] == (
        "inject_fault",
        {
            "vehicle_id": "TRK-0001",
            "fault": "stale_device",
            "params": {"severity": "high", "duration": "15m"},
        },
    )


def test_inject_without_wait_returns_after_fault_is_accepted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeClient([])

    status = inject_and_wait(
        client,
        fault="stale_device",
        vehicle_id="TRK-0001",
        severity="medium",
        duration=None,
        expected="BLOCK",
        timeout_seconds=None,
        interval_seconds=1,
    )

    assert status == 0
    assert "fault-1" in capsys.readouterr().out


def test_inject_accepts_the_blackout_alias() -> None:
    client = FakeClient([])

    inject_and_wait(
        client,
        fault="blackout",
        vehicle_id="TRK-0001",
        severity="medium",
        duration="20m",
        expected="BLOCK",
        timeout_seconds=None,
    )

    assert client.calls[0][1]["fault"] == "rural_blackout"


def test_main_dispatches_inject_wait_to_attached_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = FakeClient(["BLOCK"])
    monkeypatch.setattr(cli_main, "AttachedSession", lambda _url: client)

    status = cli_main.main(["inject", "stale_device", "--vehicle", "TRK-0001", "--wait", "2s"])

    assert status == 0
    assert "observed expected BLOCK" in capsys.readouterr().out
