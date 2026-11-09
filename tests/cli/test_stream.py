"""Sampling and rendering tests for the pipeline event stream."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from telematics.cli import main as cli_main
from telematics.cli.stream import (
    EventSampler,
    StreamEvent,
    drain_subscription,
    format_event,
)
from telematics.ingest.events import (
    ChecksEvaluated,
    Decoded,
    FaultInjected,
    FrameReceived,
    ParseFailed,
    Stored,
    VerdictChanged,
)
from telematics.ingest.tap import EventTap
from telematics.models.quality import CheckResult, Verdict
from telematics.models.telemetry import TelemetryPoint

_AT = datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC)
_POINT = TelemetryPoint(_AT, -1.2921, 36.8219, 42.0, 90, 8, 1)


@pytest.mark.unit
def test_stream_model_is_strict_and_carries_schema_version() -> None:
    line = StreamEvent(
        timestamp=_AT.isoformat(),
        vehicle_id="TRK-0001",
        stage="RX",
        message="received frame",
    )

    assert line.schema_version == "1.0"
    with pytest.raises(ValidationError):
        StreamEvent.model_validate({**line.model_dump(), "unexpected": True})


@pytest.mark.unit
def test_frame_event_has_protocol_size_and_optional_full_hex() -> None:
    frame = FrameReceived("TRK-0001", bytes.fromhex("01020304"))

    short = format_event(frame, at=_AT, protocol="teltonika")
    full = format_event(frame, at=_AT, protocol="teltonika", show_hex=True)

    assert short.stage == "RX"
    assert short.details == {"protocol": "teltonika", "bytes": 4, "hex": "0102…"}
    assert full.details["hex"] == "01020304"


@pytest.mark.unit
def test_pipeline_events_map_to_readable_stages_and_priority() -> None:
    issue = CheckResult("drift", Verdict.WARN, 0.79, {"flagged_fraction": 0.02})
    events = (
        (Decoded("TRK-0001", (_POINT,)), "DECODE", False),
        (Stored("TRK-0001", _POINT), "STORE", False),
        (ParseFailed("TRK-0001", "bad CRC"), "PARSE", True),
        (ChecksEvaluated("TRK-0001", (issue,)), "ISSUE", True),
        (VerdictChanged("TRK-0001", Verdict.PASS, Verdict.WARN), "VERDICT", True),
        (FaultInjected("TRK-0001", "gps_drift", "drift WARN"), "FAULT", True),
    )

    for event, expected_stage, expected_priority in events:
        line = format_event(event, at=_AT)
        assert line.stage == expected_stage
        assert line.priority is expected_priority
        assert line.vehicle_id == "TRK-0001"


@pytest.mark.unit
def test_sampler_throttles_normal_events_but_never_priority_events() -> None:
    sampler = EventSampler(rate=1)
    normal = FrameReceived("TRK-0001", b"frame")
    issue = ParseFailed("TRK-0001", "bad CRC")

    assert sampler.include(normal, now=0.0)
    assert not sampler.include(normal, now=0.1)
    assert sampler.include(issue, now=0.2)
    assert sampler.include(normal, now=1.1)
    assert sampler.sampled == 1
    assert sampler.normal_seen == 3


@pytest.mark.integration
def test_stream_drains_json_events_and_keeps_parse_failures_under_sampling() -> None:
    tap = EventTap()
    subscription = tap.subscribe(maxsize=8)
    tap.publish(FrameReceived("TRK-0001", b"frame"))
    tap.publish(ParseFailed("TRK-0001", "bad CRC"))
    ticks = iter((0.0, 0.1))

    lines = drain_subscription(
        subscription,
        at=_AT,
        protocol_for=lambda _vehicle: "teltonika",
        sampler=EventSampler(rate=1),
        as_json=True,
        monotonic=lambda: next(ticks),
    )

    assert [StreamEvent.model_validate_json(line).stage for line in lines] == ["RX", "PARSE"]


def test_main_dispatches_stream_sampling_and_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def fake_stream(**kwargs: object) -> int:
        called.update(kwargs)
        return 0

    monkeypatch.setattr(cli_main, "run_stream", fake_stream)

    status = cli_main.main(
        ["stream", "--vehicles", "2", "--rate", "4", "--stage", "issue", "--json"]
    )

    assert status == 0
    assert called["vehicles"] == 2
    assert called["rate"] == 4
    assert called["stages"] == {"issue"}
    assert called["as_json"] is True
