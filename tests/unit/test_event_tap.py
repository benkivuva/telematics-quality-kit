"""Typed event delivery and bounded, nonblocking subscriber behavior."""

from datetime import UTC, datetime

import pytest

from telematics.ingest.events import (
    ChecksEvaluated,
    Decoded,
    FaultCleared,
    FaultInjected,
    FrameReceived,
    ParseFailed,
    PipelineEvent,
    Stored,
    VerdictChanged,
)
from telematics.ingest.tap import EventTap
from telematics.models.quality import Verdict
from telematics.models.telemetry import TelemetryPoint


def _point() -> TelemetryPoint:
    return TelemetryPoint(
        datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC), -1.2921, 36.8219, 30.0, 90, 8, 1
    )


@pytest.mark.unit
def test_event_models_are_typed_and_subscribers_receive_in_order() -> None:
    events: tuple[PipelineEvent, ...] = (
        FrameReceived("TRK-0001", b"raw"),
        Decoded("TRK-0001", (_point(),)),
        ParseFailed("TRK-0001", "bad CRC"),
        Stored("TRK-0001", _point()),
        ChecksEvaluated("TRK-0001", ()),
        VerdictChanged("TRK-0001", Verdict.WARN, Verdict.PASS),
        FaultInjected("TRK-0001", "stale_device", "freshness becomes WARN"),
        FaultCleared("TRK-0001", "stale_device"),
    )
    tap = EventTap()
    first = tap.subscribe(maxsize=8)
    second = tap.subscribe(maxsize=8)

    for event in events:
        tap.publish(event)

    assert tuple(first.get_nowait() for _ in events) == events
    assert tuple(second.get_nowait() for _ in events) == events


@pytest.mark.unit
def test_full_subscriber_queue_drops_its_oldest_event_and_counts_it() -> None:
    tap = EventTap()
    subscriber = tap.subscribe(maxsize=2)
    events = [FrameReceived("TRK-0001", bytes((value,))) for value in range(3)]

    for event in events:
        tap.publish(event)

    assert [subscriber.get_nowait(), subscriber.get_nowait()] == events[1:]
    assert subscriber.tap_dropped == 1
    assert tap.tap_dropped == 1


@pytest.mark.unit
def test_slow_subscriber_does_not_hold_up_fast_subscribers() -> None:
    tap = EventTap()
    slow = tap.subscribe(maxsize=8)
    fast = tap.subscribe(maxsize=1)

    for value in range(1000):
        event = FrameReceived("TRK-0001", value.to_bytes(2, "big"))
        tap.publish(event)
        assert fast.get_nowait() == event

    assert slow.tap_dropped == 992
    assert fast.tap_dropped == 0


@pytest.mark.unit
def test_unsubscribe_stops_delivery() -> None:
    tap = EventTap()
    subscriber = tap.subscribe(maxsize=1)
    tap.unsubscribe(subscriber)

    tap.publish(FrameReceived("TRK-0001", b"frame"))

    assert subscriber.empty()


@pytest.mark.unit
def test_tap_drop_total_is_retained_after_unsubscribe() -> None:
    tap = EventTap()
    subscriber = tap.subscribe(maxsize=1)
    tap.publish(FrameReceived("TRK-0001", b"first"))
    tap.publish(FrameReceived("TRK-0001", b"second"))

    tap.unsubscribe(subscriber)

    assert tap.tap_dropped == 1
