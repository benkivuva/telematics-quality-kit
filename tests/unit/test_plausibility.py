"""Structural and temporal plausibility tests."""

from datetime import UTC, datetime, timedelta

import pytest

from telematics.config import PlausibilityConfig
from telematics.models.quality import Verdict
from telematics.models.telemetry import TelemetryPoint
from telematics.quality.plausibility import PlausibilityCheck


def point(
    at: datetime, *, lat: float = 1.0, lon: float = 2.0, speed: float = 0.0
) -> TelemetryPoint:
    return TelemetryPoint(at, lat, lon, speed, 0, 8, 1, received_at=at)


@pytest.mark.unit
def test_plausibility_blocks_out_of_range_location() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)

    result = PlausibilityCheck(PlausibilityConfig()).evaluate(
        (point(now, lat=91.0),), as_of=now, max_speed_kph=90
    )

    assert result.verdict is Verdict.BLOCK
    assert result.metric["invalid_points"] == 1


@pytest.mark.unit
def test_plausibility_warns_for_five_minute_clock_skew() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    stale_device_time = now - timedelta(minutes=6)

    result = PlausibilityCheck(PlausibilityConfig()).evaluate(
        (TelemetryPoint(stale_device_time, 1.0, 2.0, 0.0, 0, 8, 1, received_at=now),),
        as_of=now,
        max_speed_kph=90,
    )

    assert result.verdict is Verdict.WARN


@pytest.mark.unit
def test_plausibility_blocks_for_future_time_and_excess_speed() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)

    result = PlausibilityCheck(PlausibilityConfig()).evaluate(
        (point(now + timedelta(seconds=1), speed=91),),
        as_of=now,
        max_speed_kph=90,
    )

    assert result.verdict is Verdict.BLOCK
